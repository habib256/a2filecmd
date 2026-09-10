#!/usr/bin/env python3
"""Banc de la surcouche IDENT (src/plugins/ident.c) : dire ce qu'est un
fichier d'apres son contenu, comme file(1).

    make build/ident.PLG && A2FC_IMG=A2FILECMD-full python3 bench/ident.py

Les specimens sont sur le disque dur du banc, /WORKHD/WORK, fabriques par
les memes outils que la demonstration : une archive ShrinkIt (mkshk), une
Binary II (mkbny), un document AppleWorks (mkawp), un Applesoft tokenise
(mkdemo, sous son type $FC et sous $06 pour l'heuristique), une page HGR de
8 192 octets et une DHGR de 16 384, une fanfare MB1, une image ProDOS de
140 Ko (mkvolume), la meme en 2IMG (po22mg), une disquette DOS 3.3
(mkdos33), des textes CR, LF
avec UTF-8 et tabulations, CRLF, a bit haut, un long au-dela de 512 octets,
un binaire aleatoire et un binaire avec un JMP. IDENT tourne sur chacun et
la ligne 22 est comparee au mot attendu, connu par construction. Un
dossier est refuse."""
import random
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, RET
from pom2 import ROOT
import mkawp
import mkbny
import mkdemo
import mkdos33
import mkshk
import po22mg

PORT = 6809

CR = b''.join(b'line %d of a CR text\r' % i for i in range(1, 8))                 # 7 lines
LF = b''.join(b'ligne %d\tcaf\xc3\xa9\n' % i for i in range(1, 12))               # 11 lines, tabs, UTF-8
CRLF = b''.join(b'row %d\r\n' % i for i in range(1, 6))                           # 5 lines
HI = bytes(c | 0x80 for c in b'HELLO WORLD\rSECOND LINE\r')                       # Apple text, 2 lines
LONG = b'0123456789012345678\r' * 40                                              # 800 bytes: 25 lines in the first 512
CODE = b'\x4c\x00\x20' + b'\xea' * 29                                             # JMP $2000, a BIN at $2000
_RNG = random.Random(6809)                                                        # une seule graine : sinon 700 fois le meme octet
RANDOM = bytes(_RNG.getrandbits(8) for _ in range(700))
assert min(RANDOM[:512]) < 9, 'le binaire doit tenir un octet de commande'        # sinon IDENT y verrait du texte


UTF_CASES = {
    'EURO': ('prix 10 €\n'.encode(), 'Text (UTF-8), LF ends, 1 lines in 12 B'),
    'CJK': ('漢字\r\n'.encode(), 'Text (UTF-8), CRLF ends, 1 lines in 8 B'),
    'EMOJI': ('hello 😀\n'.encode(), 'Text (UTF-8), LF ends, 1 lines in 11 B'),
    'BOM': (b'\xef\xbb\xbfhello\n', 'Text (UTF-8), LF ends, 1 lines in 9 B'),
    'NONASCII': ('é漢😀'.encode(), 'Text (UTF-8), no ends, 0 lines in 9 B'),
    'CRUNICODE': ('a\ré\nb'.encode(), 'Text (UTF-8), mixed ends, 2 lines in 6 B'),
    'CUT': (b'a' * 511 + '😀'.encode(), 'Text (UTF-8), no ends, 0 lines in 512 B'),
    'OVERLONG': (b'a\xe0\x80\x80', 'Binary data'),
    'SURROGATE': (b'a\xed\xa0\x80', 'Binary data'),
    'TOOHIGH': (b'a\xf4\x90\x80\x80', 'Binary data'),
    'TRUNCATED': (b'a\xf0\x9f', 'Binary data'),
    'BADCONT': (b'a\xe2\x82x', 'Binary data'),
    'CONTROL': ('漢'.encode() + b'\x01', 'Binary data'),
}


