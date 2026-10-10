"""Actual C Print Shop border/font readers: complete input and bitmap bounds."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_retrotext import HARNESS,ROOT

H=HARNESS.replace('#include RT_SOURCE','#include PS_SOURCE').replace('if(x>=79 || y<1 || y>21)','if(x>=79 || y>21)')
H=H.replace("return k=='E'?27:' ';", "return k=='R'?KEY_RIGHT:k=='L'?KEY_LEFT:k=='D'?KEY_DOWN:k=='U'?KEY_UP:KEY_ESC;")
H=H.replace('static void message(const char* s)',r'''static int print_(const char* fmt,...){
 char b[256];unsigned int i;va_list ap;va_start(ap,fmt);vsnprintf(b,sizeof b,fmt,ap);va_end(ap);
 for(i=0;b[i];++i){if(x>=79)abort();screen[y][x++]=b[i];}return i;
}
static int seek_(FILE*f,long p,int w){
 char scratch[256];unsigned int n;if(fault==6)return -1;
 if(w!=SEEK_SET || p<0)return -1;
 /* Glyphs seek once after reopening at zero; sim65 lacks lseek. */
 while(p){n=p>256?256:(unsigned int)p;if(fread(scratch,1,n,f)!=n)return -1;p-=n;}return 0;
}
static void message(const char* s)''')
H=H.replace('#include PS_SOURCE','#include <stdarg.h>\n#include PS_SOURCE')
H=H.replace('e.size=strtoul(argv[4],0,10);','e.size=strtoul(argv[4],0,10);e.type=argc>6?atoi(argv[6]):6;e.aux=atoi(argv[5]);')
H=H.replace('api.fopen=opn;','api.cprintf=print_;api.fseek=seek_;api.fopen=opn;')

H=H.replace('#include PS_SOURCE',r'''
#include PS_SOURCE
static void dump_glyph(void){
#ifdef PS_TEST_FONT
 unsigned int i;printf("GLYPH %u %u %u ",index_,width,height);
 for(i=0;i<(unsigned int)stride*height;++i)printf("%02X",(unsigned int)glyph[i]);
 putchar('\n');
#endif
}
''')
H=H.replace('flush();if(k)', 'flush();dump_glyph();if(k)')


def font(prefix=12,width=8,height=7,shared=False):
    base=0x5ff4 if prefix else 0x6000
    head=bytearray(prefix+236);data=bytearray()
    for i in range(59):
        head[prefix+i]=width|128;head[prefix+59+i]=height
        ptr=base+len(head)+(0 if shared else len(data))
        head[prefix+118+i]=ptr&255;head[prefix+177+i]=ptr>>8
        if not shared or not data:data.extend(bytes([0x81])*(((width+7)//8)*height))
    return bytes(head+data)


def font5():
    old=font();head=bytearray(392);body=old[248:]
    head[6:8]=len(body).to_bytes(2,'little')
    for i in range(59):
        head[12+i]=old[12+i];head[107+i]=old[71+i]
        p=int.from_bytes(bytes([old[130+i],old[189+i]]),'little')-0x5ff4-248
        head[202+i]=p&255;head[297+i]=p>>8
    return bytes(head)+body


class PrintShop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='ps-extra-');cls.p=Path(cls.tmp.name)
        (cls.p/'h.c').write_text(H);cls.executables={}
        for name in ('psfont','psborder'):
            exe=cls.p/name
            subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),*(['-DPS_TEST_FONT'] if name=='psfont' else []),'-DPS_SOURCE="src/plugins/'+name+'.c"',str(cls.p/'h.c'),'-o',str(exe)],check=True,capture_output=True)
            cls.executables[name]=exe
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_file(self,name,data,aux,fault=0,keys='',size=0,refused=False,typ=6):
        src=self.p/'source';src.write_bytes(data)
        r=subprocess.run([str(self.executables[name]),str(src),str(fault),keys,str(size),str(aux),str(typ)],check=True,capture_output=True,text=True,timeout=10)
        self.assertEqual(src.read_bytes(),data)
        opens,closes,note=r.stderr.rstrip('\n').split(' ',2)
        self.glyphs=[row for row in r.stdout.splitlines() if row.startswith('GLYPH ')]
        rows=[row[1:].rstrip() for row in r.stdout.splitlines() if row.startswith('|')]
        if refused:self.assertTrue(note);self.assertFalse(any(rows))
        else:self.assertEqual(note,'',r.stderr)
        return rows,(int(opens),int(closes)),note
    def test_border_column_banks_prefix_and_length(self):
        data=bytearray(144);data[24]=1;data[0]=64;data[48+24+23]=1;data[96+0+10]=2
        rows,_,_=self.run_file('psborder',bytes(data),0x7800)
        self.assertEqual(rows[3][0],'*');self.assertEqual(rows[3][49],'*');self.assertEqual(rows[16][0],'*');self.assertEqual(rows[11][62],'*')
        rows2,_,_=self.run_file('psborder',b'\x03\0\0\0'+data,0x7800)
        self.assertEqual(rows[3:17],rows2[3:17])
        for n in (0,1,143,145,147,149,512):self.run_file('psborder',bytes(n),0x7800,refused=True)
        self.run_file('psborder',bytes(144),0x2000,refused=True)
    def test_font_msb_first_both_headers_and_scroll(self):
        for prefix in (0,12):
            rows,_,_=self.run_file('psfont',font(prefix=prefix),0x5ff4 if prefix else 0x6000)
            self.assertEqual(rows[0],'    **            **')
        rows,_,_=self.run_file('psfont',font(width=48,height=64,shared=True),0x5ff4,keys='D'*44+'R')
        self.assertEqual(len([r for r in rows if r]),920)
    def test_pointer_and_glyph_bounds_before_display(self):
        data=font()
        for n in (0,11,247,248,len(data)-1):self.run_file('psfont',data[:n],0x5ff4,refused=True)
        for offset,value in ((13,49),(12+59+1,65),(12+177+58,255),(12+118+58,0)):
            bad=bytearray(data);bad[offset]=value
            # Pointer low byte zero can still be valid: force its high byte zero.
            if offset==12+118+58:bad[12+177+58]=0
            self.run_file('psfont',bytes(bad),0x5ff4,refused=True)
        self.run_file('psfont',data,0x2000,refused=True)
    def test_io_and_stale_sizes(self):
        for name,data,aux in (('psborder',bytes(144),0x7800),('psfont',font(),0x5ff4)):
            for fault in (1,2,3):self.run_file(name,data,aux,fault=fault,refused=True)
            for size in (0,1,16777215):self.run_file(name,data,aux,size=size)
        for fault in (2,3):self.run_file('psfont',font(),0x5ff4,fault=fault,refused=True)
        for fault in (4,5,6):
            _,_,note=self.run_file('psfont',font(),0x5ff4,fault=fault,refused=True);self.assertIn('error',note)
    def test_real_fonts_and_borders(self):
        root=Path(os.environ.get('A2FC_PRINTSHOP_CORPUS','/tmp/a2fc-printshop-corpus'))/'images'
        if not root.is_dir():self.skipTest('Print Shop corpus unavailable')
        from corpus_read import files
        count=0
        for p in root.rglob('*'):
            if not p.is_file() or not ('Borders' in p.name or 'Fonts' in p.name):continue
            fs,entries=files(p.read_bytes())
            for n,t,a,d in entries:
                if t==6 and n.startswith('BORD.') and len(d)==148:self.run_file('psborder',d,a);count+=1
                elif t==6 and n.startswith('FONT.') and a==0x5ff4:self.run_file('psfont',d,a);count+=1
        self.assertEqual(count,113)
    def test_prodos_f5_real_paired_pixels_and_all_glyph_bounds(self):
        root=Path(os.environ.get('A2FC_PRINTSHOP_CORPUS','/tmp/a2fc-printshop-corpus'))/'images'
        if not root.is_dir():self.skipTest('Print Shop corpus unavailable')
        from corpus_read import files
        old={};new={}
        for p in root.rglob('*.dsk'):
            if not ('Borders' in p.name or 'Fonts' in p.name):continue
            _,entries=files(p.read_bytes())
            for n,t,a,d in entries:
                name=n.rsplit('/',1)[-1]
                if name.startswith(('BORD.','FONT.')):
                    if t==6:old[name]=(a,d)
                    elif t==0xf5:new[name]=(a,d)
        self.assertEqual(len(new),113)
        for n,(a,d) in new.items():
            plugin='psborder' if a==0x2000 else 'psfont';oa,od=old[n]
            keys='' if plugin=='psborder' else 'R'*56
            rows,_,_=self.run_file(plugin,d,a,typ=0xf5,keys=keys)
            glyphs=self.glyphs
            original,_,_=self.run_file(plugin,od,oa,keys=keys)
            if plugin=='psborder':self.assertEqual(rows[3:17],original[3:17],n)
            else:
                self.assertEqual(rows,original,n)
                self.assertEqual(glyphs,self.glyphs,n) # Complete C-loaded bitmaps, including rows below viewport.
            if plugin=='psfont':
                self.run_file(plugin,d,a,typ=0xf5,keys='R'*92)
                for pos in (6,12+95+94,12+285+94):
                    bad=bytearray(d);bad[pos]=255
                    self.run_file(plugin,bytes(bad),a,typ=0xf5,refused=True)
        # Both metadata and exact lengths are required, all I/O closes precede pixels.
        a,d=next(v for v in new.values() if v[0]==0x2000)
        for n in (0,12,263,265):self.run_file('psborder',d[:n] if n<264 else d+b'X',a,typ=0xf5,refused=True)
        for plugin,aux,data in (('psborder',a,d),('psfont',*next(v for v in new.values() if v[0]==0x1000))):
            self.run_file(plugin,data,aux^1,typ=0xf5,refused=True)
            for fault in (1,2,3):self.run_file(plugin,data,aux,typ=0xf5,fault=fault,refused=True)

    def test_f5_ident_routing_and_negative_metadata(self):
        import ctypes
        from corpus_census import C_SOURCE
        (self.p/'ident.c').write_text(C_SOURCE)
        for cpu in ('6502','65c02'):
            libpath=self.p/(cpu+'-ident.so')
            subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-shared','-fPIC','-I',str(ROOT),*(['-DA2FC_6502'] if cpu=='6502' else []),str(self.p/'ident.c'),'-o',str(libpath)],check=True,capture_output=True)
            lib=ctypes.CDLL(str(libpath));identify=lib.corpus_ident
            identify.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_void_p];identify.restype=ctypes.c_char_p
            for name,aux,data,expected in (('BORD.TEST',0x2000,bytes(264),'PSBORDER'),('FONT.TEST',0x1000,font5(),'PSFONT')):
                for dos in (0,1):
                    output=ctypes.create_string_buffer(80)
                    self.assertTrue(identify(name.encode(),0xf5,aux,data,len(data),dos,output))
                    self.assertEqual(output.value.decode(),expected if not dos else 'DOSVIEW')
                for wrongname,wrongaux,body in (('OTHER',aux,data),(name,aux+1,data),(name,aux,data[:247])):
                    output=ctypes.create_string_buffer(80)
                    self.assertTrue(identify(wrongname.encode(),0xf5,wrongaux,body,len(body),0,output))
                    self.assertNotEqual(output.value.decode(),expected)

    def test_cc65_both_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65/sim65 absent')
        targetpath=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=(targetpath.parent/'cfg'/(target+'.cfg')).read_text();config=self.p/(target+'.cfg');config.write_text(cfg.replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
            for name,data,aux in (('psborder',bytes(144),0x7800),('psfont',font(),0x5ff4),('psborder',bytes(264),0x2000),('psfont',font5(),0x1000)):
                exe=self.p/(target+'-'+name)
                subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-Cl','-C',str(config),'-I',str(ROOT),*(['-DPS_TEST_FONT'] if name=='psfont' else []),'-DPS_SOURCE="src/plugins/'+name+'.c"','-o',str(exe),str(self.p/'h.c')],check=True,capture_output=True)
                src=self.p/'native-source';src.write_bytes(data);args=[str(src),'0','','0',str(aux),str(0xf5 if aux in (0x1000,0x2000) else 6)]
                expected=subprocess.run([str(self.executables[name])]+args,check=True,capture_output=True)
                actual=subprocess.run(['sim65',str(exe)]+args,check=True,capture_output=True,timeout=20)
                self.assertEqual(actual.stdout,expected.stdout);self.assertEqual(actual.stderr,expected.stderr);self.assertEqual(src.read_bytes(),data)

if __name__=='__main__':unittest.main()
