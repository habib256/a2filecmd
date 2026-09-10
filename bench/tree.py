#!/usr/bin/env python3
"""TREE must finish a complete XL root scan, with exact recursive totals."""
import sys,tempfile
from pathlib import Path
from pom2 import Pom2,Session,BUILD,ROOT,VERSION
from xplug import menu_run,ESC,ok_all
sys.path.insert(0,str(ROOT/'tools'))
from prodos_read import Image

def main():
    cpu='6502' if BUILD.name=='build-6502' else '65C02'
    data=(ROOT/'dist'/f'A2FILECMD-{cpu}-XL-{VERSION}.2mg').read_bytes()[64:]
    files=[size for name,kind,size in Image(data).walk() if kind!='DIR']
    with tempfile.TemporaryDirectory(prefix='a2fc-tree-') as t:
        disk=Path(t)/'XL.hdv';disk.write_bytes(data)
        with Pom2(disk,port=6854) as p:
            s=Session(p);s.boot();stack=p.peek(0x80,2)
            menu_run(s,p,'TREE');pages=0
            while True:
                s.wait(lambda:s.has('SPACE Next') or s.has('TREE complete') or s.has('INCOMPLETE'),'TREE page',90);p.stable()
                if not s.has('SPACE Next'):break
                s.key(b' ');pages+=1
                if pages>30:raise AssertionError('TREE did not finish')
            s.ok('XL root finishes without false incomplete warning',s.has('TREE complete') and not s.has('INCOMPLETE'),'\n'.join(s.rows()))
            s.key(ESC);p.stable()
            expected=f'TREE: {len(files)} files, {sum(files)} bytes'
            s.ok('exact recursive file count and sizes',s.has(expected),s.rows()[22])
            s.ok('paginated traversal and stack restored',pages>0 and p.peek(0x80,2)==stack)
        s.ok('XL unchanged',disk.read_bytes()==data)
        return ok_all(s,'tree')
if __name__=='__main__':raise SystemExit(main())
