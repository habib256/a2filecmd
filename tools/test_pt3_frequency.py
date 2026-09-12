"""Compare real assembly tables/AY tones with archived upstream full tables.
Reference: deater/vmw-meter ay-3-8910/pt3/pt3_lib.c, fetched 2026-09-12.
The reference JSON holds the published 96 periods, not generated seeds.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_pt3_volume import HARNESS, PLUGINS

C = HARNESS[:HARNESS.index('static int run(')] + r'''
int main(void) {
 unsigned char v,t,k,note;
 unsigned i,want,got;
 pt_hw_start(4);
 for(v=0;v<12;++v) for(t=0;t<4;++t) for(note=0;note<96;++note) {
  fixture(v<10?'0'+v:'x',255,15,0); song[99]=t;
  song[240]=song[260]=song[280]=0x50+note;
  if(pt_init()) return 1;
  k=t==1?2:t==0?(v<=3?0:1):t==2?(v<=3?3:4):(v<=3?5:6);
  for(i=0;i<96;++i) if((tables[i]|((unsigned)tables[96+i]<<8))!=ref[k][i]) {
   printf("table version %u type %u note %u got %u want %u\n",v,t,i,tables[i]|((unsigned)tables[96+i]<<8),ref[k][i]);return 2;
  }
  if(pt_frame()) return 3;
  pt_output(); want=ref[k][note];
#ifdef CONVERTED
  want=(want*9UL+8)/16;
#endif
  for(i=0;i<3;++i) {
   got=pt_regs[2*i]|((unsigned)pt_regs[2*i+1]<<8);
   if(got!=want) {printf("tone %u != %u\n",got,want);return 4;}
  }
  for(i=448;i<512;++i) if(tables[i]!=0xa5)return 5;
 }
 puts("all tables and 96 AY tones match");return 0;
}
'''

@unittest.skipUnless(shutil.which('cl65') and shutil.which('sim65'), 'needs cc65')
class Frequency(unittest.TestCase):
 def test_all_tables_and_tones(self):
  data=json.loads((Path(__file__).with_name('pt3_frequency_reference.json')).read_text())
  values=[data[k] for k in ('PT_33_34r','PT_34_35','ST','ASM_34r','ASM_34_35','REAL_34r','REAL_34_35')]
  reference='static const unsigned ref[7][96]={'+','.join('{'+','.join(map(str,v))+'}' for v in values)+'};\n'
  with tempfile.TemporaryDirectory(prefix='pt3-freq-') as directory:
   tmp=Path(directory)
   for cpu in ('sim6502','sim65c02'):
    for converted in (False,True):
     with self.subTest(cpu=cpu,converted=converted):
      (tmp/'main.c').write_text(('#define CONVERTED\n' if converted else '')+reference+C)
      source=(PLUGINS/'pt3.s').read_text().replace('PT3_LOC=$3700','PT3_LOC=$8000').replace('.include "pt3lib/init.inc"', '.align 256\n.include "pt3lib/init.inc"')
      if not converted:source='PT3_DISABLE_FREQ_CONVERSION=1\nPT3_DISABLE_ENABLE_FREQ_CONVERSION=1\n'+source
      source+='\n.export _notes, _emitted\n_notes=note_a\n.segment "BSS"\n_emitted: .res 14\n'
      (tmp/'pt3.s').write_text(source)
      r=subprocess.run(['cl65','-C',str(PLUGINS.parents[1]/'sdk/pt3-sim.cfg'),'-t',cpu,'-O','--asm-include-dir',str(PLUGINS),'-o',str(tmp/'test'),str(tmp/'main.c'),str(tmp/'pt3.s')],capture_output=True,text=True)
      self.assertEqual(r.returncode,0,r.stderr)
      r=subprocess.run(['sim65',str(tmp/'test')],capture_output=True,text=True,timeout=120)
      self.assertEqual(r.returncode,0,r.stdout+r.stderr)

if __name__=='__main__':unittest.main()
