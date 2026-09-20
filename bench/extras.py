#!/usr/bin/env python3
"""Published 140K essentials and complete 800K: boot, menus and missing tools."""
import re
import shutil
import sys
import tempfile
from pathlib import Path
from pom2 import VERSION, Pom2, Session, ROOT, BUILD
from smoke import scratch
from xplug import menu_inventory, menu_run, ok_all, RET, ESC
sys.path.insert(0, str(ROOT / 'tools'))
from distribution import image_name, inventories
from check_images import check_cpu


def check_menu(s, p, expected):
    hidden = set(re.search(r'mn_hidden\[\] = "([^"\n]+)"', (ROOT / 'src/a2fc.c').read_text())[1].strip('|').split('|'))
    s.key(b'!'); s.wait(lambda: s.has('the overlays'), 'menu', 30); p.stable()
    names = set(menu_inventory(s, p))
    s.ok('menu lists exactly the tools available on this image', names == expected - hidden,
         sorted(names ^ (expected - hidden)))
    s.key(ESC)


def main():
    check_cpu('6502')
    essential, complete = inventories()
    with tempfile.TemporaryDirectory(prefix='a2fc-distribution-') as directory:
        tmp = Path(directory)
        floppy = tmp / 'essential.po'
        shutil.copyfile(ROOT / 'dist' / image_name('140K').replace('.dsk', '.po'), floppy)
        with Pom2(scratch(tmp), floppy=floppy, port=6830) as p:
            s = Session(p); s.boot()
            check_menu(s, p, essential)
            s.key(b'/'); s.select('/SCRATCH'); s.key(RET)
            s.select('WORK'); s.key(RET); s.select('NOTE'); p.stable()
            s.key(b'E'); s.wait(lambda: s.value('view', 1) == 5 and s.has('cratch volume'), 'essential editor', 30)
            s.ok('the essential disk includes the text editor', True)
            s.key(ESC); p.stable()
            if not s.has('Type  Aux'): s.key(b'Q')
            s.wait(lambda: s.has('Type  Aux'), 'panels', 30)
            s.key(b'W'); s.wait(lambda: s.has('DISKIMG.PLG is missing or stale'), 'unavailable command returns immediately', 30)
            s.ok('no obsolete companion request for an unavailable tool', not s.has('Insert '))
            s.key(b'T'); s.wait(lambda: s.has('scratch volume'), 'text reader after refusal', 30)
            s.ok('normal commands still work after an unavailable tool', True)
            s.key(ESC)
        first = ok_all(s, '140K essentials')
    with tempfile.TemporaryDirectory(prefix='a2fc-800k-') as directory:
        tmp = Path(directory)
        hd = tmp / 'complete800.po'
        shutil.copyfile(ROOT / 'dist' / image_name('800K'), hd)
        # Boot the published block image through the emulator's block device.
        # This checks ProDOS boot/content, not a physical 3.5-inch drive.
        with Pom2(hd, port=6831, boot=5) as p:
            s = Session(p); s.boot()
            s.ok('800K boots as a self-contained ProDOS volume', s.rows()[0].startswith('/A28006502'))
            check_menu(s, p, complete)
            s.select('A2FILE'); s.key(RET); s.select('A2FILE.HELP'); s.key(b'T')
            s.wait(lambda: s.value('view', 1) == 2, '800K text reader', 30)
            s.ok('800K loads its reader without a companion disk', True)
            s.key(ESC)
        second = ok_all(s, '800K complete')
    return first or second


if __name__ == '__main__':
    raise SystemExit(main())