def specimens(tmp):
    """{chemin ProDOS: octets} des fichiers a poser dans WORK/."""
    sample = b'hello from the archive\r' * 8
    hello = mkdemo.applesoft([
        (10, bytes([mkdemo.HOME])),
        (20, bytes([mkdemo.PRINT]) + b'"IDENT"'),
        (30, bytes([mkdemo.END])),
    ])
    inside = [{'name': 'SAMPLE', 'data': sample, 'filetype': 0x04},
              {'name': 'HELLO', 'data': hello, 'filetype': 0xFC, 'auxtype': 0x0801}]
    mkshk.write_shk(tmp / 'S.SHK', inside)
    mkbny.write_bny(tmp / 'S.BNY', inside)
    mkawp.write_awp(tmp / 'L.AWP', 'A letter written for AppleWorks.\n\nWith two paragraphs.')
    tiny = tmp / 'tiny'
    tiny.mkdir()
    (tiny / 'HELLO.TXT').write_bytes(b'hello from inside a disk image\r' * 4)
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(tiny), str(tmp / 'TINY.PO'),
                    '--volume', 'TINY', '--blocks', '280'], check=True, capture_output=True)
    po = (tmp / 'TINY.PO').read_bytes()
    dsk = mkdos33.build([('GREETINGS', 0x00, b'HELLO FROM A DOS 3.3 DISK\r' * 4 + b'\x00')])
    assert len(po) == 143360 and len(dsk) == 143360
    return {
        'WORK/SAMPLE.SHK#E08002': (tmp / 'S.SHK').read_bytes(),
        'WORK/SAMPLE.BNY#E08000': (tmp / 'S.BNY').read_bytes(),
        'WORK/LETTER#1A0000': (tmp / 'L.AWP').read_bytes(),
        'WORK/HELLO#FC0801': hello,
        'WORK/HELLO2.BIN': hello,                 # the same bytes as a BIN: the heuristic alone
        'WORK/HGR.BIN': mkdemo.hgr_card(),        # 8,192 bytes
        'WORK/DHGR.BIN': mkdemo.dhgr_card(),      # 16,384 bytes : les deux plans
        'WORK/WELCOME.MB.BIN': mkdemo.fanfare(),
        'WORK/TINY.PO': po,
        'WORK/TINY.2MG': po22mg.to_2mg(po),
        'WORK/DOS33.DSK': dsk,
        'WORK/CR.TXT': CR,
        'WORK/LF.TXT': LF,
        'WORK/CRLF.TXT': CRLF,
        'WORK/HI.TXT': HI,
        'WORK/LONG.TXT': LONG,
        'WORK/CODE#062000': CODE,
        'WORK/RANDOM.BIN': RANDOM,
    }


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-ident-') as tmp:
        tmp = Path(tmp)
        files = specimens(tmp)
        files.update({'WORK/' + name + '#040000': data for name, (data, _) in UTF_CASES.items()})
        size = {rel.split('/')[1].split('#')[0]: len(data) for rel, data in files.items()}
        for host in list(size):
            for suf in ('.TXT', '.BIN'):
                if host.endswith(suf):
                    size[host[:-len(suf)]] = size.pop(host)

        def expect(name, what):
            return '%s (%d bytes): %s' % (name, size[name], what)

        cases = [
            ('SAMPLE.SHK', expect('SAMPLE.SHK', 'ShrinkIt archive (NuFX)')),
            ('SAMPLE.BNY', expect('SAMPLE.BNY', 'Binary II archive')),
            ('LETTER', expect('LETTER', 'AppleWorks word processor')),
            ('HELLO', expect('HELLO', 'Applesoft BASIC program')),
            ('HELLO2', expect('HELLO2', 'Applesoft BASIC program')),
            ('HGR', expect('HGR', 'HGR picture, 8K')),
            ('DHGR', expect('DHGR', 'DHGR picture, 16K (two planes)')),
            ('WELCOME.MB', expect('WELCOME.MB', 'Mockingboard music (MB1)')),
            ('TINY.PO', expect('TINY.PO', 'ProDOS disk image, 140K')),
            ('TINY.2MG', expect('TINY.2MG', '2IMG disk image')),
            ('DOS33.DSK', expect('DOS33.DSK', 'DOS 3.3 disk image, 140K')),
            ('CR', expect('CR', 'Text, CR ends, high bit clear, %d lines in %d B' % (CR.count(b'\r'), len(CR)))),
            ('LF', expect('LF', 'Text (UTF-8), LF ends, %d lines in %d B, tabs' % (LF.count(b'\n'), len(LF)))),
            ('CRLF', expect('CRLF', 'Text, CRLF ends, high bit clear, %d lines in %d B' % (CRLF.count(b'\r\n'), len(CRLF)))),
            ('HI', expect('HI', 'Text, CR ends, high bit set, %d lines in %d B' % (HI.count(b'\x8d'), len(HI)))),
            ('LONG', expect('LONG', 'Text, CR ends, high bit clear, %d lines in 512 B' % LONG[:512].count(b'\r'))),
            ('CODE', expect('CODE', 'Binary, maybe 6502 code')),
            ('RANDOM', expect('RANDOM', 'Binary data')),
        ]
        cases.extend((name, expect(name, what)) for name, (_, what) in UTF_CASES.items())
        with boot_hd(tmp, files, port=PORT, plugins=['ident']) as (p, s):
            # 1. A directory is refused: WORK, at the root of the boot volume.
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/WORKHD'); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD '), 'la racine'); p.stable()
            s.select('WORK'); p.stable()
            menu_run(s, p, 'IDENT')
            s.wait(lambda: s.has('Select a file'), 'le refus du dossier', 20); p.stable()
            s.ok('refuse un dossier', s.rows()[22].strip() == 'Select a file in a ProDOS directory.',
                 s.rows()[22].strip())

            # 2. Each specimen in WORK.
            s.key(RET); s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()
            for name, want in cases:
                s.select(name, 0); p.stable()
                menu_run(s, p, 'IDENT')
                s.wait(lambda: s.has(name + ' ('), 'la ligne de IDENT sur ' + name, 30); p.stable()
                got = s.rows()[22].strip()
                s.ok(want, got == want, got if got != want else '')
            s.ok('le curseur est reste sur le dernier specimen', s.line(0).startswith(cases[-1][0] + ' '), s.line(0))
    return ok_all(s, 'ident')


if __name__ == '__main__':
    sys.exit(main())
