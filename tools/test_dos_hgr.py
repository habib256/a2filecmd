"""Execute the native HGR handoff, observing every byte and ABI argument.

The validated C driver's return is stubbed; the real assembled loader is
executed after its code above $2000 has become image data. Resident I/O
callbacks inject errors and never provide write services.
"""
import re
import subprocess
import unittest
from pathlib import Path
from mos6502 import CPU
from mini33_fixture import make_disk,offset
from take1_ref import DosImage
ROOT=Path(__file__).resolve().parents[1]
ORDER=(0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15)


class HGR(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builds=[]
        for arch,d in (('enh','build'),('6502','build-6502')):
            subprocess.run(['make','ARCH='+arch,d+'/dosview.PLG'],cwd=ROOT,check=True,capture_output=True)
            labels={m[2]:int(m[1],16) for m in re.finditer(r'al ([0-9A-Fa-f]{6}) \.([^\s]+)',(ROOT/d/'dosview.lbl').read_text())}
            data=(ROOT/d/'dosview.PLG').read_bytes()
            at=labels['_dh_api_offsets']-0x1b00
            if data[at:at+6]!=bytes((34,44,48,52,54,92)):
                raise AssertionError('compiler ABI differs from HGR handoff')
            cls.builds.append((data,labels))

    def run_loader(self,build,length=8192,image=False,base=0,fault=None,sparse=False,news=None):
        plugin,l=build
        picture=bytes((i*13+i//256)&255 for i in range(length))
        body=picture;first=0
        if news:
            width,height,history=news
            length=width*height;picture=picture[:length]
            body=length.to_bytes(2,'little')+bytes((0,height-1,0,(width-1)*7))+bytes(history)+b'\xff'+picture
            first=(4+len(body)-length)//256
        disk=make_disk([('PICTURE',4,b'\0 '+len(body).to_bytes(2,'little')+body)])
        ts=DosImage(disk).find(b'PICTURE');table=disk[offset(*ts):offset(*ts)+256]
        mapping=[table[12+2*i+1]|table[12+2*i]<<8 for i in range(first,first+33)]
        if sparse:mapping[12]=0
        physical=bytes(base)+disk
        source_before=bytes(physical);calls=[];counts={'read':0,'seek':0,'close':0,'show':0}
        class Guest(CPU):
            def fetch(guest):
                if counts['read'] and 0x2000<=guest.pc<0x4000:
                    raise AssertionError('executed overwritten graphics memory')
                return super().fetch()
        c=Guest();c.m[:]=b'\xa5'*65536;c.m[0x1b00:0x1b00+len(plugin)]=plugin
        def word(at,value):c.m[at:at+2]=value.to_bytes(2,'little')
        def getword(at):return int.from_bytes(c.m[at:at+2],'little')
        for i,pair in enumerate(mapping):word(l['_dh_map']+2*i,pair)
        if news:
            c.m[l['_dn_width']]=width;c.m[l['_dn_height']]=height
            c.m[l['_dn_offset']]=(4+len(body)-length)&255
        word(l['_dh_length'],length);word(l['_dh_file'],0x1500 if image else 0)
        word(l['_dh_buffer'],0x1200);c.m[l['_dh_unit']]=0 if image else 0xe0
        c.m[l['_dh_base']:l['_dh_base']+4]=base.to_bytes(4,'little')
        word(l['sp'],0xb000);c.m[0x1501]=0
        word(0x1000+92,0x1600);c.m[0x1600]=0
        callbacks={34:'wait',44:'mli',48:'read',52:'close',54:'seek'}
        addresses={}
        for off,name in callbacks.items():
            addr=0x6000+off;word(0x1000+off,addr);c.m[addr]=2;addresses[addr]=name
        c.m[l['_dv_entry']]=2
        filepos=[0]
        def trap():
            addr=c.pc-1;name=addresses.get(addr,'driver');sp=getword(l['sp'])
            args=bytes(c.m[sp:sp+6]);ax=c.a|c.x<<8;result=0;drop=0
            if name=='driver':result=1
            elif name=='mli':
                self.assertEqual(args[0],0x80);drop=1
                p=c.m[ax:ax+6];self.assertEqual(p[:2],bytes((3,0xe0)))
                self.assertEqual(int.from_bytes(p[2:4],'little'),0x1200)
                b=int.from_bytes(p[4:6],'little');t=b//8
                counts['read']+=1
                if fault==('read',counts['read']):result=0x27
                else:
                    for half in (0,1):
                        s=ORDER[(b&7)*2+half];start=offset(t,s)
                        c.m[0x1200+half*256:0x1300+half*256]=disk[start:start+256]
            elif name=='seek':
                self.assertEqual(ax,2);self.assertEqual(int.from_bytes(args[4:6],'little'),0x1500)
                drop=6;counts['seek']+=1;filepos[0]=int.from_bytes(args[:4],'little')
                if fault==('seek',counts['seek']):result=0xffff
            elif name=='read':
                self.assertEqual(ax,0x1500);self.assertEqual(args,b'\0\1\1\0\0\x12')
                drop=6;counts['read']+=1;start=filepos[0]
                self.assertGreaterEqual(start,base);self.assertLessEqual(start+256,len(physical))
                c.m[0x1200:0x1300]=physical[start:start+256];result=256
                if fault==('read',counts['read']):result=0
                if fault==('ferror',counts['read']):c.m[0x1501]=4
            elif name=='close':
                self.assertEqual(ax,0x1500);counts['close']+=1
                if fault==('close',1):result=0xffff
            elif name=='wait':
                counts['show']+=1
                self.assertIn(0xc050,c.writes)
                result=27
            calls.append(name);word(l['sp'],sp+drop)
            c.a=result&255;c.x=result>>8
            c.pc=(c.pull()|c.pull()<<8)+1
        c.ops[2]=trap;c.x=0x10
        c.call(l['_plugin_entry'],a=0,limit=900000)
        self.assertEqual(getword(l['sp']),0xb000)
        self.assertEqual(c.s,255)
        self.assertEqual(physical,source_before)
        self.assertEqual(counts['close'],int(image))
        def writable(at):
            return (0x80<=at<0x9a or 0x100<=at<0x200 or
                    0x1200<=at<0x1400 or 0x1600<=at<0x1650 or
                    0x1b00<=at<l['_dh_buffer']+2 or 0x2000<=at<0x4000 or
                    0xaffa<=at<0xb000 or
                    at in (0xc000,0xc002,0xc004,0xc00c,0xc00d,0xc050,
                           0xc051,0xc052,0xc054,0xc057,0xc05f))
        self.assertFalse([hex(at) for at in c.writes if not writable(at)])
        self.assertFalse(any(0xc005<=a<=0xc009 or a in (0xc001,0xc055) for a in c.writes))
        if fault:
            self.assertEqual(counts['show'],0)
            self.assertNotIn(0xc050,c.writes)
            self.assertTrue(bytes(c.m[0x1600:0x1640]).startswith(b'DOS Newsroom read/close error.' if news else b'DOS HGR read/close error.'))
        else:
            expected=bytearray(picture+bytes(8192-length))
            if news:
                from newsroom_ref import page
                expected=page(body)
            if sparse:expected[12*256-4:13*256-4]=bytes(256)
            self.assertEqual(c.m[0x2000:0x4000],expected)
            self.assertEqual(counts['show'],1)
            if image:self.assertLess(calls.index('close'),calls.index('wait'))
        return counts

    def test_exact_pages_on_both_cpus_and_backends(self):
        for build in self.builds:
            for length in (8184,8192):
                for image,base in ((False,0),(True,0),(True,64),(True,0x20345)):
                    self.run_loader(build,length,image,base)
            self.run_loader(build,sparse=True)
            self.run_loader(build,image=True,base=64,sparse=True)

    def test_each_read_seek_error_and_close_before_display(self):
        for build in self.builds:
            for image in (False,True):
                for n in range(1,34):
                    self.run_loader(build,image=image,fault=('read',n))
                    if image:
                        self.run_loader(build,image=True,base=64,fault=('seek',n))
                        self.run_loader(build,image=True,fault=('ferror',n))
            self.run_loader(build,image=True,fault=('close',1))


if __name__=='__main__':unittest.main()
