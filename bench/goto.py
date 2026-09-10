#!/usr/bin/env python3
"""Banc de la surcouche GOTO (src/plugins/goto.c) : les repertoires
favoris, dans A2FILE/GOTO.CFG, a cote du programme.

    make build/goto.PLG && A2FC_IMG=A2FILECMD-full python3 bench/goto.py

Le disque dur du banc porte /WORKHD/WORK/SUB/DEEP/X et /WORKHD/OTHER/Y :
deux repertoires assez differents pour qu'on voie tout de suite dans quel
panneau on est. Le banc joue le cycle complet -- liste vide, deux ajouts,
un doublon refuse, deux sauts, une suppression -- puis rouvre GOTO : POM2
ne recopie jamais le .hdv d'amorcage sur l'hote, alors c'est la liste
affichee par une SECONDE ouverture qui prouve ce que GOTO.CFG contient,
puisqu'elle sort d'une relecture du fichier."""
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, menu_run, ok_all, RET, TAB, ESC

PORT = 6812
DEEP = '/WORKHD/WORK/SUB/DEEP'
OTHER = '/WORKHD/OTHER'
TITLE = 'GOTO -- favourite directories'
LONG = '/WORKHD/'+'A'*15+'/'+'B'*15+'/'+'C'*15+'/'+'D'*7

