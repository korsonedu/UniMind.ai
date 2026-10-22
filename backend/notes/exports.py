import io
import json
import posixpath
import re
import zipfile
from urllib.parse import quote
from django.http import HttpResponse
from .links import rewrite_note_links
from .models import Note, Notebook
from .access import notebook_ids


def filename(name, pk):
    name = re.sub(r'[\\/\x00-\x1f:*?"<>|]', '_', name).strip(' .')
    suffix = f'-{pk}'
    # Reserve four bytes for .zip (also enough for .md) on 255-byte filesystems.
    name = name.encode('utf-8')[:255 - 4 - len(suffix.encode('utf-8'))].decode('utf-8', errors='ignore').rstrip(' .')
    return f'{name or "未命名"}{suffix}'


def notebook_paths(user):
    books = {book.pk: book for book in Notebook.objects.filter(user=user)}
    paths = {}

    def path(pk):
        if pk not in paths:
            book = books[pk]
            parent = path(book.parent_id) if book.parent_id in books else ''
            paths[pk] = posixpath.join(parent, filename(book.name, pk))
        return paths[pk]

    for pk in books:
        path(pk)
    return paths


def markdown(note, paths, files):
    def replace(match):
        target = files.get(int(match.group(1)))
        return quote(posixpath.relpath(target, posixpath.dirname(files[note.pk]))) if target else match.group(0)

    content = rewrite_note_links(note.content, replace)
    tags = list(note.tags.values_list('name', flat=True))
    return ('---\ntitle: ' + json.dumps(note.title, ensure_ascii=False)
            + '\ntags: ' + json.dumps(tags, ensure_ascii=False)
            + '\nnotebook: ' + json.dumps(paths.get(note.notebook_id, ''), ensure_ascii=False)
            + '\n---\n\n' + content + '\n')


def attachment(content, name, content_type):
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = "attachment; filename*=UTF-8''" + quote(name)
    return response


def export_note(note):
    name = filename(note.title, note.pk) + '.md'
    return attachment(markdown(note, notebook_paths(note.user), {note.pk: name}), name, 'text/markdown; charset=utf-8')


def export_notebook(notebook):
    notes = list(Note.objects.filter(user=notebook.user, deleted_at__isnull=True,
                                    notebook_id__in=notebook_ids(notebook.user, [notebook.pk])).prefetch_related('tags'))
    paths = notebook_paths(notebook.user)
    files = {note.pk: posixpath.join(paths[note.notebook_id], filename(note.title, note.pk) + '.md') for note in notes}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        # Include empty directories as well as the notes inside them.
        for pk in notebook_ids(notebook.user, [notebook.pk]):
            archive.writestr(paths[pk] + '/', '')
        for note in notes:
            archive.writestr(files[note.pk], markdown(note, paths, files))
    return attachment(output.getvalue(), filename(notebook.name, notebook.pk) + '.zip', 'application/zip')
