#!/usr/bin/env python3
"""A BATCH overlay without an entry must restore both panel tables and marks."""
import tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,TAB,ok_all
from pom2 import BUILD
from roi import pair,mark

def main():
 bad=bytearray((BUILD/'A2FILE.CODE.BIN.BATCH').read_bytes());bad[3:5]=b'\0\0'
 files={'A2FILE/BATCH.PLG#061B00':bytes(bad),'SRC/A#040000':b'original A','SRC/C#040000':b'original C','DST/KEEP#040000':b'original target'}
 with tempfile.TemporaryDirectory(prefix='batch-missing-') as t:
  with boot_hd(Path(t),files,port=6897) as(p,s):
   pair(s,p,'DST','SRC');s.key(TAB);mark(s,p,40);menu_run(s,p,'MOVE');p.stable()
   s.wait(lambda:s.has('Batch unavailable'),'missing entry refused')
   rows=s.rows()[2:20]
   s.ok('right source names and marks restored',all(any(r[40:58].startswith(n+' ') and '*' in r[40:58] for r in rows) for n in ('A','C')))
   s.ok('left destination remains readable',any(r.startswith('KEEP ') for r in rows))
   s.ok('no list created',not s.has('A2MOVE.LST  '))
 return ok_all(s,'batch missing entry')
if __name__=='__main__':raise SystemExit(main())
