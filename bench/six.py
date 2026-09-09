#!/usr/bin/env python3
"""Six service overlays on a real cc65 runtime, with disposable volumes."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from pom2 import Pom2, Session, ROOT
from xplug import stage_hd, menu_run, ok_all, RET, ESC
sys.path.insert(0,str(ROOT/'tools'))
from prodos_read import Image
from po2dsk import to_dsk
from po22mg import to_2mg


def make_disk(tmp):
    stage=tmp/'target';(stage/'DST').mkdir(parents=True)
    (stage/'DST'/'OLDER.TXT#040000').write_bytes(b'old destination\r')
    (stage/'DST'/'KEEP.TXT#040000').write_bytes(b'keep me\r')
    image=tmp/'TARGET.po'
    subprocess.run([sys.executable,str(ROOT/'tools/mkvolume.py'),str(stage),str(image),'--volume','TARGET','--blocks','280'],check=True,capture_output=True)
    return image


def entry(image,path):
    key=2
    for name in path.split('/'):
        e=next(e for e in image.entries(key) if e[1:1+(e[0]&15)].decode()==name)
        key=int.from_bytes(e[17:19],'little')
    return e


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-six-') as t:
        tmp=Path(t);target=make_disk(tmp)
        original=target.read_bytes();different=bytearray(original);different[10000]^=1
        files={'SRC/NEW.TXT':b'new file\r'*90,'SRC/OLDER.TXT':b'new source\r',
               'SRC/DIR/NEST.TXT':b'nested\r','SRC/GONE.TXT':b'recover deleted\r'*80,
               'IMAGES/SAME.PO':original,'IMAGES/SAME.DSK':to_dsk(original),
               'IMAGES/SAME.2MG':to_2mg(original),'IMAGES/DIFF.PO':bytes(different)}
        hd=stage_hd(tmp,{k+('#040000' if k.endswith('.TXT') else ''):v for k,v in files.items()},blocks=8000,plugins=['undelete','diskcmp','mkimage','rescue','sync','tree'])
        # Source OLDER.TXT is explicitly newer than the target.
        d=bytearray(hd.read_bytes());im=Image(d)
        old=entry(im,'SRC/OLDER.TXT');key=int.from_bytes(entry(im,'SRC')[17:19],'little')
        off=d.index(old,key*512,(key+1)*512)
        d[off+33:off+35]=((30<<9)|(1<<5)|1).to_bytes(2,'little');hd.write_bytes(d)
        with Pom2(hd,floppy2=target,port=6840+int(os.environ.get('A2FC_PORT_OFFSET','0'))) as p:
            s=Session(p);s.boot();floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            def go(volume,dirs=(),side=0):
                s.key(b'/');s.select('/'+volume,side);s.key(RET);p.stable()
                for name in dirs:s.select(name,side);s.key(RET);p.stable()
            def done(text):
                s.wait(lambda:s.has(text),'fin: '+text,120);p.stable()
            go('TARGET',['DST']);s.key(b'\t');go('WORKHD',['SRC'],40);s.key(b'\t')
            # Left destination, right source: focus source throughout.
            s.key(b'\t')
            menu_run(s,p,'SYNC');done('Copy missing/newer');s.key(b'N');p.stable()
            s.ok('SYNC annulation avant toute copie',s.has('Type  Aux'))
            menu_run(s,p,'SYNC');done('Copy missing/newer');s.key(b'Y');done('SYNC:')
            s.ok('SYNC copie fichiers nouveaux, plus recents et sous-dossiers',s.has('4 copied') and s.has('0 errors'),s.rows()[22])
            menu_run(s,p,'SYNC');done('Copy missing/newer');s.key(b'Y');done('SYNC:')
            s.ok('SYNC second passage sans recopie',s.has('0 copied') and s.has('4 skipped'),s.rows()[22])
            menu_run(s,p,'TREE');done('TREE complete.')
            s.ok('TREE total recursif et fichier imbrique',s.has('NEST.TXT') and s.has('4 files'), '\n'.join(s.rows()))
            s.key(ESC);p.stable()
            # Delete the source file through ProDOS itself, then recover it.
            s.select('GONE.TXT',40);s.key(b'D');p.stable();s.key(b'Y');p.stable()
            # A new recovery directory avoids the name copied by SYNC.
            s.key(b'\t');s.key(b'K');p.stable();s.type('RECOVER');s.key(RET);p.stable();s.select('RECOVER');s.key(RET);p.stable();s.key(b'\t')
            menu_run(s,p,'UNDELETE');done('UNDELETE - SOURCE');s.ok('candidat libre',s.has('Candidate: all referenced blocks are free.'),'\n'.join(s.rows()))
            s.ok('UNDELETE retrouve le fichier efface et valide ses blocs',s.has('GONE.TXT'))
            s.key(b'R');done('Recover this candidate');s.key(b'Y');done('Recovered GONE.TXT')
            s.select('NEW.TXT',40);menu_run(s,p,'RESCUE');done('RESCUE: F');s.key(b'F');done('Recovery base name');s.key(b'\x7f'*7);s.type('SALVAGE');s.key(RET)
            done('Recover with 30');s.key(b'Y');s.wait(lambda:s.has('RESCUE:') or s.has('RESCUE incomplete'),'rescue result',120);p.stable()
            if s.has('RESCUE incomplete'):
                p.eject(1);debug=Image(target.read_bytes());print(list(debug.walk()),flush=True);print(debug.read(entry(debug,'DST/RECOVER/SALVAGE.LOG')),flush=True)
            s.ok('RESCUE copie le fichier avec journal',s.has('0 missing chunks'),s.rows()[22])
            go('WORKHD',['IMAGES'],40)
            # Both panels now point to the image directory for comparisons.
            s.key(b'\t');go('WORKHD',['IMAGES']);s.key(b'\t');s.select('SAME.PO',40)
            for name,expected in [('SAME.DSK','Identical: 280'),('SAME.2MG','Identical: 280'),('DIFF.PO','1 differing blocks')]:
                menu_run(s,p,'DISKCMP');done('DISKCMP: V');s.key(b'I');done('Image in OTHER panel');s.key(b'\x7f'*7);s.type(name);s.key(RET);done(expected)
                s.ok('DISKCMP '+name,s.has(expected),s.rows()[22])
            # A new .2MG on HD; IMGFS must accept its filesystem as empty.
            menu_run(s,p,'MKIMAGE');done('MKIMAGE: P');s.key(b'2');done('Size: 1');s.key(b'1');done('Image base name');s.key(b'\x7f'*3);s.type('EMPTY');s.key(RET);done('Created EMPTY: 280')
            s.select('EMPTY.2MG',40);s.key(RET);p.stable()
            s.ok('MKIMAGE produit une image ProDOS navigable et vide',s.has('EMPTY.2MG') and not s.has('Cannot'), '\n'.join(s.rows()[:5]))
            s.ok('les six surcouches respectent la pile reservee',p.peek(floor,8)==b'\xa5'*8)
            p.eject(1)
        im=Image(target.read_bytes())
        def read(path):return im.read(entry(im,path))
        s.ok('SYNC contenu et fichiers destination conserves',read('DST/NEW.TXT')==files['SRC/NEW.TXT'] and read('DST/OLDER.TXT')==files['SRC/OLDER.TXT'] and read('DST/KEEP.TXT')==b'keep me\r')
        s.ok('SYNC copie recursive exacte',read('DST/DIR/NEST.TXT')==files['SRC/DIR/NEST.TXT'])
        s.ok('UNDELETE recupere chaque octet du fichier sapling',read('DST/RECOVER/GONE.TXT')==files['SRC/GONE.TXT'])
        s.ok('RESCUE contenu exact et journal complet',read('DST/RECOVER/SALVAGE.REC')==files['SRC/NEW.TXT'] and b'COMPLETE' in read('DST/RECOVER/SALVAGE.LOG'))
        return ok_all(s,'six')

if __name__=='__main__':raise SystemExit(main())
