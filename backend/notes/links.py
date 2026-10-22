import re
from .models import Note, NoteLink

# Stable IDs survive renaming and notebook moves. Ignore links to other owners.
NOTE_LINK = re.compile(r'(?<=\]\()(?:/notes/|note:)(\d+)(?=\))')
CODE_SPAN = re.compile(r'(?<!`)(`+)(?!`)[\s\S]*?(?<!`)\1(?!`)')
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')
LIST_ITEM = re.compile(r'^ *(?:[-+*]|[0-9]{1,9}[.)])(?: +|$)')


def note_links(content):
    """Find actual note hrefs, leaving ordinary Markdown code examples alone."""
    fence = None
    list_indents = []
    prose, masked = [], []

    def flush_prose():
        text = ''.join(prose)
        masked.append(CODE_SPAN.sub(lambda match: ' ' * len(match.group()), text))
        prose.clear()

    for line in content.splitlines(keepends=True):
        expanded = line.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip(' '))
        if fence is None and expanded.strip():
            while list_indents and indent < list_indents[-1]:
                list_indents.pop()
        base = list_indents[-1] if list_indents else 0
        code = fence is not None or indent >= base + 4
        if not code:
            item = LIST_ITEM.match(expanded)
            if item:
                base = item.end()
                list_indents.append(base)
        marker = FENCE.match(expanded[base:].rstrip('\r\n'))
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker and (marker[1][0] != '`' or '`' not in marker[2]):
            fence = marker[1]
            code = True
        if code:
            flush_prose()
            masked.append(' ' * len(line))
        else:
            prose.append(line)
    flush_prose()
    yield from NOTE_LINK.finditer(''.join(masked))


def rewrite_note_links(content, replace):
    parts, start = [], 0
    for match in note_links(content):
        parts.extend([content[start:match.start()], replace(match)])
        start = match.end()
    return ''.join(parts) + content[start:]


def index_links(note):
    targets = Note.objects.filter(user=note.user, id__in={match[1] for match in note_links(note.content)})
    NoteLink.objects.filter(source=note).delete()
    NoteLink.objects.bulk_create([NoteLink(source=note, target=target) for target in targets])
