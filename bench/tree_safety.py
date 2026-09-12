#!/usr/bin/env python3
"""Deep recursive copy/delete must refuse before stack corruption or writes."""
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
 for depth in [20,3]:
  with tempfile.TemporaryDirectory(prefix='tree-safe-') as t:
   files={'TREE/'+('Z/'*depth)+'KEEP#040000':b'keep deepest bytes',
          'TREE/A.FIRST#040000':b'keep this before descending', 'DEST/NOTE#040000':b'destination original'}
   with boot_hd(Path(t),files,port=6904) as(p,s):
    original=Path(p.hdv).read_bytes();select_tree(p,s,'TREE')
    floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8)
    s.key(b'C');s.wait(lambda:s.has('copied') or s.has('Directory unreadable'),'recursive copy',60);p.stable()
    s.ok(f'depth {depth} copy stays within stack',p.peek(floor,8)==b'\xA5'*8)
    if depth==20:
     s.ok('deep copy refused before transfer',s.has('Directory unreadable'))
     s.select('TREE');s.key(b'D');s.wait(lambda:s.has('Delete TREE'),'delete confirmation');s.key(b'Y')
     s.wait(lambda:s.has('Directory unreadable'),'deep delete refusal',60);p.stable()
     s.ok('deep delete stays within stack',p.peek(floor,8)==b'\xA5'*8)
   if depth==20:s.ok('refused copy and delete preserve every disk byte',Path(p.hdv).read_bytes()==original)
   else:
    leaf=['TREE']+['Z']*depth+['KEEP']
    s.ok('ordinary recursive copy preserves source and destination bytes',
         contents(Path(p.hdv),leaf)==b'keep deepest bytes' and
         contents(Path(p.hdv),['DEST']+leaf)==b'keep deepest bytes' and
         contents(Path(p.hdv),['DEST','NOTE'])==b'destination original')
   checks+=s.checks
 s.checks=checks
 return ok_all(s,'recursive stack safety')
if __name__=='__main__':raise SystemExit(main())
