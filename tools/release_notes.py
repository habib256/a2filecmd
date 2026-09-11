#!/usr/bin/env python3
"""Les notes d'une version, tirees de CHANGELOG.md, pour la publication.

    release_notes.py 0.6.8 > dist/RELEASE_NOTES.md

Prend la section "## [0.6.8]" du CHANGELOG (ou "## Unreleased" si le numero
n'y est pas encore), et y ajoute les quatre supports (BOOT, EXTRA, EXTRA2
et XL) de chaque processeur."""
import re
import sys
from pathlib import Path

FILES = """
### Files

| CPU | BOOT: 140 KB, bootable | EXTRA: 140 KB, companion | EXTRA2: 140 KB, disk tools | XL: 32 MB, complete |
|---|---|---|---|---|
| 6502 | `A2FILECMD-6502-BOOT-{version}.dsk` | `A2FILECMD-6502-EXTRA-{version}.dsk` | `A2FILECMD-6502-EXTRA2-{version}.dsk` | `A2FILECMD-6502-XL-{version}.2mg` |
| 65C02 | `A2FILECMD-65C02-BOOT-{version}.dsk` | `A2FILECMD-65C02-EXTRA-{version}.dsk` | `A2FILECMD-65C02-EXTRA2-{version}.dsk` | `A2FILECMD-65C02-XL-{version}.2mg` |

The concise English user guide is included as `A2FILECMD-MANUAL-EN-{version}.pdf`, with a screenshot of both panels, clickable contents and bookmarks.

Choose the same CPU and release for every disk. BOOT has 19 overlays; EXTRA
and EXTRA2 carry the 32 absent from it, EXTRA the everyday tools and
BASIC.SYSTEM, EXTRA2 the disk and block surgery (BLKVIEW, BLKEDIT, DISASM,
SYNC, MOVE, DISKCMP, UNDELETE, RESCUE, TREE, MKIMAGE). XL has all 51
overlays, BASIC.SYSTEM, DEMO and IMGHGR, and needs neither companion.
The 6502 versions run on an Apple II with 128 KB and 80 columns, including
the original IIe. The 65C02 versions support enhanced IIe, //c and IIgs,
with optional mouse.

Boot an image and press **?** for the key map; `sha256sum -c SHA256SUMS-{version}.txt`
checks the download. The bootable images carry ProDOS 8 2.4.3; the `.2mg` and EXTRA carry
BASIC.SYSTEM (John Brooks' free distribution; they are Apple's). Sources,
manual and benches:
<https://github.com/habib256/a2filecmd>.
"""


def main():
    """Le premier argument est le nom de la reference : "v0.6.8" sur un tag,
    "main" sur un push de branche -- seul un vrai numero choisit une
    section ; sinon on prend l'inedit, ou a defaut la derniere version
    publiee, pour que l'artefact de construction porte quand meme des
    notes lisibles."""
    ref = sys.argv[1].lstrip('v') if len(sys.argv) > 1 else ''
    version = ref if re.fullmatch(r'\d+(\.\d+)*', ref) else ''
    text = Path(__file__).resolve().parents[1].joinpath('CHANGELOG.md').read_text()
    m = re.search(r'^## \[%s\][^\n]*\n(.*?)(?=^## |\Z)' % re.escape(version), text, re.S | re.M) if version else None
    if not m:
        m = re.search(r'^## Unreleased\n(.*?)(?=^## |\Z)', text, re.S | re.M)
    if not m or not m.group(1).strip():
        m = re.search(r'^## \[([^\]]+)\][^\n]*\n(.*?)(?=^## |\Z)', text, re.S | re.M)
        if m and not version:
            version = m.group(1)
        body = m.group(2) if m and m.lastindex == 2 else (m.group(1) if m else '')
    else:
        body = m.group(1)
    body = body.strip().replace('[Full changelog]', '\n[Full changelog]')
    title = 'A2 File Cmd %s' % version if version else 'A2 File Cmd'
    sys.stdout.write('## %s — *Two panels. One Apple II.*\n\n%s\n%s' % (title, body, FILES.replace('{version}', version)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
