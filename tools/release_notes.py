#!/usr/bin/env python3
"""Les notes d'une version, tirees de CHANGELOG.md, pour la publication.

    release_notes.py 0.6.8 > dist/RELEASE_NOTES.md

Prend la section "## [0.6.8]" du CHANGELOG (ou "## Unreleased" si le numero
n'y est pas encore), et y ajoute les disquettes 6502 par categorie et les deux XL."""
import re
import sys
from disk_packages import ROOT, assignments

FILES = """
### Files

| Image | Contents |
|---|---|
| `A2FILECMD-6502-BOOT-{version}.dsk` | Bootable 140 KB file manager and essential tools |
| `A2FILECMD-6502-FILES-{version}.dsk` | Documents, search, archives, file operations |
| `A2FILECMD-6502-MEDIA-{version}.dsk` | Pictures and music |
| `A2FILECMD-6502-DISKTOOLS-{version}.dsk` | Disk images, blocks, boot repair and recovery |
| `A2FILECMD-6502-DEVTOOLS-{version}.dsk` | BASIC listings, disassembly and BASIC.SYSTEM |
| `A2FILECMD-6502-XL-{version}.2mg` | Complete bootable 32 MB image, 6502 |
| `A2FILECMD-65C02-XL-{version}.2mg` | Complete bootable 32 MB image, 65C02 with optional mouse |

The concise English user guide is included as `A2FILECMD-MANUAL-EN-{version}.pdf`, with a screenshot of both panels, clickable contents and bookmarks.

All floppies use 6502 code and also run on enhanced machines. Choose the
categories you need, from the same release as BOOT. Each carries MENU and
the full command catalog. XL includes all {overlays} overlays, BASIC.SYSTEM, DEMO
and IMGHGR; it needs no companion. Choose XL 6502 for an original IIe, or
XL 65C02 for an enhanced IIe or //c. All editions need 128 KB and 80 columns.
Do not mix native plugins from XL 65C02 with the 6502 companions.

Boot an image and press **?** for the key map; `sha256sum -c SHA256SUMS-{version}.txt`
checks the download. The bootable images carry ProDOS 8 2.4.3; the `.2mg` and DEVTOOLS carry
BASIC.SYSTEM (John Brooks' free distribution; they are Apple's). Sources,
manual and benches:
<https://github.com/habib256/a2filecmd>.
"""


def build_version():
    return re.search(r'^A2FC_VERSION\s*=\s*(\S+)', (ROOT / 'Makefile').read_text(), re.M)[1]


def check_tag(tag):
    expected = 'v' + build_version()
    if tag != expected:
        raise ValueError('Release tag %s does not match build version %s' % (tag, expected))


def overlay_count():
    native = re.search(r'^PLUGINS = (.+)$', (ROOT / 'Makefile').read_text(), re.M)[1].split()
    plugins = [p.stem for p in (ROOT / 'src/plugins').glob('*.c')]
    return len(assignments(native, plugins))


def main():
    """Le premier argument est le nom de la reference : "v0.6.8" sur un tag,
    "main" sur un push de branche -- seul un vrai numero choisit une
    section ; sinon on prend l'inedit, ou a defaut la derniere version
    publiee, pour que l'artefact de construction porte quand meme des
    notes lisibles."""
    if len(sys.argv) > 1 and sys.argv[1] == '--check-tag':
        if len(sys.argv) != 3:
            sys.stderr.write('Usage: release_notes.py --check-tag vVERSION\n')
            return 1
        try:
            check_tag(sys.argv[2])
        except ValueError as error:
            sys.stderr.write(str(error) + '\n')
            return 1
        return 0
    ref = sys.argv[1].removeprefix('v') if len(sys.argv) > 1 else ''
    version = ref if re.fullmatch(r'\d+(\.\d+)*', ref) else ''
    text = (ROOT / 'CHANGELOG.md').read_text()
    m = re.search(r'^## \[%s\][^\n]*\n(.*?)(?=^## |\Z)' % re.escape(version), text, re.S | re.M) if version else None
    if not m:
        m = re.search(r'^## Unreleased\n(.*?)(?=^## |\Z)', text, re.S | re.M)
    if not m or not m.group(1).strip():
        m = re.search(r'^## \[([^\]]+)\][^\n]*\n(.*?)(?=^## |\Z)', text, re.S | re.M)
        body = m.group(2) if m and m.lastindex == 2 else (m.group(1) if m else '')
    else:
        body = m.group(1)
    body = body.strip().replace('[Full changelog]', '\n[Full changelog]')
    if not version:
        version = build_version()
    title = 'A2 File Cmd %s' % version if version else 'A2 File Cmd'
    sys.stdout.write('## %s — *Two panels. One Apple II.*\n\n%s\n%s' % (title, body, FILES.replace('{version}', version).replace('{overlays}', str(overlay_count()))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
