#!/usr/bin/env python3
"""New MAIN-only readers on a disposable ProDOS disk, either CPU."""
import sys
import tempfile
from pathlib import Path
from xplug import boot_hd, menu_run, RET, ESC, ok_all
from pom2 import ROOT
sys.path.insert(0, str(ROOT / 'tools'))
from test_retrotext import pascal, sc_line, lisa
from test_fontrix import fixture


def main():
    high = lambda b: bytes(c | 128 for c in b)
    samples = {
        'PASTEXT': (pascal(b'PASCAL FIRST\r'*21 + b'PASCAL SECOND\r'), 'PASCAL FIRST'),
        'SCASM': (sc_line(100, b'\x89LDA\x83#0'), '0100          LDA   #0'),
        'MERLIN': (high(b'LABEL LDA #$20 ;note\r'), 'LABEL    LDA   #$20'),
        'LISAV2': (lisa(b' \xa0\0\r'), 'NOP'),
        'GUTTEXT': (high(b'GUTENBERG\r') + b'\0', 'GUTENBERG'),
        'TEACHTXT': (b'Teach text\r\x80', 'Teach text'),
        'FONTRIX': (fixture(height=32), 'Fontrix: A ($41)'),
    }
    files = {'WORK/' + name + '#040000': data for name, (data, _) in samples.items()}
    files['WORK/BAD.LISA#040000'] = samples['LISAV2'][0][:-1]
    with tempfile.TemporaryDirectory(prefix='legacy-native-') as tmp:
        with boot_hd(Path(tmp), files, port=6918, plugins=[n.lower() for n in samples]) as (p, s):
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            before = p.peek(0x1000, 0xb000, 'aux')
            floor = s.sym['__HIMEM__'] - s.sym['__STACKSIZE__']
            p.poke(floor, b'\xa5'*8)
            for name, (_, expected) in samples.items():
                s.select(name);menu_run(s, p, name)
                s.wait(lambda: s.has(expected), name + ' visible', 30)
                s.ok(name + ' decoded display', True)
                if name == 'PASTEXT':
                    s.key(b' ');s.wait(lambda: s.has('PASCAL SECOND'), 'Pascal second page', 10)
                    s.ok('Pascal paging', True)
                if name == 'FONTRIX':
                    s.key(b'\x15');s.wait(lambda: s.has('Fontrix: B ($42)'), 'Fontrix next', 10)
                    s.ok('Fontrix next glyph', True)
                s.key(ESC);s.wait(lambda: s.has('Type  Aux'), name + ' exit', 30);p.stable()
            s.select('BAD.LISA');menu_run(s, p, 'LISAV2')
            s.wait(lambda: s.has('Malformed LISA v2 file.'), 'bad LISA rejected', 30)
            s.ok('AUX unchanged by all readers', p.peek(0x1000, 0xb000, 'aux') == before)
            s.ok('C-stack floor unchanged', p.peek(floor, 8) == b'\xa5'*8)
    return ok_all(s, 'retrotext')


if __name__ == '__main__':
    raise SystemExit(main())
