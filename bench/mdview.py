#!/usr/bin/env python3
"""Banc de la surcouche MDVIEW (src/plugins/mdview.c) : un fichier Markdown
ou un texte a longues lignes, lu en plein ecran, replie a 79 colonnes, page
par page dans les deux sens.

    make build/mdview.PLG && A2FC_IMG=A2FILECMD-full python3 bench/mdview.py

Trois fichiers sur le disque dur du banc : WORK/README.MD (LF) avec un
titre `#`, un paragraphe de 300 caracteres, une liste a puces dont un
element deborde, un bloc ``` , un mot accentue en UTF-8 et vingt lignes de
queue pour faire une seconde page ; WORK/LONG.TXT (CRLF) avec une ligne de
plus de 400 caracteres et une de 1800 a cheval sur deux pages ; WORK/HI.TXT,
un texte ProDOS avec le bit haut. Les lignes attendues sont recalculees ici par
textwrap (meme regle : coupure au dernier espace avant la colonne 79) et
comparees a l'ecran ligne a ligne ; l'inverse du titre et de l'en-tete est
lu dans la memoire ecran."""
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, menu_run, ok_all, RET, ESC

PORT = 6810
DOWN, UP = b'\x0a', b'\x0b'

WORDS = ('the quick brown fox jumps over the lazy dog near the old river bank while the evening '
         'sun sets slowly behind the purple hills and the first stars appear above the valley ').split()
PARA = ' '.join(WORDS * 4)[:300]
PARA = PARA[:PARA.rfind(' ')]                       # 300 caracteres, coupes a un mot entier
assert 290 <= len(PARA) <= 300
ITEM1 = 'first bullet item, short'
ITEM2 = ('second bullet item long enough to spill past the seventy-nine column limit of the '
         'screen and show the hanging indent')
ITEM3 = 'third item with a star'
CODE = ('    code line  with  spaces kept verbatim, not wrapped, and long enough to be cut at the '
        'seventy-ninth column of the screen')
ACC = 'Un café très chaud, **bold** and `code` markers dropped.'
ACC_OUT = 'Un cafe tres chaud, bold and code markers dropped.'
TAIL = ['Line %02d of the tail.' % i for i in range(1, 21)]
README = ('# A2 File Cmd README\n\n' + PARA + '\n\n'
          + '- ' + ITEM1 + '\n- ' + ITEM2 + '\n* ' + ITEM3 + '\n\n'
          + '```\n' + CODE + '\n```\n\n' + ACC + '\n' + '\n'.join(TAIL) + '\n').encode('utf-8')

LONGLINE = ' '.join(WORDS * 5)[:420]
LONGLINE = LONGLINE[:LONGLINE.rfind(' ')]
HUGE = ' '.join(WORDS * 30)[:1800]
HUGE = HUGE[:HUGE.rfind(' ')]                       # a cheval sur les pages 1 et 2
LONG = ('First line.\r\n' + LONGLINE + '\r\nend\r\n\r\nafter blank\r\n' + HUGE + '\r\nlast\r\n').encode('ascii')
HI = bytes(b | 0x80 for b in b'HELLO WORLD\rSECOND LINE\r')   # un texte ProDOS, bit haut

MANY_ROWS = ['row %04d **literal**' % i for i in range(21 * 66)]
MANY = ('```\n' + '\n'.join(MANY_ROWS) + '\n```\n# Last heading\n').encode('ascii')

SOLID_ROWS = ['%04d' % i + 'x' * 75 for i in range(280)]
SOLID = (''.join(SOLID_ROWS) + '\nlast\n').encode('ascii')

UTF_ROWS = ['ee?? %02d' % i for i in range(32)]
UTF = ''.join('éé漢😀 %02d\n' % i for i in range(32)).encode('utf-8')
BOM = b'\xef\xbb\xbf' + README

SPLIT = ('é' * 1023 + '漢\nEND\n').encode('utf-8')

FILES = {'WORK/SPLIT.TXT': SPLIT, 'WORK/UTF.TXT': UTF, 'WORK/BOM.MD#040000': BOM, 'WORK/SOLID.TXT': SOLID, 'WORK/MANY.MD#040000': MANY, 'WORK/README.MD#040000': README, 'WORK/LONG.TXT': LONG, 'WORK/HI.TXT': HI}


def wrap(text, first='', rest=''):
    return textwrap.wrap(text, 79, initial_indent=first, subsequent_indent=rest,
                         break_long_words=False, break_on_hyphens=False)