HD_FILES = {'A2FILE/GOTO.RES#040000':b'keep this recovery file\r', 'WORK/SUB/DEEP/X.TXT': b'deep\r', 'OTHER/Y.TXT': b'other\r', LONG[len('/WORKHD/'):]+ '/X.TXT':b'long\r'}


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-goto-') as tmp:
        with boot_hd(Path(tmp), HD_FILES, port=PORT, plugins=['goto']) as (p, s):

            stack=p.peek(0x80,2);floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8)

            def open_panel(x, vol, *names):
                """Amene le panneau qui commence en colonne x sur /vol/names..."""
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
                s.select(vol, x); s.key(RET)
                s.wait(lambda: s.rows()[0][x:].startswith(vol), vol); p.stable()
                path = vol
                for n in names:
                    s.select(n, x); s.key(RET)
                    path += '/' + n
                    s.wait(lambda: s.rows()[0][x:].startswith(path), path); p.stable()

            def open_goto():
                """Ouvre GOTO par le menu ; rend l'ecran de la liste."""
                menu_run(s, p, 'GOTO')
                s.wait(lambda: s.has(TITLE), "l'ecran de GOTO", 30)
                p.stable()
                return s.rows()

            def leave(*keys):
                """Tape les touches, attend le retour aux panneaux, rend la ligne 22."""
                for k in keys:
                    s.key(k)
                s.wait(lambda: not s.has(TITLE), 'le retour aux panneaux', 30)
                p.stable()
                return s.rows()[22].strip()

            def rows_of(screen):
                """Les lignes numerotees de la liste affichee."""
                return [r.strip() for r in screen[2:14] if r.strip() and r.strip()[0].isdigit()]

            # The menu now spans several pages: use its normal navigation.
            open_goto()
            s.ok('GOTO opens from the plugin menu',s.has(TITLE))
            leave(ESC)

            # 2. Liste vide : l'ecran le dit, et le message aussi en sortant.
            screen = open_goto()
            s.ok('la liste vide affiche le titre, le mode d\'emploi et la barre de touches',
                 s.has('No favourites yet') and any('1-9' in r and 'ESC' in r for r in screen),
                 [r.strip() for r in screen[:5] if r.strip()])
            line = leave(ESC)
            s.ok('ESC sur une liste vide : "No favourites yet: A adds this directory"',
                 line == 'No favourites yet: A adds this directory', line)

            def path_to(value,key=RET):
                open_goto();s.key(b'P');s.wait(lambda:s.has('Path: '),'path input',20)
                if value:s.type(value)
                return leave(key)
            line=path_to(DEEP.lower()+'///')
            s.ok('P opens lowercase path with trailing slashes',line=='Jumped to '+DEEP and s.rows()[0].startswith(DEEP))
            screen=open_goto();s.ok('direct path is not added to favourites',rows_of(screen)==[]);leave(ESC)
            line=path_to(OTHER,ESC)
            s.ok('ESC cancels direct path without moving panel',s.rows()[0].startswith(DEEP) and not line)
            open_goto();s.key(b'P');s.wait(lambda:s.has('Path: '),'path input',20)
            s.type(OTHER+'X');s.key(b'\x7f');line=leave(RET)
            s.ok('Delete edits the path',line=='Jumped to '+OTHER)
            for value in ('OTHER','/',''):
                line=path_to(value)
                s.ok('relative or empty path rejected: '+repr(value),line=='Use /VOLUME/DIRECTORY.' and s.rows()[0].startswith(OTHER))
            for value in ('/NO.VOLUME/MISSING',OTHER+'/Y'):
                line=path_to(value)
                s.ok('missing directory or file leaves panel unchanged',line=='Gone: '+value and s.rows()[0].startswith(OTHER))
            line=path_to(LONG+'EXCESS')
            s.ok('full 63-character path fits; excess input is bounded',len(LONG)==63 and line=='Jumped to '+LONG)
            left=s.rows()[0][:39];s.key(TAB)
            line=path_to(DEEP)
            s.ok('P acts on the right panel when active',line=='Jumped to '+DEEP and s.rows()[0][40:].startswith(DEEP) and s.rows()[0][:39]==left)

            # 3. A dans /WORKHD/WORK/SUB/DEEP : le premier favori.
            open_panel(0, '/WORKHD', 'WORK', 'SUB', 'DEEP')
            open_goto()
            line = leave(b'A')
            s.ok('A ajoute le repertoire courant : "Added %s"' % DEEP,
                 line == 'Added ' + DEEP, line)

            # 4. A dans /WORKHD/OTHER : le second.
            open_panel(0, '/WORKHD', 'OTHER')
            open_goto()
            line = leave(b'A')
            s.ok('A ajoute le second : "Added %s"' % OTHER, line == 'Added ' + OTHER, line)

            # 5. Le meme une deuxieme fois est refuse.
            open_goto()
            line = leave(b'A')
            s.ok('un chemin deja liste est refuse', line == 'Already in the list.', line)

            # 6. La liste relue du fichier montre les deux, numerotes.
            open_panel(0, '/WORKHD')
            screen = open_goto()
            listed = rows_of(screen)
            s.ok('la liste montre les deux favoris numerotes, dans l\'ordre',
                 listed == ['1 ' + DEEP, '2 ' + OTHER], listed)

            # Three entries exercise shifts past multiple neighbours.
            leave(b'A')
            def favourites():return rows_of(open_goto())
            original=['1 '+DEEP,'2 '+OTHER,'3 /WORKHD']
            s.ok('third favourite added for reordering',favourites()==original)
            def move(source,target=None):
                s.key(b'M');s.wait(lambda:s.has('Move which favourite?'),'move source',20)
                if target is None:return leave(source)
                s.key(source);s.wait(lambda:s.has('New position?'),'move destination',20)
                return leave(target)
            line=move(b'1',b'3')
            s.ok('move confirms without changing directory',line=='Favourite moved.' and s.rows()[0].startswith('/WORKHD '))
            s.ok('moving first to last persists order',favourites()==['1 '+OTHER,'2 /WORKHD','3 '+DEEP])
            move(b'3',b'1')
            s.ok('moving last to first preserves neighbours',favourites()==original)
            line=move(b'2',b'2')
            s.ok('same position is a no-op',line=='Already at that position.' and favourites()==original)
            move(ESC)
            s.ok('ESC at source preserves saved order',favourites()==original)
            move(b'1',ESC)
            s.ok('ESC at destination preserves saved order',favourites()==original)
            move(b'9')
            s.ok('unavailable source preserves saved order',favourites()==original)
            move(b'1',b'9')
            s.ok('unavailable destination preserves saved order',favourites()==original)
            s.key(b'D');s.wait(lambda:s.has('Delete which one?'),'delete third',20);leave(b'3')
            s.ok('temporary third entry removed',favourites()==['1 '+DEEP,'2 '+OTHER])

            # 7. 1 : le panneau actif saute au premier favori.
            line = leave(b'1')
            s.ok('1 emmene le panneau sur %s' % DEEP,
                 s.rows()[0].startswith(DEEP) and line == 'Jumped to ' + DEEP,
                 (s.rows()[0][:38], line))

            # 8. 2 : et au second.
            open_goto()
            line = leave(b'2')
            s.ok('2 emmene le panneau sur %s' % OTHER,
                 s.rows()[0].startswith(OTHER) and line == 'Jumped to ' + OTHER,
                 (s.rows()[0][:38], line))

            # 9. D puis 1 : le premier disparait, le fichier est reecrit.
            open_goto()
            s.key(b'D')
            s.wait(lambda: s.has('Delete which one?'), 'la question de la suppression', 20)
            line = leave(b'1')
            s.ok('D puis 1 : "Removed %s"' % DEEP, line == 'Removed ' + DEEP, line)

            # 10. La preuve du fichier : une SECONDE ouverture le relit.
            screen = open_goto()
            listed = rows_of(screen)
            s.ok('GOTO.CFG relu ne garde que %s, en 1' % OTHER, listed == ['1 ' + OTHER], listed)
            leave(ESC)

            # 11. La liste des volumes n'est pas un repertoire ProDOS.
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
            open_goto()
            line = leave(b'A')
            s.ok('A refuse la liste des volumes',
                 line == 'Not a ProDOS directory: nothing to add.', line)

            # 12. Un favori qui n'existe plus : GOTO ne bouge pas le panneau.
            # (C'est la ou une petite surcouche aurait appele read_panel ; une
            # grosse ne le peut pas, elle ouvre le chemin d'abord -- voir le
            # commentaire de tete de goto.c.)
            open_panel(0, '/WORKHD')
            s.key(b'K'); s.wait(lambda: s.has('New directory'), 'mkdir')
            s.type('GONESOON'); s.key(RET)
            s.wait(lambda: s.has('GONESOON'), 'le repertoire cree'); p.stable()
            s.select('GONESOON', 0); s.key(RET)
            s.wait(lambda: s.rows()[0].startswith('/WORKHD/GONESOON'), 'dedans'); p.stable()
            open_goto()
            line = leave(b'A')
            s.ok('A ajoute /WORKHD/GONESOON', line == 'Added /WORKHD/GONESOON', line)
            open_panel(0, '/WORKHD')
            s.select('GONESOON', 0); s.key(b'D')
            s.wait(lambda: s.has('Delete GONESOON'), 'la confirmation'); s.key(b'Y')
            s.wait(lambda: not s.has('GONESOON'), 'le repertoire supprime'); p.stable()
            open_goto()
            line = leave(b'2')
            s.ok('un favori disparu : "Gone: ..." et le panneau reste ou il est',
                 line == 'Gone: /WORKHD/GONESOON' and s.rows()[0].startswith('/WORKHD '),
                 (s.rows()[0][:38], line))

            # Inject a short fwrite on the disposable test volume. The stub
            # returns zero and discards fwrite's six stacked argument bytes.
            open_goto()
            address=s.sym['_fwrite'];original_code=p.peek(address,7)
            stub=b'\xA9\x00\xA2\x00\x4C'+s.sym['incsp6'].to_bytes(2,'little')
            try:
                p.poke(address,stub)
                line=move(b'1',b'2')
            finally:
                p.poke(address,original_code)
            s.ok('short write reports save failure instead of success',line=='GOTO.CFG cannot be written.')
            preserved=['1 '+OTHER,'2 /WORKHD/GONESOON']
            s.ok('short write preserves the original configuration',favourites()==preserved);leave(ESC)

            def fail_rename(which):
                # Trap selected RENAME calls; forward every other MLI call.
                address=s.sym['_mli_call'];saved=p.peek(address,3)
                location=0x3C00;counter=0x3C80;code=bytearray();branches=[]
                def emit(*v):code.extend(v)
                def branch(op,label):emit(op,0);branches.append((len(code)-1,label))
                emit(0x48,0xA0,0,0xB1,0x80,0xC9,0xC2);branch(0xD0,'pass')
                emit(0xEE,counter&255,counter>>8,0xAD,counter&255,counter>>8)
                for n in which:emit(0xC9,n);branch(0xF0,'fail')
                branch(0xD0,'pass') # final comparison was unequal
                labels={'fail':len(code)}
                emit(0x68,0x20,s.sym['popa']&255,s.sym['popa']>>8,0xA9,0x27,0xA2,0,0x60)
                labels['pass']=len(code);emit(0x68);code.extend(saved)
                emit(0x4C,(address+3)&255,(address+3)>>8)
                for at,label in branches:code[at]=(labels[label]-at-1)&255
                open_goto();p.poke(location,bytes(code));p.poke(counter,b'\x00')
                try:
                    p.poke(address,b'\x4C'+location.to_bytes(2,'little'))
                    result=move(b'1',b'2')
                finally:p.poke(address,saved)
                return result
            for call in (1,2):
                line=fail_rename((call,))
                s.ok('rename failure '+str(call)+' reports error',line=='GOTO.CFG cannot be written.')
                s.ok('rename failure '+str(call)+' preserves old favourites',favourites()==preserved);leave(ESC)
            open_goto();line=move(b'1',b'2')
            s.ok('retry after failures saves successfully',line=='Favourite moved.' and favourites()==['1 /WORKHD/GONESOON','2 '+OTHER]);leave(ESC)
            def rename_saved(old,new):
                path_to('/WORKHD/A2FILE');s.select(old)
                s.key(b'R');s.wait(lambda:s.has('New name'),'rename recovery file',20)
                s.key(b'\x7f'*len(old));s.type(new);s.key(RET);p.stable();s.select(new)
            current=['1 /WORKHD/GONESOON','2 '+OTHER]
            line=fail_rename((2,3))
            s.ok('failed rollback retains named recovery files',line=='Save failed; restore GOTO.BAK. GOTO.TMP kept.')
            rename_saved('GOTO.BAK','GOTO.CFG')
            s.select('GOTO.TMP');s.key(b'D');s.wait(lambda:s.has('Delete GOTO.TMP'),'delete test temporary',20)
            s.key(b'Y');p.stable()
            s.ok('original list can be recovered from backup',favourites()==current);leave(ESC)
            for reserved in ('GOTO.TMP','GOTO.BAK'):
                rename_saved('GOTO.RES',reserved)
                open_goto();line=move(b'1',b'2')
                s.ok('existing '+reserved+' blocks replacement',line==reserved+' exists; check saved files.')
                s.ok('collision preserves configuration',favourites()==current);leave(ESC)
                rename_saved(reserved,'GOTO.RES')
                menu_run(s,p,'CRC');s.wait(lambda:s.has('CRC-32'),'reserved file checksum',30)
                expected=f'GOTO.RES: CRC-32 ${zlib.crc32(HD_FILES["A2FILE/GOTO.RES#040000"]):08X}, 24 bytes'
                s.ok('recovery file contents preserved',s.rows()[22].strip()==expected,s.rows()[22].strip())
            s.ok('stack restored and bounded',p.peek(0x80,2)==stack and p.peek(floor,8)==b'\xA5'*8)

    return ok_all(s, 'goto')


if __name__ == '__main__':
    sys.exit(main())
