#!/usr/bin/env python3
"""R restarts BASLIST and AppleWorks readers after paging."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, ok_all, RET, ESC
import mkawp, mkdemo

_AWP_TMP = Path(tempfile.gettempdir()) / 'a2fc-restart-readers.awp'
mkawp.write_awp(_AWP_TMP, 'Page one text.\n\n' + ('A long AppleWorks paragraph. ' * 80))
AWP = _AWP_TMP.read_bytes()
BAS = mkdemo.applesoft([(10, bytes([mkdemo.PRINT]) + b'"FIRST"'),
                        (20, bytes([mkdemo.PRINT]) + b'"' + b'X' * 180 + b'"'),
                        (30, bytes([mkdemo.END]))])


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-restart-readers-') as tmp:
        files = {'WORK/NOTE.AWP#1A0000': AWP, 'WORK/HELLO#FC0801': BAS}
        with boot_hd(Path(tmp), files, port=6822) as (p, s):
            s.select('WORK'); s.key(RET); s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()
            s.select('HELLO'); s.key(b'T'); s.wait(lambda: s.value('view', 1) == 2, 'BASLIST'); p.stable()
            s.ok('BASLIST explique R', s.has('R First'))
            s.key(b' '); p.stable(); s.key(b'R'); p.stable()
            s.ok('BASLIST R revient au debut', s.has('10 '), '\n'.join(s.rows()[:3]))
            s.key(ESC); s.wait(lambda: s.has('Type  Aux     Size'), 'panneaux BAS'); p.stable()
            s.select('NOTE.AWP'); s.key(b'T'); s.wait(lambda: s.value('view', 1) == 2, 'AWP'); p.stable()
            s.ok('AppleWorks explique R', s.has('R First'))
            s.key(b' '); p.stable(); s.key(b'R'); p.stable()
            s.ok('AppleWorks R revient au debut', s.has('Page one text'), '\n'.join(s.rows()[:3]))
            s.key(ESC); s.wait(lambda: s.has('Type  Aux     Size'), 'panneaux AWP'); p.stable()
    return ok_all(s, 'restart-readers')


if __name__ == '__main__':
    sys.exit(main())
