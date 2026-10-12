"""Real C media readers: bounded AUX, consent, complete reads and both CPUs."""
import hashlib,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from test_pfswrite import ROOT
CORPUS=Path(os.environ.get('A2FC_V1_CORPUS','/tmp/a2fc-v1-corpus'))
H=r'''
#define __fastcall__
#define PLUGIN_HOST
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#undef strcpy
#undef memcpy
struct A2fcApi;
static int fault,reads,opens,closes,ioerr,consents,key_at;
static const char* movie_keys;
static unsigned int frames,writes;
static unsigned char aux[16384];
static const char* source_path;
static int ferr(FILE* f){return ioerr || ferror(f);}
#define ferror ferr
#include MEDIA_SOURCE
#undef ferror
#ifdef GRAPHICS
void vg_write(unsigned char c){if(vg_addr<0x4000 || vg_addr>=0x8000)abort();aux[vg_addr-0x4000]=c;++writes;}
void vg_read(void){if(vg_addr<0x4000 || vg_addr+vg_count>0x8000)abort();memcpy(vg_buf,aux+vg_addr-0x4000,vg_count);}
void plugin_entry(const struct A2fcApi* a){(void)a;}
#else
void mv_host_display(const unsigned char* p){unsigned int i,sum=0;++frames;for(i=0;i<1920;++i){if(p[i]>15)abort();sum=(sum*31+p[i])&65535;}printf("frame %u %u\n",frames,sum);}
#endif
static unsigned char consent(void){++consents;return fault!=8;}
static char key(void){if(movie_keys){unsigned char k=movie_keys[key_at];if(k){++key_at;return k;}return 27;}return frames<2?32:27;}
#ifndef GRAPHICS
unsigned char mv_key_wait(unsigned char units){
 if(units!=1 && units!=4 && units!=8)abort();
 if(movie_keys && strpbrk(movie_keys,"123"))printf("wait %u\n",(unsigned int)units);
 if(movie_keys && movie_keys[key_at]=='~'){++key_at;return 0;}
 return 1;
}
#endif
static void clear(void){}
static FILE* opn(const char* p,const char* m){++opens;ioerr=0;if(strcmp(m,"rb"))abort();if(fault==1 || (fault==7 && opens==2))return NULL;return fopen(p,m);}
static size_t rd(void* p,size_t z,size_t n,FILE* f){++reads;if((fault==2 && reads==2)||(fault==5 && opens==2)||(fault==6 && reads==5)||(fault==12 && key_at)
#ifndef GRAPHICS
 || (fault==14 && frames>=mv_total && mv_draw)
#endif
 ){ioerr=1;return 0;}return fread(p,z,n,f);}
static int close_(FILE* f){++closes;return fclose(f) || fault==3 || (fault==4 && closes==2)?EOF:0;}
static int seek_(FILE* f,long at,int mode){
 if(fault==9 || (fault==11 && key_at))return -1;
#ifndef GRAPHICS
 if(fault==13 && frames>=mv_total && mv_draw)return -1;
#endif
#ifdef __CC65__
 {unsigned char buf[64];FILE* again;unsigned int n;if(mode!=SEEK_SET || at<0 || fclose(f))return -1;again=fopen(source_path,"rb");if(again!=f)return -1;while(at){n=at>64?64:(unsigned int)at;if(fread(buf,1,n,f)!=n)return -1;at-=n;}return 0;}
#else
 return fseek(f,at,mode);
#endif
}
int main(int argc,char**argv){
 struct A2fcApi api;struct Entry e;char note[80],reselect[80];unsigned char flags=0;unsigned int i;
 memset(&api,0,sizeof api);memset(&e,0,sizeof e);memset(note,0,sizeof note);memset(aux,0xA5,sizeof aux);
 source_path=argv[1];fault=atoi(argv[2]);movie_keys=argc>3?argv[3]:NULL;e.type=6;e.size=1;strcpy(e.name,"SAMPLE");
 api.full=(char*)source_path;if(fault==10)api.full="/RAM/PICTURE";api.selected=&e;api.note=note;api.reselect=reselect;api.fopen=opn;api.fread=rd;api.fclose=close_;api.fseek=seek_;api.strcpy=strcpy;api.aux_consent=consent;api.wait_key=key;api.clrscr=clear;
#ifdef GRAPHICS
 flags=vg_run(&api);if(flags&4)fwrite(aux,1,16384,stdout);
#endif
#ifndef GRAPHICS
 plugin_entry(&api);for(i=0;i<16384;++i)if(aux[i]!=0xA5)abort();
#endif
 fprintf(stderr,"%u %u %d %d %d %s\n",flags,writes,opens,closes,consents,note);return 0;
}
'''
def pcs():
 # Independent square and a complete zero bitmap, not copied from PCS.
 obj=bytes([1,14,4,10,20,20,10,10,10,20,20])
 return bytes(28)+bytes([1,len(obj)])+obj+b'\x01\x00'*32+b'\x01\x01'