PAGE1 = (['A2 File Cmd README', ''] + wrap(PARA) + ['']
         + ['- ' + ITEM1] + wrap(ITEM2, '- ', '  ') + ['- ' + ITEM3, '']
         + [CODE[:79], '', ACC_OUT] + TAIL)[:21]
LONG_ROWS = ['First line.'] + wrap(LONGLINE) + ['end', '', 'after blank']
HUGE_ROWS = wrap(HUGE)


def inverse(p, r, n):
    """Les n premieres cases de la ligne r sont-elles en video inverse ?"""
    main, aux = p.peek(0x400, 1024), p.peek(0x400, 1024, 'aux')
    base = 0x80 * (r % 8) + 0x28 * (r // 8)
    return all((aux if c % 2 == 0 else main)[base + c // 2] < 0x80 for c in range(n))


def text_rows(s):
    """Les lignes 1 a 21 de l'ecran, sans les espaces de fin."""
    return [r.rstrip() for r in s.rows()[1:22]]


def view(s, p, name):
    s.select(name, 0); p.stable()
    menu_run(s, p, 'MDVIEW')
    s.wait(lambda: s.has('Page 1'), 'la premiere page de ' + name, 30)
    p.stable()


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-mdview-') as tmp:
        tmp = Path(tmp)
        with boot_hd(tmp, FILES, port=PORT, plugins=['mdview']) as (p, s):
            # -- Un dossier : refuse ------------------------------------------
            s.select('WORK', 0); p.stable()
            menu_run(s, p, 'MDVIEW')
            s.wait(lambda: s.has('Select a text file'), 'le refus du dossier', 30); p.stable()
            s.ok('refuse un dossier', s.rows()[22].startswith('Select a text file to read.') and s.has('Type  Aux'),
                 s.rows()[22].strip())

            s.select('WORK', 0); s.key(RET); s.wait(lambda: s.has('/WORKHD/WORK'), 'WORK'); p.stable()

            # -- README.MD, page 1 --------------------------------------------
            view(s, p, 'README.MD')
            rows = text_rows(s)
            s.ok('le titre, ligne 0, nomme le fichier en inverse',
                 s.rows()[0].startswith('/WORKHD/WORK/README.MD') and inverse(p, 0, 22), s.rows()[0].strip())
            s.ok("l'en-tete # est en inverse, sans son #",
                 rows[0] == 'A2 File Cmd README' and inverse(p, 1, len(rows[0])), rows[0])
            n = len(wrap(PARA))
            s.ok('le paragraphe est replie sur %d lignes de 79 colonnes au plus, sans mot coupe' % n,
                 rows[2:2 + n] == wrap(PARA) and all(len(r) <= 79 for r in rows[2:2 + n])
                 and ' '.join(rows[2:2 + n]) == PARA, rows[2:2 + n])
            b = 3 + n
            s.ok("les puces : `- ` et `* ` en tirets, l'element long avec un retrait de 2",
                 rows[b] == '- ' + ITEM1 and rows[b + 1:b + 3] == wrap(ITEM2, '- ', '  ')
                 and rows[b + 2].startswith('  ') and rows[b + 3] == '- ' + ITEM3, rows[b:b + 4])
            c = b + 5
            s.ok('la ligne du bloc ``` est verbatim, tronquee a 79, sans les lignes ```',
                 rows[c] == CODE[:79] and rows[c - 1] == '' and rows[c + 1] == '', (rows[c - 1:c + 2]))
            s.ok('e pour e accent aigu, e pour e accent grave, ** et ` supprimes', rows[c + 2] == ACC_OUT, rows[c + 2])
            s.ok('toute la page 1 est celle attendue', rows == PAGE1,
                 [(i, a, b) for i, (a, b) in enumerate(zip(rows, PAGE1)) if a != b][:3])
            s.ok('la ligne 22 dit la page 1', s.rows()[22].startswith('Page 1: Space/Down next, Up back, R start, ESC quits'),
                 s.rows()[22].strip())

            # -- Espace : page 2, la fin ; Haut : page 1 ------------------------
            s.key(b' '); s.wait(lambda: s.has('Page 2'), 'la page 2', 20); p.stable()
            rows = text_rows(s)
            s.ok('Espace : la page 2 reprend a la ligne de queue suivante, et dit la fin',
                 rows[:len(TAIL) - 6] == TAIL[6:] and rows[len(TAIL) - 6] == ''
                 and s.rows()[22].startswith('Page 2 (end)'), (rows[:2], s.rows()[22].strip()))
            s.key(b' '); p.stable()
            s.ok('Espace a la fin : la page 2 reste', s.rows()[22].startswith('Page 2 (end)'), s.rows()[22].strip())
            s.key(UP); s.wait(lambda: s.has('Page 1'), 'le retour a la page 1', 20); p.stable()
            s.ok("Haut : la page 1 revient, l'en-tete en inverse",
                 text_rows(s) == PAGE1 and inverse(p, 1, 18), text_rows(s)[:2])
            s.key(DOWN); s.wait(lambda: s.has('Page 2'), 'la page 2 par Bas', 20); p.stable()
            s.ok('Bas : la page 2 encore, identique', text_rows(s)[:3] == TAIL[6:9], text_rows(s)[:3])
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux     Size'), 'le retour aux panneaux', 30); p.stable()
            s.ok('ESC rend les panneaux, le curseur sur README.MD',
                 s.rows()[0].startswith('/WORKHD/WORK ') and s.line(0).startswith('README.MD '), s.line(0).strip()[:24])

            # -- LONG.TXT : CRLF, une ligne de 400 caracteres ------------------
            view(s, p, 'LONG')
            rows = text_rows(s)
            k = len(LONG_ROWS)
            s.ok('LONG : la ligne de %d caracteres repliee sur %d lignes, sans mot coupe' % (len(LONGLINE), k - 4),
                 rows[1:k - 3] == wrap(LONGLINE) and ' '.join(rows[1:k - 3]) == LONGLINE, rows[1:k - 3])
            s.ok('LONG : CRLF ne fait pas de ligne vide, la ligne vide du fichier en fait une',
                 rows[:k] == LONG_ROWS, rows[k - 4:k + 1])
            # La ligne de 1800 caracteres commence en bas de la page 1 et finit sur la 2 :
            # la page 2 rejoue la ligne depuis son debut en sautant les lignes deja vues.
            top = rows[k:]
            s.key(b' '); s.wait(lambda: s.has('Page 2'), 'la page 2 de LONG', 20); p.stable()
            rows2 = text_rows(s)
            h = len(HUGE_ROWS) - len(top)
            s.ok('LONG : la ligne de %d caracteres, a cheval sur les pages 1 et 2 (%d + %d lignes), sans rupture'
                 % (len(HUGE), len(top), h),
                 top + rows2[:h] == HUGE_ROWS and rows2[h] == 'last' and s.rows()[22].startswith('Page 2 (end)'),
                 (top[-1:], rows2[:1], rows2[h - 1:h + 1], s.rows()[22].strip()))
            s.key(UP); s.wait(lambda: s.has('Page 1'), 'le retour a la page 1 de LONG', 20); p.stable()
            s.ok('LONG : Haut rend la page 1 a l identique', text_rows(s) == rows, text_rows(s)[k:k + 2])
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux     Size'), 'le retour aux panneaux', 30); p.stable()
            s.ok('ESC rend les panneaux, le curseur sur LONG', s.line(0).startswith('LONG '), s.line(0).strip()[:24])

            # A fence crosses the 64-slot ring boundary; return through retained
            # history, then restart and verify that its fence state was reset.
            view(s, p, 'MANY.MD')
            for page in range(2, 68):
                s.key(DOWN)
                s.wait(lambda: s.rows()[22].startswith('Page %d' % page), 'long page %d' % page, 20)
            p.stable()
            s.ok('lecture au-dela de 64 pages, fin et titre hors du bloc',
                 text_rows(s)[0] == 'Last heading' and inverse(p, 1, 12)
                 and s.rows()[22].startswith('Page 67 (end)'), s.rows()[22].strip())
            s.key(DOWN); p.stable()
            s.ok('la fin au-dela de 64 reste stable', s.rows()[22].startswith('Page 67 (end)'))
            for page in range(66, 3, -1):
                s.key(UP)
                s.wait(lambda: s.rows()[22].startswith('Page %d:' % page), 'back page %d' % page, 20)
            p.stable()
            s.ok('les 64 pages retenues gardent le texte et le bloc de code',
                 text_rows(s) == MANY_ROWS[63:84], text_rows(s)[:2])
            s.key(UP); p.stable()
            s.ok('Haut reste sur la plus ancienne page retenue', s.rows()[22].startswith('Page 4:'))
            s.key(DOWN); s.wait(lambda: s.has('Page 5:'), 'forward retained'); p.stable()
            s.ok('retour avant dans les pages retenues', text_rows(s) == MANY_ROWS[84:105])
            s.key(b'r'); s.wait(lambda: s.has('Page 1:'), 'restart'); p.stable()
            s.ok('R repart au debut avec le bon etat Markdown', text_rows(s) == MANY_ROWS[:21])
            s.key(UP); p.stable()
            s.ok('Haut ne depasse pas la premiere page', s.rows()[22].startswith('Page 1:'))
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux     Size'), 'les panneaux apres MANY', 30); p.stable()
            s.ok('ESC restaure la selection du document long', s.line(0).startswith('MANY.MD '))

            # A single logical line crosses the old 8-bit wrapped-row limit.
            view(s, p, 'SOLID')
            expected = SOLID_ROWS + ['last']
            for page in range(1, 15):
                if page > 1:
                    s.key(DOWN)
                    s.wait(lambda: s.rows()[22].startswith('Page %d' % page), 'solid page %d' % page, 60)
                    p.stable()
                want = expected[(page - 1) * 21:page * 21]
                s.ok('ligne sans saut : page %d exacte' % page,
                     text_rows(s) == want + [''] * (21 - len(want)), text_rows(s)[:1])
            s.ok('la longue ligne atteint la vraie fin', s.rows()[22].startswith('Page 14 (end)'))
            for page in (13, 12):
                s.key(UP)
                s.wait(lambda: s.rows()[22].startswith('Page %d:' % page), 'solid back %d' % page, 60)
                p.stable()
                s.ok('retour dans la longue ligne : page %d exacte' % page,
                     text_rows(s) == expected[(page - 1) * 21:page * 21])
            s.key(b'R'); s.wait(lambda: s.has('Page 1:'), 'solid restart', 60); p.stable()
            s.ok('R retrouve le debut de la longue ligne', text_rows(s) == SOLID_ROWS[:21])
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux     Size'), 'panneaux apres SOLID', 30); p.stable()
            s.ok('la selection revient apres la longue ligne', s.line(0).startswith('SOLID '))

            view(s, p, 'UTF')
            s.ok('UTF-8 majoritaire : accents translitteres, autres caracteres remplaces',
                 text_rows(s) == UTF_ROWS[:21], text_rows(s)[:2])
            s.key(DOWN); s.wait(lambda: s.has('Page 2'), 'UTF page 2'); p.stable()
            s.ok('UTF-8 : seconde page exacte', text_rows(s) == UTF_ROWS[21:] + [''] * 10)
            s.key(UP); s.wait(lambda: s.has('Page 1:'), 'UTF back'); p.stable()
            s.ok('UTF-8 : retour exact', text_rows(s) == UTF_ROWS[:21])
            s.key(ESC); s.wait(lambda: s.has('Type  Aux     Size'), 'UTF panels'); p.stable()

            view(s, p, 'SPLIT')
            s.ok('UTF-8 coupe a 2048 octets : detection et decodage corrects',
                 text_rows(s) == ['e' * 79] * 12 + ['e' * 75 + '?', 'END'] + [''] * 7,
                 text_rows(s)[12:14])
            s.key(ESC); s.wait(lambda: s.has('Type  Aux     Size'), 'SPLIT panels'); p.stable()

            view(s, p, 'BOM.MD')
            s.ok('BOM retire : titre Markdown reconnu en inverse',
                 text_rows(s) == PAGE1 and inverse(p, 1, 18), text_rows(s)[:2])
            s.key(DOWN); s.wait(lambda: s.has('Page 2'), 'BOM page 2'); p.stable()
            s.key(b'R'); s.wait(lambda: s.has('Page 1:'), 'BOM restart'); p.stable()
            s.ok('R saute encore le BOM et restaure le titre',
                 text_rows(s) == PAGE1 and inverse(p, 1, 18))
            s.key(ESC); s.wait(lambda: s.has('Type  Aux     Size'), 'BOM panels'); p.stable()

            # -- HI.TXT : un texte ProDOS, le bit haut sur chaque octet, CR ------
            view(s, p, 'HI')
            rows = text_rows(s)
            s.ok('HI : le bit haut retire, CR en fin de ligne', rows[:3] == ['HELLO WORLD', 'SECOND LINE', '']
                 and s.rows()[22].startswith('Page 1 (end)'), rows[:3])
            s.key(ESC)
            s.wait(lambda: s.has('Type  Aux     Size'), 'le retour aux panneaux', 30); p.stable()
    return ok_all(s, 'mdview')


if __name__ == '__main__':
    sys.exit(main())
