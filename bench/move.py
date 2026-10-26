#!/usr/bin/env python3
"""Banc de la surcouche MOVE (src/plugins/move.c) : deplacer une entree d'un
repertoire a l'autre sans recopier les blocs.

    make build/move.PLG && A2FC_IMG=A2FILECMD-full python3 bench/move.py

Le cas verifie ici est celui qui ecrit dans la TABLE BINAIRE du volume : un
repertoire cible plein doit gagner un bloc. VOLINFO sert de juge -- il relit
tout le volume et compte les blocs occupes mais marques libres, les
references partagees, les pointeurs invalides, les compteurs faux et les
blocs perdus. Un agrandissement de travers se voit la, et nulle part
ailleurs. tools/test_move.py couvre la meme chose sur l'hote; ce banc fait
tourner la surcouche livree sur un vrai volume ProDOS."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from xplug import boot_hd, menu_run, ok_all, RET, ESC, TAB
from pom2 import ROOT,BUILD
sys.path.insert(0,str(ROOT/'tools'))
from prodos_read import Image

PORT = 6819


def main():
    files = {'SRC/HELLO#040000': b'hello' * 20,
             'SRC/KEEP#040000': b'keep' * 8}
    # Douze entrees remplissent le premier bloc d'un repertoire : l'en-tete
    # prend la place zero. DST n'a donc plus une seule entree libre.
    for i in range(12):
        files['DST/F%02d#040000' % i] = b'x' * 16
    with tempfile.TemporaryDirectory(prefix='a2fc-move-') as tmp:
        tmp=Path(tmp)
        # Match the disposable host's resident and native overlays to the
        # current link; BUILD/vol can still be an earlier release stage.
        program={'A2FILE/A2FILE.CODE.BIN':(BUILD/'A2FILE.CODE.BIN').read_bytes()}
        for source in BUILD.glob('A2FILE.CODE.BIN.*'):
            if source.suffix[1:].isupper():
                program['A2FILE/'+source.suffix[1:]+'.PLG#061B00']=source.read_bytes()
        stage=tmp/'bound-stage'
        for name,data in {'SRC/HELLO':b'keep hello','SRC/SUB/INSIDE':b'keep inside','DST/KEEP':b'keep destination'}.items():
            path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        floppy=tmp/'BOUND.po'
        subprocess.run([sys.executable,str(ROOT/'tools/mkvolume.py'),str(stage),str(floppy),
                        '--volume','BOUND','--blocks','280'],check=True,capture_output=True)
        before=floppy.read_bytes();image=Image(before)
        entry=lambda key,name:next(e for e in image.entries(key) if e[1:1+(e[0]&15)].decode()==name)
        srckey=int.from_bytes(entry(2,'SRC')[17:19],'little')
        checks=[]
        for target,badblock,selection in (('DST',1,'HELLO'),('SUB',0,'SUB')):
            case=tmp/('bounds-'+target);case.mkdir()
            good=case/'GOOD.po';good.write_bytes(before)
            victim=entry(2 if target=='DST' else srckey,target)
            assert before.count(victim)==1
            offset=before.index(victim);oldkey=int.from_bytes(victim[17:19],'little')
            malformed=bytearray(before)
            malformed[badblock*512:(badblock+1)*512]=before[oldkey*512:(oldkey+1)*512]
            malformed[offset+17:offset+19]=badblock.to_bytes(2,'little')
            bad=case/'BAD.po';bad.write_bytes(malformed)
            with boot_hd(case,program,port=PORT,blocks=4000,plugins=['move'],floppy2=good) as (p,s):
                def panel(x,name):
                    if s.cursor_row(x) is None:s.key(TAB)
                    s.key(b'/');s.wait(lambda:s.has('[Volumes]'),'volumes');p.stable()
                    s.select('/BOUND',x);s.key(RET);p.stable();s.select(name,x);s.key(RET);p.stable()
                panel(40,'DST');panel(0,'SRC');s.select(selection);p.stable()
                # The cached paths were valid when selected. Replace only
                # disposable media with a corrupt reference into boot data.
                p.eject(1);p.insert(1,str(bad))
                floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8)
                aux=p.peek(0x1000,0xB000,'aux')
                menu_run(s,p,'MOVE')
                s.wait(lambda:s.has('The directories cannot be walked.'),'raw bounds refusal');p.stable()
                s.ok(target+' boot-block reference is refused',s.has('The directories cannot be walked.'))
                s.ok(target+' refusal preserves AUX and the C stack guard',
                     p.peek(0x1000,0xB000,'aux')==aux and p.peek(floor,8)==b'\xA5'*8)
            s.ok(target+' malformed disk is byte-for-byte unchanged',bad.read_bytes()==malformed)
            s.ok(target+' original disk is byte-for-byte unchanged',good.read_bytes()==before)
            checks.extend(s.checks)
        files.update(program)
        # Leave room for the complete distribution and the test directories.
        # DST itself still has exactly one full block and must grow on MOVE.
        with boot_hd(tmp, files, port=PORT, blocks=4000,
                     plugins=['move', 'volinfo']) as (p, s):
            # Le panneau de gauche sur SRC, celui de droite sur DST.
            s.select('SRC'); s.key(RET)
            s.wait(lambda: s.has('/WORKHD/SRC'), 'SRC a gauche'); p.stable()
            s.key(TAB)
            s.select('/WORKHD', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/WORKHD'), 'la racine a droite')
            p.stable()
            s.select('DST', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/WORKHD/DST'), 'DST a droite')
            p.stable()
            s.key(TAB); p.stable()

            s.select('HELLO'); p.stable()
            s.key(b'L'); p.stable()
            menu_run(s, p, 'MOVE')
            s.wait(lambda: s.has('Source is locked'), 'locked source refusal', 30); p.stable()
            s.ok('MOVE refuses a source locked through the file manager',
                 s.has('Source is locked'))
            s.ok('locked source remains in its original directory',
                 any(r[:38].startswith('HELLO ') for r in s.rows()[2:20]))
            s.key(b'L'); p.stable()  # unlock, then the normal move must succeed
            menu_run(s, p, 'MOVE')
            s.wait(lambda: s.has('must grow a block'), 'la demande', 30); p.stable()
            s.ok('dit que le repertoire doit grandir avant de le faire',
                 s.rows()[22].strip().startswith('Move HELLO into /WORKHD/DST?'),
                 s.rows()[22].strip())
            s.key(b'Y')
            s.wait(lambda: s.has('moved:'), 'le deplacement', 60); p.stable()
            s.ok('le deplacement est annonce sans recopie',
                 'nothing copied' in s.rows()[22], s.rows()[22].strip())

            # L'entree est bien dans la cible, et plus dans la source.
            s.ok('HELLO a quitte le panneau de gauche',
                 not any(r[:38].startswith('HELLO ') for r in s.rows()[2:20]),
                 s.rows()[2][:38])
            s.key(TAB); p.stable()
            s.select('HELLO', 40)
            s.ok('HELLO est dans le repertoire cible',
                 s.line(40).startswith('HELLO '), s.line(40))
            s.key(TAB); p.stable()

            # Le juge : le volume doit etre irreprochable.
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
            s.select('/WORKHD'); p.stable()
            menu_run(s, p, 'VOLINFO')
            s.wait(lambda: s.has('M Bitmap'), 'le diagnostic', 180); p.stable()
            text = '\n'.join(s.rows())

            def number(label):
                m = re.search(re.escape(label) + r'\s*(\d+)', text)
                return int(m[1]) if m else None

            for label in ('Used but marked free:', 'Shared references:',
                          'Invalid structure/pointers:', 'Count mismatches:',
                          'Lost blocks:'):
                s.ok('volume sain apres agrandissement -- %s 0' % label,
                     number(label) == 0, text)
            s.key(ESC); s.wait(lambda: s.has('! More'), 'retour aux panneaux'); p.stable()

            # Cross-volume CREATE must work through the actual ProDOS MLI,
            # and the resident destination buffer must survive confirmation.
            s.select('/WORKHD'); s.key(RET); p.stable()
            s.select('SRC'); s.key(RET); p.stable()
            s.select('KEEP'); p.stable()
            s.key(TAB); s.key(b'/'); p.stable()
            s.select('/RAM', 40); s.key(RET); p.stable()
            s.key(TAB); p.stable()
            menu_run(s, p, 'MOVE')
            s.wait(lambda: s.has('Another volume:'), 'cross-volume confirmation', 30)
            s.key(b'Y')
            s.wait(lambda: s.has('copied to the other volume and removed'),
                   'cross-volume move', 60); p.stable()
            s.ok('cross-volume MOVE removes the source after verification',
                 not any(r[:38].startswith('KEEP ') for r in s.rows()[2:20]))
            s.key(TAB); p.stable(); s.select('KEEP', 40)
            s.key(b'T'); p.stable()
            s.ok('cross-volume destination contains the complete file',
                 s.has('keep' * 8), '\n'.join(s.rows()))
            s.key(ESC); p.stable()
        s.checks.extend(checks)
        return ok_all(s, 'move')


if __name__ == '__main__':
    sys.exit(main())
