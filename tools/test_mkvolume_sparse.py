"""Disposable build volumes: sparse pointers, exact bytes and allocation counts."""
import tempfile,unittest
from pathlib import Path
from mkvolume import Volume
from prodos_read import Image
class Sparse(unittest.TestCase):
 def test_seed_sapling_tree_and_partial_last_block(self):
  with tempfile.TemporaryDirectory(prefix='sparse-volume-') as t:
   p=Path(t);sources={'SEED.BIN':bytes(17),'ZERO.BIN':bytes(1024),'MIX.BIN':b'A'*512+bytes(512)+b'Z'*9,'TREE.BIN':bytes(131072)+b'Q'+bytes(1000)}
   for n,d in sources.items():(p/n).write_bytes(d)
   dense=Volume('TEST',4000,b'BOOT',(0,0));dense.build(p)
   sparse=Volume('TEST',4000,b'BOOT',(0,0),sparse=True);sparse.build(p)
   self.assertLess(sparse.next_free,dense.next_free)
   for v in (dense,sparse):
    im=Image(bytes(v.image));self.assertEqual(im.free_blocks(),4000-v.next_free)
    used=7
    for e in im.entries(2):
     name=e[1:1+(e[0]&15)].decode();d=sources[name+'.BIN'];self.assertEqual(im.read(e),d)
     count=int.from_bytes(e[0x13:0x15],'little');used+=count
     if v is sparse and name=='ZERO':self.assertEqual(count,1)
    self.assertEqual(used,v.next_free)
 def test_overflow_never_produces_an_image(self):
  with tempfile.TemporaryDirectory(prefix='sparse-overflow-') as t:
   p=Path(t);(p/'DATA.BIN').write_bytes(b'X'*8192)
   with self.assertRaises(SystemExit):Volume('TEST',10,b'',(0,0),sparse=True).build(p)
if __name__=='__main__':unittest.main()
