#!/usr/bin/env python3
"""GOTO.CFG edited on a host: mixed CR/LF/CRLF, blanks and final unterminated line.
Run for each CPU as with goto.py. The ordinary save must remain readable.
"""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, menu_run, ok_all, ESC

TITLE = 'GOTO -- favourite directories'
PATHS = ['/WORKHD/DIR%d' % i for i in range(1, 10)]
CONFIG = b'\r\n\n' + b''.join(p.encode() + (b'\r', b'\n', b'\r\n')[i % 3] + b'\n'
                              for i, p in enumerate(PATHS[:-1])) + PATHS[-1].encode()
FILES = {'A2FILE/GOTO.CFG#040000': CONFIG}
FILES.update({'DIR%d/HELLO.TXT' % i: b'hello\r' for i in range(1, 10)})


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-gotocfg-') as tmp:
        with boot_hd(Path(tmp), FILES, port=6814, plugins=['goto']) as (p, s):
            def show():
                menu_run(s, p, 'GOTO')
                s.wait(lambda: s.has(TITLE), 'GOTO'); p.stable()
                return [r.strip() for r in s.rows()[2:14] if r.strip()[:1].isdigit()]

            def leave(key):
                s.key(key)
                s.wait(lambda: not s.has(TITLE), 'panels'); p.stable()

            rows = show()
            s.ok('CR/LF/CRLF et lignes vides : neuf favoris exacts',
                 len(rows) == 9 and all(r.endswith(path) for r, path in zip(rows, PATHS)), rows)
            leave(ESC)
            for digit in (1, 2, 3, 9):
                show(); leave(str(digit).encode())
                s.ok('saut %d sans caractere de fin de ligne parasite' % digit,
                     s.rows()[0].startswith(PATHS[digit - 1] + ' '), s.rows()[0].strip())
            show(); s.key(b'D'); s.wait(lambda: s.has('Delete which'), 'delete choice')
            leave(b'2')
            rows = show()
            expected = PATHS[:1] + PATHS[2:]
            s.ok('suppression puis relecture : huit favoris intacts',
                 len(rows) == 8 and all(r.endswith(path) for r, path in zip(rows, expected)), rows)
            leave(b'8')
            s.ok('dernier favori sans saut final conserve apres sauvegarde',
                 s.rows()[0].startswith(PATHS[-1] + ' '))
    return ok_all(s, 'gotocfg')


if __name__ == '__main__':
    sys.exit(main())
