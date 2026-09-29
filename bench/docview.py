#!/usr/bin/env python3
"""Banc de la surcouche DOCVIEW (src/plugins/docview.c) : documents Epistole,
Papyrus et HomeWord mis en page comme a l'impression.

    make all disk && A2FC_IMG=A2FILECMD-full python3 bench/docview.py

tools/test_docview.py fait tourner le rendu sur l'hote ; ce banc fait tourner
la surcouche livree, ouverte par Retour (un texte qui commence par une
commande _ ou un code $FF) : marges, retrait, variable en inverse, accents
ISO 646-FR montres sans accent puis tels quels avec A, titre Papyrus
centre, pages, Echap vers les panneaux. Les documents sont ecrits ici,
dans la syntaxe relevee sur les disques d'Epistole et de Papyrus."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, ok_all, RET, ESC

PORT = 6862
HI = lambda t: bytes(c | 0x80 for c in t)
LETTRE = (b'_MG10_MD65_JD\r\r_MI30#NOM]\r_MI0\r\r'
          b'Ceci est une lettre type : vous d{sirez rentrer vous m{me les variables.\r'
          b'_CE TITRE CENTRE\r_PC\r' + b''.join(b'Ligne %d du document.\r' % i for i in range(40)))
# Calculations on the ROM's arithmetic, as Epistole prints them: a decimal
# tab (comma at margin 10 + 38), a division by zero left as written, the
# total carried to the second page.
FACTURE = (b'_MG10_MD60\r1 Ordinateur _TD38#:PR=10949]#:?PR]#:HT=HT+PR]\r'
           b'1 Souris #:PR=825]#:?PR]#:HT=HT+PR]\rTOTAL #:?HT]\rZERO #:?1/0] FIN\r' +
           b''.join(b'Ligne %d.\r' % i for i in range(30)) + b'SUITE #:?HT*2]\r')
PAPYRUS = (b'\xff\x0d\x07\x05\xff\xff\x06\xff' + HI(b'LE SCANDALE DES JARDINS') + b'\x8d' +
           HI(b'Le maire a beau faire, M') + b'\x19' + HI(b'me @ Paris.') + b'\x8d')


def main():
    files = {'WORK/LETTRE#040000': LETTRE, 'WORK/JARDINS#040000': PAPYRUS,
             'WORK/FACTURE#040000': FACTURE}
    with tempfile.TemporaryDirectory(prefix='a2fc-docview-') as tmp:
        with boot_hd(Path(tmp), files, port=PORT, plugins=['docview']) as (p, s):
            s.key(b'/'); s.select('/WORKHD'); s.key(RET); p.stable()
            s.select('WORK'); s.key(RET); p.stable()
            s.select('LETTRE'); s.key(RET)
            s.wait(lambda: s.has('Page 1'), 'first page', 60)
            rows = s.rows()
            s.ok('variable at margin 10 + indent 30, marks dropped',
                 any(r[40:43] == 'NOM' and '#' not in r for r in rows))
            s.ok('commands never shown', not any('_MG' in r or '_CE' in r for r in rows))
            s.ok('accents shown as plain letters', any('vous desirez rentrer' in r for r in rows))
            s.ok('right margin 65 honoured', all(len(r.rstrip()) <= 65 for r in rows[1:22]))
            titre = next((r for r in rows if 'TITRE CENTRE' in r), '')
            s.ok('centred title', titre.index('TITRE') > 20 if titre else False)
            s.key(b'A'); s.wait(lambda: any('d{sirez' in r for r in s.rows()), 'accents as stored', 30)
            s.ok('A shows the ISO 646-FR codes as stored', True)
            s.key(b' '); s.wait(lambda: s.has('Page 2'), 'second page', 30)
            s.ok('Space turns the page', any('Ligne' in r for r in s.rows()))
            s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'panels restored', 60); p.stable()
            s.select('JARDINS'); s.key(RET)
            s.wait(lambda: s.has('Page 1'), 'Papyrus page', 60)
            rows = s.rows()
            t = next((r for r in rows if 'LE SCANDALE' in r), '')
            s.ok('Papyrus title centred', t.index('LE SCANDALE') == (79 - 23) // 2 if t else False)
            s.ok('Papyrus $19 and @ read as e and a', any('Meme a Paris.' in r for r in rows))
            s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'panels restored', 60); p.stable()
            s.select('FACTURE'); s.key(RET)
            s.wait(lambda: s.has('Page 1'), 'calculations page', 60)
            rows = s.rows()
            item = next((r for r in rows if '10949,00' in r), '')
            s.ok('10949,00 with its comma at the decimal tab', item.rfind(',') == 47)
            s.ok('825,00 on the same tab', any(r.rfind('825,00') == 44 for r in rows))
            s.ok('the total from the ROM', any('TOTAL' in r and r.rstrip().endswith('11774,00') for r in rows))
            s.ok('1/0 left as written, A2 File Cmd still here', any('ZERO 1/0 FIN' in r for r in rows))
            s.key(b' '); s.wait(lambda: s.has('Page 2'), 'second calculations page', 60)
            suite = next((r.rstrip() for r in s.rows() if 'SUITE' in r), '')
            s.ok('the total carried to page 2, on the tab still in force',
                 suite.endswith('23548,00') and suite.rfind(',') == 47, suite)
            s.key(b'B'); s.wait(lambda: s.has('Page 1'), 'back to page 1', 60)
            s.ok('page 1 again, the same numbers', any(r.rstrip().endswith('11774,00') for r in s.rows()))
            s.key(ESC); s.wait(lambda: s.has('Type  Aux'), 'panels restored', 60); p.stable()
            s.select('LETTRE')
            s.ok('the panels answer after the ROM was used', s.has('LETTRE'))
    return ok_all(s, 'docview')


if __name__ == '__main__':
    sys.exit(main())
