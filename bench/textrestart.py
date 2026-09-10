#!/usr/bin/env python3
"""TEXT viewer restart key and bounded navigation."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, ok_all, RET, ESC

DATA = b''.join((b'line %02d\r' % (i + 1)) for i in range(70))


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-textrestart-') as tmp:
        with boot_hd(Path(tmp), {'WORK/LONG.TXT': DATA}, port=6820) as (p, s):
            s.select('WORK'); s.key(RET); s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()
            s.select('LONG'); s.key(b'T'); s.wait(lambda: s.has('page 1'), 'TEXT page 1'); p.stable()
            s.ok('TEXT affiche la premiere page', s.rows()[1].startswith('line 02'), '\n'.join(s.rows()[:3]))
            s.key(b' '); s.wait(lambda: s.has('page 2'), 'TEXT page 2'); p.stable()
            s.ok('Espace avance dans TEXT', s.rows()[1].startswith('line 24'), '\n'.join(s.rows()[:3]))
            s.key(b' '); s.wait(lambda: s.has('page 3'), 'TEXT page 3'); p.stable()
            s.key(b'R'); s.wait(lambda: s.has('page 1'), 'TEXT restart'); p.stable()
            s.ok('R revient directement a la premiere page', s.rows()[1].startswith('line 02'), '\n'.join(s.rows()[:3]))
            s.key(b'B'); p.stable()
            s.ok('Retour en debut reste borne', s.rows()[1].startswith('line 02'), '\n'.join(s.rows()[:3]))
            s.key(ESC); s.wait(lambda: s.has('Type  Aux     Size'), 'panneaux'); p.stable()
            s.ok('selection conservee', s.line(0).startswith('LONG '))
    return ok_all(s, 'textrestart')


if __name__ == '__main__':
    sys.exit(main())
