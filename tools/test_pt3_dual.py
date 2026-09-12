"""Real assembly: two independently evolving PT3 states and two AY buses."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_pt3_volume import HARNESS,PLUGINS
C=HARNESS[:HARNESS.index('static int run(')]+r'''
extern unsigned pt_base;
extern unsigned char pt_chip,pt_dual,pt_running,pt_cache_pages[8];
static unsigned char init_saved[512];
static unsigned char* reclaimed;
void pt_swap(void),pt_silence(void);
void __fastcall__ pt_play_tables(unsigned char*);
static unsigned char second_tables[512], songs[2][512], expected[2][8][14], results[2][8];
static unsigned char index;
static void select_song(void){
 pt_swap();index^=1;pt_base=index?512:0;pt_chip=index?128:0;
 pt_play_tables(index?second_tables:tables);
}
int main(void){
 unsigned char a,b,k,f,mode;
 unsigned i;
 reclaimed=(unsigned char*)((unsigned)pt_cache_pages[3]<<8);memcpy(init_saved,reclaimed,512);
 for(mode=0;mode<4;++mode){
  memcpy(reclaimed,init_saved,512);pt_running=0;
  for(k=0;k<2;++k){
   fixture(k?'7':'3',k?4:9,k?12:6,mode);song[99]=k?2:0;
   memset(song+320,0,192);memcpy(songs[k],song,512);
   pt_base=0;pt_end=512;
   if(pt_init())return 1;
   for(f=0;f<8;++f){results[k][f]=pt_frame();memcpy(expected[k][f],pt_regs,14);}
  }
  memcpy(song,songs[0],512);memcpy(song+512,songs[1],512);
  pt_pages[0]=0x80;pt_pages[1]=0x81;pt_pages[2]=0x82;pt_pages[3]=0x83;
  index=pt_base=pt_chip=0;pt_dual=1;pt_end=512;
  pt_tables(tables);if(pt_init())return 2;
  select_song();pt_tables(second_tables);if(pt_init())return 3;
  select_song();pt_hw_start(4);pt_running=6;memset(reclaimed,0xd7,512);
  for(f=0;f<8;++f)for(k=0;k<2;++k){
   a=pt_frame();b=results[k][f];
   if(a!=b||memcmp(expected[k][f],pt_regs,14)){
    printf("mode %u frame %u chip %u result %u/%u\n",mode,f,k,a,b);return 4;
   }
   pt_output();
   for(i=0;i<13;++i)if(emitted[k*14+i]!=pt_regs[i])return 5;
   select_song();
  }
  for(i=0;i<512;++i)if(reclaimed[i]!=0xd7)return 7;
  pt_silence();
  for(k=0;k<2;++k)if(emitted[k*14+7]!=63||emitted[k*14+8]||emitted[k*14+9]||emitted[k*14+10])return 6;
 }
 puts("dual contexts match independent decodes; both AY buses silenced");return 0;
}
'''
@unittest.skipUnless(shutil.which('cl65') and shutil.which('sim65'),'needs cc65')
class Dual(unittest.TestCase):
 def test_contexts_and_both_chips(self):
  with tempfile.TemporaryDirectory(prefix='pt3-dual-') as d:
   t=Path(d);(t/'main.c').write_text(C)
   for cpu in ('sim6502','sim65c02'):
    s=(PLUGINS/'pt3.s').read_text().replace('PT3_LOC=$3700','PT3_LOC=$8000').replace('.include "pt3lib/init.inc"', '.align 256\n.include "pt3lib/init.inc"')
    s='PT3_HEADER_XOR=$02\n'+s
    s=s.replace(' pla\n iny\n sta (ptr1),y\n',' pla\n ldy ptr1\n beq :+\n sta _emitted+14,x\n jmp :++\n: sta _emitted,x\n: ldy #1\n sta (ptr1),y\n')
    s+='\n.export _notes, _emitted\n_notes=note_a\n.segment "BSS"\n_emitted: .res 28\n'
    (t/'pt3.s').write_text(s)
    r=subprocess.run(['cl65','-C',str(PLUGINS.parents[1]/'sdk/pt3-sim.cfg'),'-t',cpu,'-O','--asm-include-dir',str(PLUGINS),'-o',str(t/'test'),str(t/'main.c'),str(t/'pt3.s')],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stderr)
    r=subprocess.run(['sim65',str(t/'test')],capture_output=True,text=True,timeout=60)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
