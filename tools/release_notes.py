#!/usr/bin/env python3
"""Les notes d'une version, tirees de CHANGELOG.md, pour la publication.

    release_notes.py 0.6.8 > dist/RELEASE_NOTES.md

Prend la section "## [0.6.8]" du CHANGELOG (ou "## Unreleased" si le numero
n'y est pas encore), et y ajoute les cinq images autonomes."""
import re
import sys
from distribution import ROOT, inventories

FILES = """
### Files

| Image | Contents |
|---|---|
| `A2FILECMD-PRODOS-XL-{version}.2mg` | Complete bootable 32 MB image, 6502, with demonstration files |
| `A2FILECMD-PRODOS-XL-65C02-enhanced-{version}.2mg` | Complete 32 MB image for an enhanced IIe, //c or IIgs: MouseText, optional mouse |
| `A2FILECMD-DOS3.3-{version}.dsk` | Standalone DOS 3.3 edition for Apple II+ 48 KB, 40 columns, two drives |
| `A2FILECMD-PRODOS-800K-{version}.po` | Bootable 800 KB ProDOS image, 6502, all tools and BASIC runtimes, no demo corpus |
| `A2FILECMD-PRODOS-140K-{version}.dsk` | Bootable 5.25-inch ProDOS disk, 6502, essential file operations, text editor, text/hex readers, format and verify |

The English user guide is included as `A2FILECMD-MANUAL-EN-{version}.pdf`.

XL includes all {overlays} overlays, BASIC.SYSTEM, INTBASIC.SYSTEM and a DEMO
folder sorted by kind of file. The 800K edition has the same tools without the demonstration
corpus. The 140K edition is self-contained; its menu lists available tools,
without asking for the former FILES/MEDIA/DISKTOOLS/DEVTOOLS disks.
All ProDOS editions need 128 KB and 80 columns. The choice is enhanced or
not: the enhanced XL is for an enhanced IIe, a //c or a IIgs; every other
ProDOS image runs on any IIe. Mini is a separate DOS 3.3 program for the 48 KB Apple II+.

Boot an image and press **?** for help. `sha256sum -c SHA256SUMS-{version}.txt`
checks the five images and manual. ProDOS images carry ProDOS 8 2.4.3.
XL and 800K include BASIC.SYSTEM (John Brooks' free distribution; Apple's
software) and INTBASIC.SYSTEM v0.9 by Joshua Bell
(<https://github.com/a2stuff/intbasic>).
Sources, manual and benches: <https://github.com/habib256/a2filecmd>.
"""


def build_version():
    return re.search(r'^A2FC_VERSION\s*=\s*(\S+)', (ROOT / 'Makefile').read_text(), re.M)[1]


def check_tag(tag):
    expected = 'v' + build_version()
    if tag != expected:
        raise ValueError('Release tag %s does not match build version %s' % (tag, expected))


def overlay_count():
    return len(inventories()[1])


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
        m = re.search(r'^## \[?Unreleased\]?\n(.*?)(?=^## |\Z)', text, re.S | re.M)
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
