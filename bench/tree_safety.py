#!/usr/bin/env python3
"""Tree copy and delete walk without recursion: deep trees are walked within
the stack, a tree beyond the entry pool is refused before any write, and a
destination path beyond ProDOS's 64 characters stops the copy cleanly."""
import tempfile
from pathlib import Path
from xplug import boot_hd,RET,TAB,ok_all
from data_safety import contents

def select_tree(p,s,name):
 s.key(b'/');s.select('/WORKHD');s.key(RET)
 s.key(TAB);s.key(b'/');s.select('/WORKHD',40);s.key(RET);s.select('DEST',40);s.key(RET);s.key(TAB)
 s.select(name);p.stable()

def main():
 checks=[]
 for depth in [18,3,20,'wide']:
  with tempfile.TemporaryDirectory(prefix='tree-safe-') as t:
   if depth=='wide':   # 200 files beside a directory of 20: 221 entries along one path, over the 213-entry pool
    files={'TREE/F%03d#040000'%k:b'x' for k in range(200)}
    files.update({'TREE/SUB/G%02d#040000'%k:b'y' for k in range(20)})
    files.update({'DEST/NOTE#040000':b'destination original'})
   else:
    files={'TREE/'+('Z/'*depth)+'KEEP#040000':b'keep deepest bytes',
           'TREE/A.FIRST#040000':b'keep this before descending', 'DEST/NOTE#040000':b'destination original'}
   with boot_hd(Path(t),files,port=6904) as(p,s):
    original=Path(p.hdv).read_bytes();select_tree(p,s,'TREE')
    floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8)
    s.key(b'C');s.wait(lambda:s.has('copied') or s.has('Directory unreadable') or s.has('Failed; source kept'),'tree copy',120);p.stable()
    s.ok(f'{depth} copy stays within stack',p.peek(floor,8)==b'\xA5'*8)
    if depth=='wide':
     s.ok('a tree beyond the pool is refused before transfer',s.has('Directory unreadable'))
     s.select('TREE');s.key(b'D');s.wait(lambda:s.has('Delete TREE'),'delete confirmation');s.key(b'Y')
     s.wait(lambda:s.has('Directory unreadable'),'wide delete refusal',60);p.stable()
     s.ok('wide delete stays within stack',p.peek(floor,8)==b'\xA5'*8)
    elif depth==20:
     # /WORKHD/DEST/TREE/Z x20/A2FC.COPY: the recoverable copy's temporary name passes 64 characters
     s.ok('a destination path beyond 64 characters stops the copy, source kept',s.has('Failed; source kept'))
     s.select('TREE');s.key(b'D');s.wait(lambda:s.has('Delete TREE'),'delete confirmation');s.key(b'Y')
     s.wait(lambda:s.has('deleted'),'20-level delete',120);p.stable()
     s.ok('20-level delete stays within stack',p.peek(floor,8)==b'\xA5'*8)
     s.ok('the 20-level tree is gone',not any(r.startswith('TREE/') for r in s.rows()))
    else:
     s.ok(f'{depth}-level copy completes',s.has('copied'))
   if depth=='wide':s.ok('refused copy and delete preserve every disk byte',Path(p.hdv).read_bytes()==original)
   elif depth==20:
    s.ok('the source of the stopped copy was kept until deleted, and DEST/NOTE is intact',
         contents(Path(p.hdv),['DEST','NOTE'])==b'destination original')
   else:
    leaf=['TREE']+['Z']*depth+['KEEP']
    s.ok(f'{depth}-level copy preserves source and destination bytes',
         contents(Path(p.hdv),leaf)==b'keep deepest bytes' and
         contents(Path(p.hdv),['DEST']+leaf)==b'keep deepest bytes' and
         contents(Path(p.hdv),['DEST','NOTE'])==b'destination original')
   checks+=s.checks
 s.checks=checks
 return ok_all(s,'tree walk safety')
if __name__=='__main__':raise SystemExit(main())
