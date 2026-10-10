"""Native IDENT relay: overwritten code, ABI, stack and preserved sample."""
import re,subprocess,unittest
from test_mcs_handoff import Handoff,ROOT
class IdentHandoff(Handoff):
 @classmethod
 def setUpClass(cls):
  cls.builds=[]
  for arch,d in (('enh','build'),('6502','build-6502')):
   names=('ident','idread','idformats')
   subprocess.run(['make','ARCH='+arch]+[d+'/'+n+'.PLG' for n in names],cwd=ROOT,check=True,capture_output=True)
   for n in names:
    l={m[2]:int(m[1],16) for m in re.finditer(r'al ([0-9A-Fa-f]{6}) \.([^\s]+)',(ROOT/d/(n+'.lbl')).read_text())}
    old=(ROOT/d/(n+'.PLG')).read_bytes();new=(ROOT/d/'idformats.PLG').read_bytes()
    cls.builds.append((old,l,new))
 def run_handoff(self,build,fault=None,payload=None):super().run_handoff(build,fault,payload,ident=True)
 def test_bad_headers_truncation_trailing_bytes_and_entry(self):
  for build in self.builds:
   original=build[2]
   for n in (0,4,8,255,len(original)-1):self.run_handoff(build,payload=original[:n])
   self.run_handoff(build,payload=original+b'X');self.run_handoff(build,payload=original+bytes(0x2500))
   for off,value in ((0,0),(1,0),(2,5),(5,0),(6,0),(7,2),(7,129 if original[7]==1 else 1)):
    bad=bytearray(original);bad[off]=value;self.run_handoff(build,payload=bad)
   for target in (0x1b00,0x1b07,0x4000,0x1b00+len(original)):
    bad=bytearray(original);bad[3:5]=target.to_bytes(2,'little');self.run_handoff(build,payload=bad)
if __name__=='__main__':unittest.main()
