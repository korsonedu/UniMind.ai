import re
from .models import Note, NoteLink

# Stable IDs survive renaming and notebook moves. Ignore links to other owners.
NOTE_LINK = re.compile(r'(?<=\]\()(?:/notes/|note:)(\d+)(?=\))')


def index_links(note):
    targets = Note.objects.filter(user=note.user, id__in=set(NOTE_LINK.findall(note.content)))
    NoteLink.objects.filter(source=note).delete()
    NoteLink.objects.bulk_create([NoteLink(source=note, target=target) for target in targets])
