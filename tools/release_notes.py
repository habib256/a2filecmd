#!/usr/bin/env python3
"""Les notes d'une version, tirees de CHANGELOG.md, pour la publication.

    release_notes.py 0.6.8 > dist/RELEASE_NOTES.md

Prend la section "## [0.6.8]" du CHANGELOG (ou "## Unreleased" si le numero
n'y est pas encore), et y ajoute le tableau des deux editions : la
disquette (6502, le gestionnaire et les outils disque) et le disque dur
(65C02, tout)."""
import re
import sys
from pathlib import Path

FILES = """
### Files

| | Contents | Runs on |
|---|---|---|
| `A2FILECMD-6502.po` — bootable 140 KB floppy, ProDOS order | **Floppy edition**, 6502 build: the file manager and the disk tools | Any Apple II with 128 KB and 80 columns, the 1983 IIe included; keyboard only |
| `A2FILECMD-6502.dsk` — the same floppy, `.dsk` (DOS-order) layout | The same | The same |
| `A2FILECMDXL-65C02.2mg` — 32 MB hard disk | **Complete edition**, 65C02 build: every tool, `DEMO/`, `IMGHGR/`, BASIC.SYSTEM | Enhanced IIe, //c, IIgs; mouse optional |
| `A2FILECMD-EXTRAS.po` — non-bootable 140 KB companion | 17 extra tools and BASIC.SYSTEM; slot 6 drive 2, or prompted swaps in drive 1 | Same machines as the 6502 floppy |

Boot an image and press **?** for the key map; `sha256sum -c SHA256SUMS.txt`
checks the download. The bootable images carry ProDOS 8 2.4.3; the `.2mg` and companion carry
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
    sys.stdout.write('## %s — *Two panels. One Apple II.*\n\n%s\n%s' % (title, body, FILES))
    return 0


if __name__ == '__main__':
    sys.exit(main())
