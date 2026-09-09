#!/usr/bin/env python3
"""DISKCMP: full exact comparison with named single-drive swaps."""
import os
import tempfile
from pathlib import Path
from six import make_disk
from xplug import boot_hd,menu_run,RET,ok_all


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-diskcmp-') as t:
        tmp=Path(t);first=make_disk(tmp);before=first.read_bytes();second=tmp/'SECOND.po'
        d=bytearray(before);d[1029:1035]=b'SECOND';second.write_bytes(d)
        with boot_hd(tmp,{},port=6843,floppy2=first,plugins=['diskcmp']) as (p,s):
            s.key(b'/');s.select('/TARGET');menu_run(s,p,'DISKCMP');s.key(b'S')
            s.wait(lambda:s.has('Second volume name'),'nom cible');s.type('SECOND');s.key(RET)
            s.wait(lambda:s.has('Insert /SECOND S6,D2'),'demande cible')
            s.ok('demande nom du disque et lecteur initial',s.has('Insert /SECOND S6,D2'))
            # Move both roles to drive 1; all subsequent exchanges use it.
            s.key(b'1');s.wait(lambda:s.has('Insert /SECOND S6,D1'),'changement lecteur')
            p.eject(1);p.insert(0,str(second));s.key(RET)
            s.wait(lambda:s.has('Insert /TARGET'),'premiere passe source')
            swaps=0
            while True:
                s.wait(lambda:s.has('Insert /TARGET') or s.has('Insert /SECOND') or s.has('differing blocks') or s.has('Read error'),'echange ou resultat',30)
                if s.has('differing blocks') or s.has('Read error'):break
                name='TARGET' if s.has('Insert /TARGET') else 'SECOND'
                assert s.has('S6,D1'), '\n'.join(s.rows())
                p.insert(0,str(first if name=='TARGET' else second));s.key(RET,0.03)
                # Wait for this prompt to disappear before accepting the next.
                s.wait(lambda:not s.has('Insert /'+name),'lecture apres insertion',30)
                swaps+=1
                if swaps>282:raise AssertionError('swap loop did not advance')
            s.ok('comparaison complete exacte sur un lecteur',s.has('1 differing blocks; first at 2.'),s.rows()[22])
            s.ok('deux blocs compares par echange',swaps==280,swaps)
            p.eject(0)
        s.ok('les deux images sources sont intactes',first.read_bytes()==before and second.read_bytes()==d)
        return ok_all(s,'disksingle')
if __name__=='__main__':raise SystemExit(main())
