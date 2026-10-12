"""Actual IDREAD -> IDV1 -> IDFORMATS relay with immutable full DOS names."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_dos_stream as D
from test_dosint import HARNESS as BASE
from mini33_fixture import make_disk

H=BASE.replace('#include "src/plugins/dosint.c"',r'''
unsigned char host_id_sample[512];
#define md_entrypoint id_source
#include "src/plugins/idread.c"
#undef md_entrypoint
unsigned char __fastcall__ id_detect(const struct A2fcApi*);
unsigned char __fastcall__ id_formats(const struct A2fcApi*);
void __fastcall__ plugin_entry(const struct A2fcApi* a){
 unsigned char* context=(unsigned char*)a->other_full;unsigned char next;
 if(!id_source(a))return;
 if(fault==1005)context[48]^=1;
 next=id_detect(a);
 if(next && context[42]==3)next=id_formats(a);
 if(next && context[42]==4)next=id_detect(a);
 if(next && context[42]!=1)abort();
 if(!a->note[0])printf("%s\n",a->input[0]?a->input:"FALLBACK");
}
''')
H=H.replace('static char note[80],sel[80];','static char note[80],sel[80],context[81],input[64];')
H=H.replace('api.cgetc=key;','api.input=input;api.other_full=context;api.cgetc=key;')
H=H.replace(' plugin_entry(&api);',' api.arg=argv[9][4]==\'R\'?13:argv[9][4];plugin_entry(&api);')

from test_six_plugins import PREFIX
STAGE=PREFIX+r'''
extern unsigned char host_id_sample[512];
#define md_entrypoint STAGE_ENTRY
#define md_player stage_player
#define md_cpu_tag stage_tag
#define __plugin_header stage_header
#define plugin_entry stage_stub
#ifdef TEST_V1
static const char* known(const char*,const char*);
#include "src/plugins/idv1.c"
static const char* known(const char* label,const char* view){reader=view;return label;}
#else
#include "src/plugins/idformats.c"
#endif
void __fastcall__ stage_stub(const struct A2fcApi* a){(void)a;}
'''
# Private symbols differ between the two separately compiled production units.
V1=STAGE.replace('stage_player','v1_player').replace('stage_tag','v1_tag').replace('stage_header','v1_header').replace('stage_stub','v1_stub')
FORMATS=STAGE.replace('stage_player','fm_player').replace('stage_tag','fm_tag').replace('stage_header','fm_header').replace('stage_stub','fm_stub')

def display_name(name):
    name=name.rstrip()[:15].upper()
    name=''.join(c if c.isascii() and c.isalnum() else '.' for c in name)
    return name if 'A'<=name[0]<='Z' else 'X'+name[1:]

def high(b):return bytes(c|128 for c in b)

def binary(name,b,aux=0x6100):
    return make_disk([(name,4,aux.to_bytes(2,'little')+len(b).to_bytes(2,'little')+b)])

class Names(unittest.TestCase):
    run_disk=D.Streams.run_disk
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dos-names-',dir='/tmp');cls.p=Path(cls.tmp.name)
        cls.h=cls.p/'h.c';cls.h.write_text(H);cls.v1=cls.p/'v1.c';cls.v1.write_text(V1)
        cls.fm=cls.p/'formats.c';cls.fm.write_text(FORMATS);cls.exe=cls.p/'host'
        cls.compile(cls.exe)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    @classmethod
    def compile(cls,exe,target=None,cpu=None):
        objects=[]
        if target:
            root=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip()).parent
            cfg=cls.p/(target+'.cfg');cfg.write_text((root/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
        for label,src,defs in [('h',cls.h,[]),('v1',cls.v1,['-DTEST_V1','-DSTAGE_ENTRY=id_detect']),('formats',cls.fm,['-DSTAGE_ENTRY=id_formats'])]:
            obj=cls.p/(exe.name+'-'+label+'.o');objects.append(str(obj))
            cmd=['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl'] if target else ['cc','-std=c99','-Wno-unknown-pragmas']
            subprocess.run(cmd+['-I',str(D.ROOT),*defs,'-c',str(src),'-o',str(obj)],check=True,capture_output=True)
            if target:src.with_suffix('.o').rename(obj)
        cmd=['cl65','-t',target,'--cpu',cpu,'-C',str(cfg)] if target else ['cc']
        subprocess.run(cmd+objects+['-o',str(exe)],check=True,capture_output=True)
    def check(self,raw,name,expected,typ=6,image=1,fault=0,exe=None,size=1,mode='viewI'):
        out,counts,note=self.run_disk(raw,name=display_name(name),key=783,typ=typ,image=image,fault=fault,exe=exe,size=size,mode=mode,good=not bool(fault))
        if not fault:self.assertEqual(out,expected.encode()+b'\n')
        else:self.assertEqual(out,b'')
        return counts
    def test_full_30_byte_names_case_spaces_and_boundaries(self):
        for name in ('BLIPPO BLACK.SET','ABCDEFGHIJKLMNOPQRSTUVWXY.FONT','LONG.HRCG.TYPEFACE.FONT',
                     'long mixed Case.font','LONG FONT.SET     ','SHORT.FONT'):
            for n in (768,1024):
                for image in (0,1,2):self.check(binary(name,bytes(n)),name,'DOSFONT',image=image)
        for name in ('LONG.MERLIN.SOURCE.ASM','LONG SOURCE NAME.S','a.Mixed.Long.Source.asm'):
            for image in (0,1,2):self.check(make_disk([(name,0,high(b'LABEL LDA #0\r'))]),name,'MERLIN',typ=4,image=image)
        b=bytearray(256);b[0]=0x8d;b[2]=32;b+=high(b'Hello\r')
        for image in (0,1,2):self.check(binary('FASTLOADER/DOCS.MW',b), 'FASTLOADER/DOCS.MW','MAGWIN',image=image)
        name='LONG.HRCG.TYPEFACE.FONT'
        for size in (0,1,0xffffff):
            for mode in ('viewR','viewI','viewO'):self.check(binary(name,bytes(768)),name,'DOSFONT',size=size,mode=mode)
    def test_suffix_and_content_mismatches_and_other_readers_keep_priority(self):
        for name,n in [('LONG.FONT.TYPEFACE.FONT',769),('LONG.FONT.TYPEFACE.FONX',768),('LONG.FONT.TYPEFACEFONT',768),('LONG.FAKE.FONT.X',768)]:
            self.check(binary(name,bytes(n)),name,'FALLBACK')
        name='LONG.MERLIN.SOURCE.ASM'
        self.check(make_disk([(name,0,b'ordinary text\r')]),name,'FALLBACK',typ=4)
        self.check(binary(name,high(b' LDA #0\r')),name,'FALLBACK')
        self.check(make_disk([(name,0,high(b'.lm2\rHello\r'))]),name,'APPLEWR',typ=4)
        name='FONT.LONG.TYPEFACE.FONT'
        self.check(binary(name,bytes(768),aux=0x6000),name,'PSFONT')
        name='LONG.FONTRIX.TYPEFACE.FONT';b=bytearray(1024);b[24:27]=b'\x90\xf7\xb2'
        self.check(binary(name,b),name,'FONTRIX')
    def test_every_source_read_open_seek_close_fault_and_bad_context(self):
        name='LONG.HRCG.TYPEFACE.FONT';raw=binary(name,bytes(1024))
        for image in (0,1,2):
            counts=self.check(raw,name,'DOSFONT',image=image)
            for fault in list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else [])+[1005]:
                self.check(raw,name,'DOSFONT',image=image,fault=fault)
    def test_catalog_identity_with_colliding_display_names(self):
        a='LONG.HRCG.TYPEFACE.FONT';b='LONG.HRCG.TYPEFACE.FONX'
        raw=make_disk([(a,4,b'\0a\0\x03'+bytes(768)),(b,4,b'\0a\0\x03'+bytes(768))])
        from take1_ref import DosImage
        for name,expected in [(a,'DOSFONT'),(b,'FALLBACK')]:
            t,s=DosImage(raw).find(name.encode());out,_,_=self.run_disk(raw,name=display_name(name),key=t*256+s,typ=6,image=1,mode='viewI')
            self.assertEqual(out,expected.encode()+b'\n')
    def test_merlin_content_without_suffix_and_conservative_fallback(self):
        name='SOURCE'
        body=high(b'*Assembler source\rLABEL LDA #0\r STA $300\r RTS\r')
        for image in (0,1,2):
            counts=self.check(make_disk([(name,0,body)]),name,'MERLIN',typ=4,image=image)
            for fault in list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else []):
                self.check(make_disk([(name,0,body)]),name,'MERLIN',typ=4,image=image,fault=fault)
        for b in (high(b' LDA #0\r STA $300\r'),high(b'* LDA\r* STA\r* RTS\r'),
                  high(b' LDA #0\r STA $300\r RTS'),
                  high(b' LDA #0\r STA $300\r RTS\r')+b'\x01',
                  b' LDA #0\r STA $300\r RTS\r',high(b'ordinary text\rmore prose\r')):
            self.check(make_disk([(name,0,b)]),name,'FALLBACK',typ=4)
        self.check(binary(name,body),name,'FALLBACK')
        self.check(make_disk([(name,0,high(b'.lm2\r LDA #0\r STA $300\r RTS\r'))]),name,'APPLEWR',typ=4)
    def test_renamed_printshop_font_structure_and_io_errors(self):
        from test_printshop_extras import font
        name='RENAMED'
        for aux,prefix in ((0x6000,0),(0x5ff4,12)):
            body=font(prefix=prefix)
            for image in (0,1,2):
                raw=binary(name,body,aux)
                counts=self.check(raw,name,'PSFONT',image=image)
                for fault in list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else []):
                    self.check(raw,name,'PSFONT',image=image,fault=fault)
            for pos in (prefix+58,prefix+59+58,prefix+177+58):
                bad=bytearray(body);bad[pos]=255
                self.check(binary(name,bad,aux),name,'FALLBACK')
            self.check(binary(name,body[:-1],aux),name,'FALLBACK')
            self.check(binary(name,body,aux+1),name,'FALLBACK')
    def test_actual_dos_font_reader_validates_before_pixels(self):
        from test_printshop_extras import font
        h=self.p/'ps-reader.c';h.write_text(BASE.replace('#include "src/plugins/dosint.c"','#include "src/plugins/psfont.c"'))
        exe=self.p/'ps-reader'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(D.ROOT),str(h),'-o',str(exe)],check=True,capture_output=True)
        self.exe=exe
        raw=binary('RENAMED',font(),0x5ff4)
        for image in (0,1,2):
            out,counts,_=self.run_disk(raw,name='RENAMED',typ=6,image=image,mode='viewI')
            self.assertIn(b'Print Shop font:',out);self.assertEqual(out.count(b'**            **'),7)
            for fault in list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else []):
                out,_,_=self.run_disk(raw,name='RENAMED',typ=6,image=image,mode='viewI',fault=fault,good=False)
                self.assertNotIn(b'Print Shop font:',out)
    def border_cases(self,exe=None):
        for aux in (0x4800,0x5800,0x6800,0x7800):
            for length in (144,148):
                raw=binary('RENAMED',bytes(length),aux)
                for image in (0,1,2):
                    for mode in ('viewR','viewI','viewO'):
                        counts=self.check(raw,'RENAMED','PSBORDER',image=image,exe=exe,mode=mode,size=0xffffff)
                    if exe is None:
                        for fault in list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else []):
                            self.check(raw,'RENAMED','PSBORDER',image=image,fault=fault)
        for length in (0,143,145,147,149,264):
            self.check(binary('RENAMED',bytes(length),0x4800),'RENAMED','FALLBACK',exe=exe)
        self.check(binary('RENAMED',bytes(144),0x4801),'RENAMED','FALLBACK',exe=exe)

    def test_renamed_border_profiles_and_all_detector_io_faults(self):self.border_cases()

    def test_actual_dos_border_reader_validates_before_pixels(self):
        h=self.p/'border-reader.c';h.write_text(BASE.replace('#include "src/plugins/dosint.c"','#include "src/plugins/psborder.c"'))
        exe=self.p/'border-reader'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(D.ROOT),str(h),'-o',str(exe)],check=True,capture_output=True)
        self.exe=exe
        body=bytearray(144);body[24]=1;body[0]=64;body[48+24+23]=1;body[96+10]=2
        for prefix in (b'',b'\x03\x00\x00\x00'):
            raw=binary('RENAMED',prefix+body,0x7800)
            for image in (0,1,2):
                out,counts,_=self.run_disk(raw,name='RENAMED',typ=6,image=image,mode='viewI')
                self.assertIn(b'Print Shop border:',out);self.assertEqual(out.count(b'*'),4)
                for fault in list(range(1,counts[1]+1))+([1001,1002,1003,1004] if image else []):
                    out,_,_=self.run_disk(raw,name='RENAMED',typ=6,image=image,mode='viewI',fault=fault,good=False)
                    self.assertNotIn(b'Print Shop border:',out);self.assertNotIn(b'*',out)
    def original_merlin(self,exe=None):
        from legacy_corpus import dos_files
        p=Path.home()/'.cache/a2fc/asimov_corpus/raw/images/programming/assembler/merlin/MERLIN-8_DOS33.dsk'
        if not p.exists():self.skipTest('local Merlin corpus unavailable')
        original=p.read_bytes();count=0
        for name,typ,aux,b in dos_files(original):
            if typ!=4:continue
            expected='FALLBACK' if name=='PI.NAMES' else 'MERLIN'
            with self.subTest(name=name,exe=exe):
                self.check(make_disk([(name,0,b)]),name,expected,typ=4,exe=exe);count+=1
        self.assertEqual(count,9);self.assertEqual(p.read_bytes(),original)
    def test_original_merlin_unnamed_sources_when_available(self):
        self.original_merlin()
    def test_original_long_named_hrcg_font_when_available(self):
        import json,hashlib
        index=Path.home()/'.cache/a2fc/asimov_corpus/index.json'
        if not index.exists():self.skipTest('local DOS font corpus unavailable')
        seen=set()
        for row in json.loads(index.read_text())['rows']:
            name=row.get('name','').rstrip()
            if row.get('fs')!='dos' or row.get('type')!='B' or row.get('length') not in (768,1024) or len(name)<=15 or not name.endswith(('.FONT','.SET')):continue
            for directory,filename in row.get('saved',{}).items():
                p=Path(directory)/filename
                if not p.exists():continue
                b=p.read_bytes();self.assertEqual(hashlib.sha1(b).hexdigest(),row['sha1'])
                if (name,b) in seen:continue
                seen.add((name,b));self.check(binary(name,b),name,'DOSFONT')
                self.assertEqual(p.read_bytes(),b)
        if not seen:self.skipTest('saved long-named DOS font unavailable')
    def test_cc65_on_both_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            exe=self.p/target;self.compile(exe,target,cpu)
            self.border_cases(exe)
            self.original_merlin(exe)
            for image in (0,1,2):
                from test_printshop_extras import font
                from test_v1media import pcs
                self.check(binary('TABLE',pcs(),0x4000),'TABLE','FALLBACK',image=image,exe=exe)
                self.check(binary('TABLE.PB',pcs(),0x4000),'TABLE.PB','DOSVIEW',image=image,exe=exe)
                dpc=b'\x20\x81\x18\x30\xa2\x2f\xbf\0'
                self.check(binary('PALETTE',dpc,0x4000),'PALETTE','FALLBACK',image=image,exe=exe)
                self.check(binary('PAL.DPC',dpc,0x4000),'PAL.DPC','DOSVIEW',image=image,exe=exe)
                multiscribe=b'\x80\x19\x01\0\x01\0\xb1\xe2\x02'+bytes(27)+b'\x02Hello\r'
                self.check(binary('IMPORTED',multiscribe,0),'IMPORTED','FALLBACK',image=image,exe=exe)
                from test_v1text import mouse,multiplan_number
                self.check(binary('MOUSE',mouse(),0),'MOUSE','FALLBACK',image=image,exe=exe)
                self.check(binary('SHEET',multiplan_number(1),0),'SHEET','FALLBACK',image=image,exe=exe)
                from test_nexttext import lisa
                self.check(binary('LISA',lisa(),0x2000),'LISA','FALLBACK',image=image,exe=exe)
                from test_retrotext import sc_line
                self.check(binary('SCIMPORT',sc_line(100,b'\x89LDA\x83#0'),0),'SCIMPORT','FALLBACK',image=image,exe=exe)
                self.check(binary('ARLIMPORT',b'\x09\x51gs'+bytes(4),0),'ARLIMPORT','FALLBACK',image=image,exe=exe)
                from test_v1media import movie
                self.check(binary('FILM',movie(),0),'FILM','FALLBACK',image=image,exe=exe)
                self.check(binary('RENAMED',font(),0x5ff4),'RENAMED','PSFONT',image=image,exe=exe)
                name='ABCDEFGHIJKLMNOPQRSTUVWXY.FONT';raw=binary(name,bytes(768))
                counts=self.check(raw,name,'DOSFONT',image=image,exe=exe)
                for fault in (1,*([1002,1003,1004] if image else []),1005):self.check(raw,name,'DOSFONT',image=image,exe=exe,fault=fault)
                name='LONG.MERLIN.SOURCE.ASM'
                self.check(make_disk([(name,0,high(b' LDA #0\r'))]),name,'MERLIN',typ=4,image=image,exe=exe)
                name='SOURCE'
                self.check(make_disk([(name,0,high(b' LDA #0\r STA $300\r RTS\r'))]),name,'MERLIN',typ=4,image=image,exe=exe)
                self.check(make_disk([(name,0,high(b' LDA #0\r STA $300\r'))]),name,'FALLBACK',typ=4,image=image,exe=exe)
                name='FASTLOADER/DOCS.MW';b=bytearray(256);b[0]=0x8d;b[2]=32;b+=b'Hello\r'
                self.check(binary(name,b),name,'MAGWIN',image=image,exe=exe)

if __name__=='__main__':unittest.main()
