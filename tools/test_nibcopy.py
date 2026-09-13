#!/usr/bin/env python3
"""Real NIBCOPY C workflow with disposable nibble tracks and injected faults."""
import ctypes as C
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#define _FORTIFY_SOURCE 0
#define PLUGIN_HOST
#define __fastcall__
#include <string.h>
#include <stdlib.h>
#include "src/plugins/nibcopy.c"
char *nb_note,nb_ram_note[48];
unsigned int nb_address;
unsigned char *nb_buffer,nb_track,nb_bank;
unsigned char aux[65536],disks[2][35][8192],before[2][35][8192];
int reads,writes,confirms,formatted,begins,ends,mode,drive,keys,which_disk;
char message[256],result[80],scratch[512],other_full[81];
static struct Panel panels[2];static unsigned char active;
static unsigned char confirm(const char* s) {++confirms;which_disk=mode==11?0:1;return mode!=1;}
static char keymock(void) {
 static const char k[]={ '6','1','2',13 };
 if(keys<4) {char c=k[keys++];return (mode==10 || mode==11) && keys==3?'1':c;}
 which_disk=0;return 13;
}
static void msg(const char* s){strcpy(message,s);}
static void nothing(void){}
static int print(const char* s,...){return 0;}
static void puts_mock(const char* s){}
static void progress(const char* s,unsigned long n,unsigned long total){if(mode==9 && n==1)cancelled=1;}
static unsigned char ram(void){++formatted;return mode!=14;}
void nb_begin(unsigned char u){drive=(u>>7)&1;if(mode==10 || mode==11)drive=which_disk;++begins;}
void nb_end(void){++ends;}
unsigned char nb_protected(void){return mode==2?0:mode==3?128:drive==0?128:0;}
void nb_fetch(void){memcpy(nb_buffer,aux+nb_address,256);}
void nb_store(void){memcpy(aux+nb_address,nb_buffer,256);}
unsigned char nb_read(void){
 ++reads;if(mode==4 && reads==1)return 0x27;
 if(mode==5 && reads==3)return 0x27;
 memcpy(aux+((unsigned int)nb_bank<<8),disks[drive][nb_track],8192);
 if(mode==6 && reads==2)aux[((unsigned int)nb_bank<<8)+60]^=1;
 if(mode==12 && reads==2) {
  aux[0x6000+39]=aux[0x6000+6160+39]=gcr[2];
  aux[0x6000+40]=aux[0x6000+6160+40]=gcr[3];
 }
 return 0;
}
unsigned char nb_write(void){
 unsigned int i;++writes;
 if(drive!=1 || nb_protected())abort();
 if(mode==7)return 0x27;
 /* Emulate a circular track containing the written stream (gap lengths
  * need not match the source; all encoded fields must match exactly). */
 for(i=0;i<8192;++i)disks[1][nb_track][i]=aux[0x8000+832+(i%6032)]|0x80;
 if(mode==8)disks[1][nb_track][35]^=1;
 if(mode==13) {
  disks[1][nb_track][23]=disks[1][nb_track][6032+23]=gcr[2];
  disks[1][nb_track][24]=disks[1][nb_track][6032+24]=gcr[3];
 }
 return 0;
}
void plugin_entry(const struct A2fcApi* api){if(nb_run(api) && !api->ram_format())strcpy(nb_note,nb_ram_note);}
void reset(void){
 struct A2fcApi api;
 memcpy(before,disks,sizeof disks);memset(&api,0,sizeof api);
 memset(aux,0xA5,sizeof aux);reads=writes=confirms=formatted=begins=ends=keys=which_disk=0;
 api.memcpy=memcpy;api.strcpy=strcpy;api.copy_buf=(unsigned char*)scratch;api.panels=panels;api.active=&active;
 api.note=result;api.other_full=other_full;api.cgetc=keymock;api.message=msg;api.confirm=confirm;
 api.clrscr=nothing;api.cprintf=print;api.cputs=puts_mock;api.progress_bar=progress;api.sprintf=sprintf;api.ram_format=ram;
 plugin_entry(&api);
}
int source_same(void){return !memcmp(before[0],disks[0],sizeof disks[0]);}
int target_same(void){return !memcmp(before[1],disks[1],sizeof disks[1]);}
'''
GCR=bytes([0x96,0x97,0x9A,0x9B,0x9D,0x9E,0x9F,0xA6,0xA7,0xAB,0xAC,0xAD,0xAE,0xAF,0xB2,0xB3,0xB4,0xB5,0xB6,0xB7,0xB9,0xBA,0xBB,0xBC,0xBD,0xBE,0xBF,0xCB,0xCD,0xCE,0xCF,0xD3,0xD6,0xD7,0xD9,0xDA,0xDB,0xDC,0xDD,0xDE,0xDF,0xE5,0xE6,0xE7,0xE9,0xEA,0xEB,0xEC,0xED,0xEE,0xEF,0xF2,0xF3,0xF4,0xF5,0xF6,0xF7,0xF9,0xFA,0xFB,0xFC,0xFD,0xFE,0xFF])
def four(v):return bytes([(v>>1)|0xAA,v|0xAA])
def track(t):
    raw=bytearray()
    for s in range(16):
        raw+=b'\xff'*16+b'\xd5\xaa\x96'+b''.join(four(v) for v in (254,t,s,254^t^s))+b'\xde\xaa\xeb'+b'\xff'*6+b'\xd5\xaa\xad'
        checksum=0
        for i in range(342):
            v=(i+s+t)%64;checksum^=v;raw.append(GCR[v])
        raw+=bytes([GCR[checksum]])+b'\xde\xaa\xeb'
    return (raw*2)[:8192]
class Nibcopy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='nibcopy-');p=Path(cls.tmp.name)
        (p/'host.c').write_text(HARNESS)
        subprocess.run(['cc','-shared','-fPIC','-Wno-unknown-pragmas','-I'+str(ROOT),str(p/'host.c'),'-o',str(p/'host.so')],check=True)
        cls.lib=C.CDLL(str(p/'host.so'));cls.disks=(C.c_ubyte*(2*35*8192)).in_dll(cls.lib,'disks')
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.disks[:]=b''.join(track(t) for t in range(35))+bytes([0xA5])*(35*8192)
    def val(self,n):return C.c_int.in_dll(self.lib,n).value
    def run_copy(self,mode=0):
        C.c_int.in_dll(self.lib,'mode').value=mode;self.lib.reset()
        self.assertTrue(self.lib.source_same(),'source bytes changed')
        self.assertEqual(self.val('begins'),self.val('ends'))
        return bytes((C.c_char*80).in_dll(self.lib,'result')).split(b'\0')[0]
    def test_verified_two_drives(self):
        self.assertEqual(self.run_copy(),b'Copy verified; 35/35 tracks verified.')
        self.assertEqual(self.val('writes'),35);self.assertEqual(self.val('formatted'),1)
    def test_single_drive(self):
        self.assertIn(b'Copy verified',self.run_copy(10));self.assertEqual(self.val('confirms'),35)
    def test_source_left_in_single_drive_is_not_written(self):
        self.assertIn(b'Target protected',self.run_copy(11));self.assertEqual(self.val('writes'),0);self.assertTrue(self.lib.target_same())
    def test_cancel_before_first_write(self):
        self.run_copy(1);self.assertEqual(self.val('writes'),0);self.assertTrue(self.lib.target_same())
    def test_unprotected_source(self):
        self.run_copy(2);self.assertEqual(self.val('reads'),0);self.assertEqual(self.val('formatted'),0);self.assertTrue(self.lib.target_same())
    def test_protected_target(self):
        self.run_copy(3);self.assertEqual(self.val('writes'),0);self.assertTrue(self.lib.target_same())
    def test_source_read_error(self):
        self.run_copy(4);self.assertEqual(self.val('writes'),0);self.assertTrue(self.lib.target_same());self.assertEqual(self.val('formatted'),1)
    def test_verify_read_error(self):self.assertIn(b'WRITE/VERIFY FAILED',self.run_copy(5));self.assertEqual(self.val('writes'),1)
    def test_unstable_source(self):
        self.run_copy(6);self.assertEqual(self.val('writes'),0);self.assertTrue(self.lib.target_same())
    def test_different_valid_source_reads(self):
        self.run_copy(12);self.assertEqual(self.val('writes'),0);self.assertTrue(self.lib.target_same())
    def test_valid_checksum_target_corruption(self):
        self.assertIn(b'WRITE/VERIFY FAILED',self.run_copy(13));self.assertEqual(self.val('writes'),1)
    def test_write_error(self):self.assertIn(b'WRITE/VERIFY FAILED',self.run_copy(7));self.assertTrue(self.lib.target_same())
    def test_silent_corruption(self):self.assertIn(b'WRITE/VERIFY FAILED',self.run_copy(8));self.assertEqual(self.val('writes'),1)
    def test_cancel_after_one_track(self):
        self.assertIn(b'1/35',self.run_copy(9));self.assertEqual(self.val('writes'),1)
        self.assertEqual(bytes(self.disks[36*8192:]),b'\xa5'*(34*8192))
    def test_malformed_fields(self):
        for offset in (16,19,20,25,29,36,50,380):
            with self.subTest(offset=offset):
                self.setUp();self.disks[offset]=0;self.disks[offset+6160]=0
                self.run_copy();self.assertEqual(self.val('writes'),0);self.assertTrue(self.lib.target_same())
    def test_ram_cleanup_failure_is_reported(self):
        self.assertEqual(self.run_copy(14),b'/RAM not rebuilt; 35/35 tracks verified.')
        self.assertEqual(self.val('formatted'),1)
    def test_wrong_track(self):
        self.disks[:8192]=track(1);self.run_copy();self.assertEqual(self.val('writes'),0);self.assertTrue(self.lib.target_same())
    def splice(self,noise,before=16,after=16):
        raw=track(0)[:6160]
        raw=raw[:385]+b'\xff'*before+noise+b'\xff'*after+raw[401:]
        self.disks[:8192]=(raw*2)[:8192]
    def test_physical_splice_noise_is_outside_fields(self):
        self.splice(b'\xf3\xfc');self.assertIn(b'Copy verified',self.run_copy())
    def test_splice_noise_is_bounded(self):
        for noise,before,after in ((b'\xf3'*9,16,16),(b'\xf3',15,16),(b'\xfc',16,15),(b'\xd5',16,16)):
            with self.subTest(noise=noise,before=before,after=after):
                self.setUp();self.splice(noise,before,after);self.run_copy()
                self.assertEqual(self.val('writes'),0);self.assertTrue(self.lib.target_same())
    def test_missing_sector(self):
        self.disks[:8192]=(track(0)[:385]*22)[:8192];self.run_copy();self.assertEqual(self.val('writes'),0);self.assertTrue(self.lib.target_same())
if __name__=='__main__':unittest.main()
