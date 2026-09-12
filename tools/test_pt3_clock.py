"""Execute the shipped replacement policy on both CPUs, including stale tags."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
C=r'''
#include <stdio.h>
#include <string.h>
unsigned char pt_pages[256],pt_cache_pages[8],pt_running;
extern unsigned char pt_slots[8],pt_next;
unsigned char pt_victim(void);
static unsigned char original[256];
static void fixture(unsigned char n,unsigned mask,unsigned char start){
 unsigned char i;
 memset(pt_pages,0,sizeof pt_pages);pt_pages[0]=0x77;
 for(i=0;i<n;++i){pt_cache_pages[i]=0x20+i;pt_slots[i]=20+i;pt_pages[20+i]=(0x20+i)|((mask&(1u<<i))?64:0);}
 pt_running=n;pt_next=start;memcpy(original,pt_pages,sizeof pt_pages);
}
int main(void){
 unsigned mask;unsigned char n,start,i,got,expected;
 for(mask=0;mask<sizeof cases/sizeof cases[0];++mask){
  const unsigned char* c=cases[mask];
  n=c[0];start=c[2];fixture(n,c[1],start);
  got=pt_victim();if(got!=c[3]||pt_next!=c[4])return 1;
  for(i=0;i<n;++i){
   expected=i==c[3]?0:(0x20+i)|((c[5]&(1u<<i))?64:0);
   if(pt_pages[20+i]!=expected)return 2;
  }
  if(pt_pages[0]!=0x77)return 3;
 }
 for(n=2;n<=8;++n)for(start=0;start<n;++start){
  fixture(n,255,start);pt_slots[start]=0;
  if(pt_victim()!=start||memcmp(pt_pages,original,256))return 4;
  fixture(n,255,start);pt_slots[start]=20+(start+1)%n;
  if(pt_victim()!=start||memcmp(pt_pages,original,256))return 5;
  fixture(n,255,start);pt_slots[start]=255;
  if(pt_victim()!=start||memcmp(pt_pages,original,256))return 6;
 }
 puts("second-chance victims, full passes, stale aliases and headers preserved");return 0;
}
'''
@unittest.skipUnless(shutil.which('cl65') and shutil.which('sim65'),'needs cc65')
class Clock(unittest.TestCase):
 def test_real_policy_exhaustively(self):
  with tempfile.TemporaryDirectory(prefix='pt3-clock-') as d:
   p=Path(d)
   cases=[]
   for n in range(1,9):
    for mask in range(1<<n):
     for start in range(n):
      order=[(start+k)%n for k in range(n)]
      cold=[k for k in order if not mask & (1<<k)]
      victim=cold[0] if cold else start
      visited=order[:order.index(victim)] if cold else order
      remaining=mask & ~(1<<victim)
      for k in visited:remaining &= ~(1<<k)
      cases.append((n,mask,start,victim,(victim+1)%n,remaining))
   oracle='static const unsigned char cases[][6]={'+','.join('{'+','.join(map(str,c))+'}' for c in cases)+'};\n'
   (p/'main.c').write_text(C.replace('int main(void){',oracle+'int main(void){'))
   (p/'cache.s').write_text('.import _pt_pages, _pt_cache_pages, _pt_running\n.include "pt3lib/cache.inc"\n')
   for cpu in ('sim6502','sim65c02'):
    r=subprocess.run(['cl65','-t',cpu,'-O','--asm-include-dir',str(ROOT/'src/plugins'),'-o',str(p/'test'),str(p/'main.c'),str(p/'cache.s')],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stderr)
    r=subprocess.run(['sim65',str(p/'test')],capture_output=True,text=True,timeout=30)
    self.assertEqual(r.returncode,0,r.stdout+r.stderr)
if __name__=='__main__':unittest.main()