def pcs_many():
 return bytes(28)+bytes([255])+bytes([9])*255+bytes([1,0,3,0,0,0,0,0,0])*255+b'\x01\x00'*32+b'\x01\x01'
def pcs_pattern():
 bitmap=bytes((i*13)&127 for i in range(8192))
 data=pcs()[:41]+b''.join(b'\0'+bitmap[i:i+256] for i in range(0,8192,256))+b'\x01\x01'
 preview=bytearray(bitmap)
 for y in range(10,20):
  for x in range(10,21):
   at=((y&7)<<10)|((y&56)<<4)|((y>>6)*40)
   preview[at+x//7]|=128|(1<<(x%7))
 return data,bitmap,bytes(preview)
def movie(dx=0,width=10,height=10,background=0):
 def cmd(t,p=b''):return bytes([t])+len(p).to_bytes(2,'little')+p
 return cmd(1,bytes([0,0,width,height])+bytes(252))+cmd(2,b'\x00\x00'+b'\xff'*8192)+cmd(3,b'\x00\x00'+bytes([background])*8192)+cmd(6)+cmd(5,bytes([1,1,dx,0,0x30,0xC0]))+cmd(0)+cmd(7)

def movie_hash(dx,width,height):
 dx=dx-256 if dx>=140 else dx
 result=0
 for y in range(48):
  for x in range(40):
   sx=x*7//2
   pixel=15 if y*4<height and dx<=sx<dx+width and sx-dx<140 else 0
   result=(result*31+pixel)&65535
 return result
def movie_navigation(positions=(0,14,28),background=0):
 data=movie(background=background);at=3+256+2*(3+8194)+3
 frames=b''.join(bytes([1,1,dx,0,0x30]) for dx in positions)+b'\xc0'
 return data[:at]+b'\x05'+len(frames).to_bytes(2,'little')+frames+b'\x00\x00\x00\x07\x00\x00'
def bad_movie_planes():
 data=movie();second=3+256+3+8194
 for at in (259,second):
  for start in (1,8193):
   bad=bytearray(data);bad[at+3:at+5]=start.to_bytes(2,'little');yield bytes(bad)
class Media(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='v1media-');cls.p=Path(cls.tmp.name);(cls.p/'h.c').write_text(H);cls.exes={}
  for name in ('dgmagi','pcsvw','mvmovie'):
   exe=cls.p/name;defines=['-DMEDIA_SOURCE="src/plugins/'+name+'.c"']+([] if name=='mvmovie' else ['-DGRAPHICS'])
   subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),*defines,str(cls.p/'h.c'),'-o',str(exe)],check=True,capture_output=True);cls.exes[name]=exe
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def run_file(self,name,d,fault=0,exe=None,keys=None):
  src=self.p/'source';src.write_bytes(d)
  r=subprocess.run(([str(self.exes[name])] if exe is None else exe)+[str(src),str(fault)]+([] if keys is None else [keys]),check=True,capture_output=True,timeout=60)
  self.assertEqual(src.read_bytes(),d);status=r.stderr.decode().strip().split(' ',5);status[1]=str(int(status[1])&65535);return r.stdout,status
 def test_valid_and_bounds(self):
  for name,d in (('dgmagi',b'\x80\0\0\xA0\0\0\0'),('pcsvw',pcs()),('mvmovie',movie())):
   out,st=self.run_file(name,d);self.assertEqual(st[2:4],['2','2']);self.assertEqual(st[4],'0' if name=='mvmovie' else '1');self.assertTrue(out)
   if name=='dgmagi':self.assertEqual(len(out),16384)
 def test_validation_before_consent(self):
  for name,d in (('dgmagi',b'\x80\0\0\xA0\0\0\0'),('pcsvw',pcs()),('mvmovie',movie())):
   for bad in (b'',d[:-1],d+b'\xFF'*5):
    out,st=self.run_file(name,bad);self.assertFalse(out);self.assertEqual(st[0:2],['0','0']);self.assertEqual(st[4],'0');self.assertTrue(st[5])
   for fault in ((1,2,3,6) if name!='pcsvw' else (1,3)):
    # Short .DPC needs only two reads, so faults at later reads cannot fire.
    src=d if name!='dgmagi' else b'\x80\0\0\xA0\0\0\0'+bytes(2048)
    out,st=self.run_file(name,src,fault);self.assertFalse(out);self.assertEqual(st[1],'0');self.assertEqual(st[4],'0');self.assertIn('error',st[5])
 def test_refusal_reopen_read_close_seek(self):
  for name,d in (('dgmagi',b'\x80\0\0\xA0\0\0\0'),('pcsvw',pcs()),('mvmovie',movie())):
   if name!='mvmovie':
    out,st=self.run_file(name,d,10);self.assertFalse(out);self.assertEqual(st[:5],['0','0','0','0','0'])
    out,st=self.run_file(name,d,8);self.assertFalse(out);self.assertEqual(st[:2],['0','0']);self.assertEqual(st[2:5],['1','1','1'])
   for fault in (4,5,7):
    out,st=self.run_file(name,d,fault);self.assertTrue(st[5]);self.assertIn('error',st[5])
    if name!='mvmovie':self.assertEqual(st[0],'1');self.assertFalse(out)
   if name!='dgmagi':self.assertIn('error',self.run_file(name,d,9)[1][5])
 def test_embedded_movie_code_is_refused(self):
  d=movie();at=3+256+3+8194+3+8194
  bad=d[:at]+b'\x04\x01\x00\x60'+d[at:]
  out,st=self.run_file('mvmovie',bad);self.assertFalse(out);self.assertIn('Unsupported',st[5]);self.assertEqual(st[2:4],['1','1'])
 def test_movie_bitmap_bounds_before_display(self):
  for bad in bad_movie_planes():
   out,st=self.run_file('mvmovie',bad)
   self.assertFalse(out);self.assertIn('Unsupported',st[5]);self.assertEqual(st[2:5],['1','1','0'])
 def test_pcs_object_bounds_before_consent_and_maximum_count(self):
  for pos,value in ((29,8),(30,0),(30,11),(31,1),(31,18),(32,2),(32,65),(33,154),(37,192)):
   bad=bytearray(pcs());bad[pos]=value
   out,st=self.run_file('pcsvw',bytes(bad));self.assertFalse(out);self.assertEqual(st[1:5],['0','1','1','0']);self.assertIn('Malformed',st[5])
  out,st=self.run_file('pcsvw',pcs_many());self.assertEqual(out,bytes(16384));self.assertEqual(st[0],'13')
 def test_pcs_preserves_original_bitmap_for_object_toggle(self):
  data,bitmap,preview=pcs_pattern()
  out,st=self.run_file('pcsvw',data)
  self.assertEqual(out[8192:],bitmap);self.assertEqual(out[:8192],preview)
  self.assertEqual(st[0],'13');self.assertEqual(st[2:5],['2','2','1'])
 def test_dpc_coordinate_bounds_before_consent(self):
  valid=b'\x20\x81\x18\x30\xa2\x2f\xbf\0'
  out,st=self.run_file('dgmagi',valid);self.assertEqual(len(out),16384);self.assertEqual(st[0],'7')
  for bad in (valid[:4]+b'\xa2\x30\0\0',valid[:4]+b'\xa2\x2f\xc0\0',valid[:-1],valid+b'\x01'):
   out,st=self.run_file('dgmagi',bad);self.assertFalse(out);self.assertEqual(st[1:5],['0','1','1','0']);self.assertIn('Malformed',st[5])
 def test_movie_negative_and_edge_sprite_clipping(self):
  for dx in (0,139,140,250,255):
   for width in (1,10,140):
    out,st=self.run_file('mvmovie',movie(dx,width))
    self.assertEqual(out,f'frame 1 {movie_hash(dx,width,10)}\n'.encode())
    self.assertEqual(st[4],'0');self.assertNotIn('error',st[5]);self.assertNotIn('Malformed',st[5])
 def navigation(self,exe=None):
  data=movie_navigation()
  for keys,positions in ((' B R', [0,14,0,14,0]),('B', [0,0]),('  \x0b\x08R', [0,14,28,14,0,0]),('x', [0]),('   ', [0,14,28]),('  B  ', [0,14,28,14,28])):
   out,st=self.run_file('mvmovie',data,exe=exe,keys=keys)
   expected=''.join(f'frame {i+1} {movie_hash(dx,10,10)}\n' for i,dx in enumerate(positions)).encode()
   self.assertEqual(out,expected);self.assertEqual(st[2:5],['2','2','0']);self.assertNotIn('error',st[5]);self.assertNotIn('Malformed',st[5])
  for fault in (11,12):
   out,st=self.run_file('mvmovie',data,fault=fault,exe=exe,keys='B')
   self.assertEqual(out,f'frame 1 {movie_hash(0,10,10)}\n'.encode());self.assertIn('error',st[5]);self.assertEqual(st[2:5],['2','2','0'])
 def test_movie_previous_restart_boundaries_and_rewind_errors(self):self.navigation()
 def last_frame(self,exe=None):
  data=movie_navigation()
  for keys,positions in (('L',[0,28]),('lBRL',[0,28,14,0,28]),('LLB ',[0,28,28,14,28]),(' L ',[0,14,28])):
   out,st=self.run_file('mvmovie',data,exe=exe,keys=keys)
   expected=''.join(f'frame {i+1} {movie_hash(dx,10,10)}\n' for i,dx in enumerate(positions)).encode()
   self.assertEqual(out,expected);self.assertEqual(st[2:5],['2','2','0']);self.assertNotIn('error',st[5]);self.assertNotIn('Malformed',st[5])
  out,st=self.run_file('mvmovie',movie(),exe=exe,keys='LlR')
  self.assertEqual(out,(f'frame 1 {movie_hash(0,10,10)}\nframe 2 {movie_hash(0,10,10)}\nframe 3 {movie_hash(0,10,10)}\nframe 4 {movie_hash(0,10,10)}\n').encode())
  # Count/target must remain 16-bit across 255 frames; skip intermediate renders.
  positions=tuple(i%140 for i in range(300))
  out,st=self.run_file('mvmovie',movie_navigation(positions),exe=exe,keys='LB')
  self.assertEqual(out,''.join(f'frame {i+1} {movie_hash(dx,10,10)}\n' for i,dx in enumerate((0,19,18))).encode())
  self.assertNotIn('error',st[5]);self.assertNotIn('Malformed',st[5])
  for fault in (11,12):
   out,st=self.run_file('mvmovie',data,fault=fault,exe=exe,keys='L')
   self.assertEqual(out,f'frame 1 {movie_hash(0,10,10)}\n'.encode());self.assertIn('error',st[5]);self.assertEqual(st[2:5],['2','2','0'])
 def test_movie_last_frame_and_checked_replay(self):self.last_frame()
 def jump_frames(self,exe=None):
  positions=tuple(i%140 for i in range(300))
  for keys,indices in (('+',[0,10]),('++-',[0,10,20,10]),('-',[0,0]),('+-',[0,10,0]),
                       (' +--',[0,1,11,1,0]),('L+-',[0,299,299,289]),('L-R+',[0,299,289,0,10])):
   out,st=self.run_file('mvmovie',movie_navigation(positions),exe=exe,keys=keys)
   self.assertEqual(out,''.join(f'frame {i+1} {movie_hash(positions[n],10,10)}\n' for i,n in enumerate(indices)).encode())
   self.assertEqual(st[2:5],['2','2','0']);self.assertNotIn('error',st[5]);self.assertNotIn('Malformed',st[5])
  for count in (1,9,10,11,12):
   data=movie_navigation(tuple(range(count)))
   out,st=self.run_file('mvmovie',data,exe=exe,keys='++--')
   indices=(0,min(10,count-1),count-1,max(0,count-11),0)
   self.assertEqual(out,''.join(f'frame {i+1} {movie_hash(n,10,10)}\n' for i,n in enumerate(indices)).encode())
   self.assertNotIn('error',st[5]);self.assertNotIn('Malformed',st[5])
  for fault in (11,12):
   for key in ('+','-'):
    out,st=self.run_file('mvmovie',movie_navigation(),fault=fault,exe=exe,keys=key)
    self.assertEqual(out,f'frame 1 {movie_hash(0,10,10)}\n'.encode());self.assertIn('error',st[5]);self.assertEqual(st[2:5],['2','2','0'])
 def test_movie_ten_frame_jumps_counts_bounds_and_io(self):self.jump_frames()
 def background_toggle(self,exe=None):
  for bg in (0,0x2A,0xD5):
   def frame_hash(dx,actors):
    result=0
    for y in range(48):
     for x in range(40):
      sx=x*7//2;bit=sx*2
      pair=((bg>>(bit%7))&1)|(((bg>>((bit+1)%7))&1)<<1)
      color=(0,6,9,15)[pair] if bg&128 else (0,3,12,15)[pair]
      if actors and y*4<10 and dx<=sx<dx+10:color=15
      result=(result*31+color)&65535
    return result
   for keys,states in (('Oo',[(0,True),(0,False),(0,True)]),
                       ('O oOBOLoRO',[(0,True),(0,False),(14,False),(14,True),(14,False),(0,False),(0,True),(28,True),(28,False),(0,False),(0,True)]),
                       ('O+o-',[(0,True),(0,False),(28,False),(28,True),(0,True)])):
    out,st=self.run_file('mvmovie',movie_navigation(background=bg),exe=exe,keys=keys)
    self.assertEqual(out,''.join(f'frame {i+1} {frame_hash(dx,actors)}\n' for i,(dx,actors) in enumerate(states)).encode())
    self.assertEqual(st[2:5],['2','2','0']);self.assertNotIn('error',st[5]);self.assertLess(len(st[5]),80)
  for fault in (11,12):
   out,st=self.run_file('mvmovie',movie_navigation(),fault=fault,exe=exe,keys='O')
   self.assertEqual(out,f'frame 1 {movie_hash(0,10,10)}\n'.encode());self.assertIn('error',st[5]);self.assertEqual(st[2:5],['2','2','0'])
 def test_movie_background_toggle_pixels_navigation_and_io(self):self.background_toggle()
 def movie_mirrors(self,exe=None):
  for bg in (0,0x2A,0xD5):
   for dx,width in ((0,10),(139,10),(250,140)):
    data=movie(dx,width,background=bg)
    # Independent output-coordinate oracle, including clipped actors.
    def frame_hash(actors,flip):
     result=0;left=dx-256 if dx>=140 else dx
     for y in range(48):
      for x in range(40):
       sx=(39-x if flip&1 else x)*7//2;sy=(47-y if flip&2 else y)*4;bit=sx*2
       pair=((bg>>(bit%7))&1)|(((bg>>((bit+1)%7))&1)<<1)
       color=((0,6,9,15) if bg&128 else (0,3,12,15))[pair]
       if actors and sy<10 and left<=sx<left+width and sx-left<140:color=15
       result=(result*31+color)&65535
     return result
    keys='HvOhVoHh';actors=True;flip=0;states=[(actors,flip)]
    for key in keys.upper():
     if key=='O':actors=not actors
     else:flip^=1 if key=='H' else 2
     states.append((actors,flip))
    out,st=self.run_file('mvmovie',data,exe=exe,keys=keys)
    self.assertEqual(out,''.join(f'frame {i+1} {frame_hash(a,f)}\n' for i,(a,f) in enumerate(states)).encode())
    self.assertEqual(st[2:5],['2','2','0']);self.assertNotIn('error',st[5]);self.assertLess(len(st[5]),80)
  for keys,states in (('H BvLRh',[(0,0),(0,1),(14,1),(0,1),(0,3),(28,3),(0,3),(0,2)]),
                      ('V+-v',[(0,0),(0,2),(28,2),(0,2),(0,0)]),
                      ('HS~sV',[(0,0),(0,1),(14,1),(14,3)]),
                      ('HHVV',[(0,0),(0,1),(0,0),(0,2),(0,0)])):
   out,st=self.run_file('mvmovie',movie_navigation(),exe=exe,keys=keys)
   def scene_hash(dx,flip):
    pixels=[15 if y*4<10 and dx<=x*7//2<dx+10 else 0 for y in range(48) for x in range(40)]
    result=0
    for y in range(48):
     for x in range(40):result=(result*31+pixels[(47-y if flip&2 else y)*40+(39-x if flip&1 else x)])&65535
    return result
   self.assertEqual(out,''.join(f'frame {i+1} {scene_hash(dx,f)}\n' for i,(dx,f) in enumerate(states)).encode())
   self.assertNotIn('error',st[5])
  for fault in (11,12):
   for key in 'HV':
    out,st=self.run_file('mvmovie',movie_navigation(),fault=fault,exe=exe,keys=key)
    self.assertEqual(out,f'frame 1 {movie_hash(0,10,10)}\n'.encode());self.assertIn('error',st[5]);self.assertEqual(st[2:5],['2','2','0'])
 def test_movie_mirrors_pixels_clipping_background_navigation_and_io(self):self.movie_mirrors()
 def movie_autoplay(self,exe=None):
  data=movie_navigation()
  for keys,positions in (('S~~',[0,14,28]),('SS ',[0,14]),('S~s B',[0,14,28,14]),
                         ('S~B~',[0,14,0]),('S\x1b',[0]),('S~R',[0,14,0]),('S~L',[0,14,28])):
   out,st=self.run_file('mvmovie',data,exe=exe,keys=keys)
   self.assertEqual(out,''.join(f'frame {i+1} {movie_hash(dx,10,10)}\n' for i,dx in enumerate(positions)).encode())
   self.assertEqual(st[2:5],['2','2','0']);self.assertNotIn('error',st[5]);self.assertLess(len(st[5]),80)
  out,st=self.run_file('mvmovie',movie(),exe=exe,keys='S~')
  self.assertEqual(out,f'frame 1 {movie_hash(0,10,10)}\n'.encode());self.assertNotIn('error',st[5])
  for fault in (11,12):
   out,st=self.run_file('mvmovie',data,fault=fault,exe=exe,keys='S~')
   self.assertEqual(out,f'frame 1 {movie_hash(0,10,10)}\n'.encode());self.assertIn('error',st[5]);self.assertEqual(st[2:5],['2','2','0'])
  out,st=self.run_file('mvmovie',data,fault=4,exe=exe,keys='S~~')
  self.assertEqual(out,''.join(f'frame {i+1} {movie_hash(dx,10,10)}\n' for i,dx in enumerate((0,14,28))).encode());self.assertIn('error',st[5])
 def test_movie_autoplay_pause_interrupt_end_and_io(self):self.movie_autoplay()
 def movie_speed(self,exe=None):
  data=movie_navigation((0,14,28,42))
  cases=(('S1~2~3~',[('f',0),('w',4),('w',1),('f',14),('w',1),('w',4),('f',28),('w',4),('w',8),('f',42),('w',8)]),
         ('3S~s B S~',[('f',0),('w',8),('f',14),('w',8),('f',28),('f',14),('f',28),('w',8),('f',42),('w',8)]),
         ('132',[('f',0)]),('1SS ',[('f',0),('w',1),('f',14)]),
         ('S3B S~',[('f',0),('w',4),('w',8),('f',0),('f',14),('w',8),('f',28),('w',8)]))
  for keys,events in cases:
   out,st=self.run_file('mvmovie',data,exe=exe,keys=keys)
   expected=''.join(f'frame {sum(k=="f" for k,_ in events[:i+1])} {movie_hash(n,10,10)}\n' if k=='f' else f'wait {n}\n' for i,(k,n) in enumerate(events)).encode()
   self.assertEqual(out,expected);self.assertEqual(st[2:5],['2','2','0']);self.assertNotIn('error',st[5]);self.assertLess(len(st[5]),80)
  for fault in (11,12):
   out,st=self.run_file('mvmovie',data,fault=fault,exe=exe,keys='3S~')
   self.assertEqual(out,f'frame 1 {movie_hash(0,10,10)}\nwait 8\n'.encode());self.assertIn('error',st[5])
 def test_movie_speed_changes_pause_navigation_and_io(self):self.movie_speed()
 def movie_repeat(self,exe=None):
  data=movie_navigation()
  cases=(('Q',[0]),('QqS~~~',[0,14,28]),('QS~~~',[0,14,28,0]),
         ('SQ~~~',[0,14,28,0]),('QS~~~~~~',[0,14,28,0,14,28,0]),
         ('QS~~~s ',[0,14,28,0,14]),('QS~~q~',[0,14,28]),
         ('Q   ',[0,14,28]),('QLS~',[0,28,0]),('QS~B',[0,14,0]),
         ('QS~R',[0,14,0]),('QS~\x1b',[0,14]))
  for keys,positions in cases:
   out,st=self.run_file('mvmovie',data,exe=exe,keys=keys)
   self.assertEqual(out,''.join(f'frame {i+1} {movie_hash(dx,10,10)}\n' for i,dx in enumerate(positions)).encode(),keys)
   self.assertEqual(st[2:5],['2','2','0']);self.assertNotIn('error',st[5]);self.assertIn('Q loop',st[5]);self.assertLess(len(st[5]),80)
  # A one-frame film still replays through checked source reads.
  out,st=self.run_file('mvmovie',movie(),exe=exe,keys='QS~~~')
  self.assertEqual(out,''.join(f'frame {i+1} {movie_hash(0,10,10)}\n' for i in range(4)).encode())
  # Mirrors and the chosen background survive a wrap without new buffers.
  out,st=self.run_file('mvmovie',data,exe=exe,keys='OHVQS~~~')
  self.assertEqual(out,''.join(f'frame {i+1} {movie_hash(0,10,10) if i==0 else 0}\n' for i in range(7)).encode())
  for fault in (13,14,4):
   out,st=self.run_file('mvmovie',data,fault=fault,exe=exe,keys='QS~~~')
   positions=(0,14,28) if fault!=4 else (0,14,28,0)
   self.assertEqual(out,''.join(f'frame {i+1} {movie_hash(dx,10,10)}\n' for i,dx in enumerate(positions)).encode())
   self.assertIn('error',st[5]);self.assertEqual(st[2:5],['2','2','0'])
 def test_movie_loop_toggle_wrap_pause_manual_end_and_io(self):self.movie_repeat()
 def test_local_originals_and_dgmagi_oracle(self):
  if not (CORPUS/'pal-original.raw').exists():self.skipTest('local original corpus not installed')
  for p in CORPUS.glob('*.PB.raw'):
   original=p.name[:-4]+'#064000';d=(CORPUS/'extracted'/original).read_bytes();out,st=self.run_file('pcsvw',d);self.assertEqual(out[:8192],p.read_bytes()[:8192]);self.assertEqual(st[0],'13')
  d=(CORPUS/'pal-no-text.dpc').read_bytes();out,st=self.run_file('dgmagi',d);self.assertEqual(st[0],'7');self.assertEqual(out,(CORPUS/'pal-original.raw').read_bytes())
  cache=Path.home()/'.cache/a2fc/moviemaker/out';seen=set()
  for p in cache.rglob('*'):
   if p.is_file() and p.name.endswith('.MVM.bin'):
    d=p.read_bytes();digest=hashlib.sha256(d).hexdigest()
    if digest in seen:continue
    if d[:3]!=b'\x01\x00\x01':continue
    seen.add(digest);out,st=self.run_file('mvmovie',d);self.assertTrue(out,p.name);self.assertNotIn('error',st[5]);self.assertNotIn('Malformed',st[5])
  self.assertEqual(len(seen),13)
 def test_both_cpus_real_decoder(self):
  if not shutil.which('cl65'):self.skipTest('cc65 unavailable')
  path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
  samples={'dgmagi':[b'\x80\0\0\xA0\0\0\0'],'pcsvw':[pcs()],'mvmovie':[movie(dx,w) for dx in (0,139,140,250,255) for w in (1,10,140)]}
  samples['mvmovie']+=list(bad_movie_planes())
  seen=set()
  for p in (Path.home()/'.cache/a2fc/moviemaker/out').rglob('*.MVM.bin'):
   data=p.read_bytes();digest=hashlib.sha256(data).hexdigest()
   if digest not in seen and data[:3]==b'\x01\x00\x01':seen.add(digest);samples['mvmovie'].append(data)
  if seen:self.assertEqual(len(seen),13)
  samples['pcsvw'].append(pcs_many())
  samples['pcsvw'].append(pcs_pattern()[0])
  samples['dgmagi']+=[b'\x20\x81\x18\x30\xa2\x2f\xbf\0',b'\x20\x81\x18\x30\xa2\x30\0\0',b'\x20\x81\x18\x30\xa2\x2f\xc0\0']
  if CORPUS.exists():samples['pcsvw'] += [p.read_bytes() for p in (CORPUS/'extracted').glob('*.PB#064000')]
  if (CORPUS/'pal-no-text.dpc').exists():samples['dgmagi'].append((CORPUS/'pal-no-text.dpc').read_bytes())
  for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
   cfg=self.p/(target+'.cfg');cfg.write_text((path.parent/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
   for name,ds in samples.items():
    exe=self.p/(name+target);defines=['-DMEDIA_SOURCE="src/plugins/'+name+'.c"']+([] if name=='mvmovie' else ['-DGRAPHICS'])
    subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(ROOT),*defines,'-o',str(exe),str(self.p/'h.c')],check=True,capture_output=True)
    for d in ds:self.assertEqual(self.run_file(name,d),self.run_file(name,d,exe=['sim65',str(exe)]))
    if name=='mvmovie':
     self.navigation(exe=['sim65',str(exe)])
     self.last_frame(exe=['sim65',str(exe)])
     self.jump_frames(exe=['sim65',str(exe)])
     self.background_toggle(exe=['sim65',str(exe)])
     self.movie_mirrors(exe=['sim65',str(exe)])
     self.movie_autoplay(exe=['sim65',str(exe)])
     self.movie_speed(exe=['sim65',str(exe)])
     self.movie_repeat(exe=['sim65',str(exe)])
if __name__=='__main__':unittest.main()
