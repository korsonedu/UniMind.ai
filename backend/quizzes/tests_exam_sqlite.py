import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Event

import pytest
from django.db import connections, transaction


def test_sqlite_exam_transaction_waits_before_reading(tmp_path, monkeypatch, django_db_blocker):
    config = connections['default'].settings_dict
    if config['ENGINE'] != 'django.db.backends.sqlite3':
        pytest.skip('SQLite transaction behavior')

    alias = 'exam_lock_test'
    path = tmp_path / 'exam.sqlite3'
    monkeypatch.setitem(connections.databases, alias, {**config, 'NAME': path})
    reader = connections[alias]
    begin_attempted = Event()

    def observe_begin(execute, sql, params, many, context):
        if sql == 'BEGIN IMMEDIATE':
            begin_attempted.set()
        return execute(sql, params, many, context)

    def read_then_write():
        db = connections[alias]
        try:
            with db.execute_wrapper(observe_begin), transaction.atomic(using=alias), db.cursor() as cursor:
                cursor.execute('SELECT value FROM exam_probe')
                value, = cursor.fetchone()
                cursor.execute('UPDATE exam_probe SET value = %s', [value + 1])
                return value
        finally:
            db.close()

    try:
        with django_db_blocker.unblock(), reader.cursor() as cursor:
            for pragma, expected in [('journal_mode', 'wal'), ('synchronous', 1), ('busy_timeout', 30000)]:
                cursor.execute(f'PRAGMA {pragma}')
                assert cursor.fetchone() == (expected,)
            cursor.execute('CREATE TABLE exam_probe (value INTEGER NOT NULL)')
            cursor.execute('INSERT INTO exam_probe VALUES (0)')

            with closing(sqlite3.connect(path)) as writer, ThreadPoolExecutor(max_workers=1) as pool:
                writer.execute('UPDATE exam_probe SET value = 1')
                pending = pool.submit(read_then_write)
                try:
                    assert begin_attempted.wait(5)
                    cursor.execute('SELECT value FROM exam_probe')
                    assert cursor.fetchone() == (0,)
                finally:
                    writer.commit()
                assert pending.result(timeout=5) == 1
                cursor.execute('SELECT value FROM exam_probe')
                assert cursor.fetchone() == (2,)
    finally:
        reader.close()
        del connections[alias]
