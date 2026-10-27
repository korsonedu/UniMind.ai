"""Small offline guards for the persistent synthetic preview."""
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import preview


class PreviewSmoke(unittest.TestCase):
    def test_state_cannot_escape_the_ignored_preview_root(self):
        with TemporaryDirectory() as folder, patch.object(preview, 'ROOT', Path(folder)):
            root = Path(folder).resolve()
            (root / '.m0-state').mkdir()
            self.assertEqual(preview.preview_state('.m0-state/demo'), root / '.m0-state/demo')
            for value in ('backend', '/tmp/foreign', '.m0-state/../../foreign'):
                with self.assertRaises(ValueError):
                    preview.preview_state(value)
            (root / '.m0-state/link').symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                preview.preview_state('.m0-state/link/demo')

    def test_existing_database_must_contain_only_the_two_synthetic_users(self):
        with TemporaryDirectory() as folder:
            state = Path(folder)
            with sqlite3.connect(state / 'db.sqlite3') as database:
                database.execute('CREATE TABLE users_user (username text)')
                database.executemany('INSERT INTO users_user VALUES (?)', [('m0-student',), ('m0-other',)])
            preview.check_database(state)
            with sqlite3.connect(state / 'db.sqlite3') as database:
                database.execute('INSERT INTO users_user VALUES (?)', ('real-user',))
            with self.assertRaises(ValueError):
                preview.check_database(state)

    def test_a_missing_database_is_not_created_by_the_guard(self):
        with TemporaryDirectory() as folder:
            state = Path(folder)
            with self.assertRaises((ValueError, sqlite3.Error)):
                preview.check_database(state)
            self.assertFalse((state / 'db.sqlite3').exists())

    def test_sdk_symlink_preserves_its_virtual_environment(self):
        with TemporaryDirectory() as folder:
            python = Path(folder) / 'python'
            python.symlink_to(sys.executable)
            with patch('preview.subprocess.run', return_value=subprocess.CompletedProcess([], 0)) as run:
                self.assertEqual(preview.sdk_executable(python), str(python.absolute()))
                self.assertEqual(run.call_args.args[0][0], str(python.absolute()))
            with patch('preview.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
                with self.assertRaises(ValueError):
                    preview.sdk_executable(python)


if __name__ == '__main__':
    unittest.main()
