"""Run both native MCS handoffs after their old overlay is overwritten."""
import re
import subprocess
import unittest
from pathlib import Path
from mos6502 import CPU
ROOT=Path(__file__).resolve().parents[1]


class Handoff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builds=[]
        for arch,d in (('enh','build'),('6502','build-6502')):
            subprocess.run(['make','ARCH='+arch,d+'/dosmcs.PLG',d+'/mcsimport.PLG',d+'/mcsplay.PLG'],cwd=ROOT,check=True,capture_output=True)
            for name in ('dosmcs','mcsimport'):
                labels={m[2]:int(m[1],16) for m in re.finditer(r'al ([0-9A-Fa-f]{6}) \.([^\s]+)',(ROOT/d/(name+'.lbl')).read_text())}
                old=(ROOT/d/(name+'.PLG')).read_bytes();at=labels['_md_api_offsets']-0x1b00
                if old[at:at+3]!=bytes((48,52,92)):raise AssertionError('MCS handoff API offsets changed')
                cls.builds.append((old,labels,(ROOT/d/'mcsplay.PLG').read_bytes()))

    def run_handoff(self,build,fault=None,payload=None,ident=False):
        old,l,player=build;player=player if payload is None else payload
        counts={'read':0,'close':0,'play':0};pos=[0];limit=0x4000 if ident else 0x3700
        class Guest(CPU):
            def fetch(guest):
                if counts['read'] and 0x1b00<=guest.pc<limit and guest.pc!=entry:
                    raise AssertionError('returned to overwritten overlay')
                return super().fetch()
        c=Guest();c.m[:]=b'\xa5'*65536;c.m[0x1b00:0x1b00+len(old)]=old
        entry=int.from_bytes(player[3:5],'little') if len(player)>=5 else 0x1b10
        song=bytes((i*17)&255 for i in range(512 if ident else 2304));protected=0xe00 if ident else 0x3700;c.m[protected:protected+len(song)]=song
        def word(at,value):c.m[at:at+2]=value.to_bytes(2,'little')
        def getword(at):return int.from_bytes(c.m[at:at+2],'little')
        word(l['_md_player'],0x1500);word(l['sp'],0xb000);c.m[0x1501]=0
        word(0x1000+92,0x1600);c.m[0x1600]=0
        callbacks={48:'read',52:'close'};addresses={}
        for off,name in callbacks.items():
            addr=0x6000+off;word(0x1000+off,addr);c.m[addr]=2;addresses[addr]=name
        c.m[l['_md_entrypoint']]=2
        def trap():
            addr=c.pc-1;name=addresses.get(addr,'driver' if addr==l['_md_entrypoint'] and not counts['read'] else 'play')
            sp=getword(l['sp']);ax=c.a|c.x<<8;drop=0;result=0
            if name=='driver':
                self.assertEqual(ax,0x1000);result=2 # importing and exports both initiate a handoff
            elif name=='read':
                self.assertEqual(ax,0x1500);drop=6;counts['read']+=1
                n=getword(sp);self.assertEqual(getword(sp+2),1);dest=getword(sp+4)
                self.assertEqual(n,limit-0x1b00 if counts['read']==1 else 1)
                if counts['read']==1:self.assertEqual(dest,0x1b00)
                else:self.assertTrue(0xc00<=dest<0x1000)
                data=player[pos[0]:pos[0]+n];pos[0]+=len(data)
                if fault==('read',counts['read']):data=data[:max(0,len(data)-1)]
                c.m[dest:dest+len(data)]=data;result=len(data)
                if fault==('error',counts['read']):c.m[0x1501]=4
            elif name=='close':
                self.assertEqual(ax,0x1500);counts['close']+=1
                if fault==('close',1):result=0xffff
            else:
                self.assertEqual(addr,entry);self.assertEqual(ax,0x1000)
                self.assertEqual(counts['close'],1);self.assertEqual(counts['read'],2)
                counts['play']+=1
            word(l['sp'],sp+drop);c.a=result&255;c.x=result>>8;c.pc=(c.pull()|c.pull()<<8)+1
        # Substitute only the new stage's entry; all loader code is real.
        player=bytearray(player)
        if 0x1b00<=entry<0x1b00+len(player):player[entry-0x1b00]=2
        c.ops[2]=trap;c.x=0x10;c.call(l['_plugin_entry'],a=0,limit=200000)
        self.assertEqual(getword(l['sp']),0xb000);self.assertEqual(c.s,255)
        self.assertEqual(counts['close'],1);self.assertEqual(c.m[protected:protected+len(song)],song)
        allowed=lambda at: (0x80<=at<0x9a or 0x100<=at<0x200 or 0xc00<=at<(0xe00 if ident else 0x1000) or
                            0x1600<=at<0x1650 or 0x1b00<=at<limit or 0xaffa<=at<0xb000)
        self.assertFalse([hex(at) for at in c.writes if not allowed(at)])
        if fault or payload is not None:
            self.assertEqual(counts['play'],0)
            self.assertTrue(bytes(c.m[0x1600:0x1640]).startswith(b'IDENT read/close or version error.' if ident else b'MCSPLAY read/close or version error.'))
        else:self.assertEqual(counts['play'],1)

    def test_real_handoffs_and_every_io_error(self):
        for build in self.builds:
            self.run_handoff(build)
            for fault in (('read',1),('error',1),('error',2),('close',1)):
                self.run_handoff(build,fault)

    def test_bad_headers_truncation_trailing_bytes_and_entry(self):
        for build in self.builds:
            original=build[2]
            for n in (0,4,8,255,len(original)-1):self.run_handoff(build,payload=original[:n])
            self.run_handoff(build,payload=original+b'X')
            self.run_handoff(build,payload=original+bytes(0x1c00))
            for off,value in ((0,0),(1,0),(2,7),(5,0),(6,0),(7,2),(7,129 if original[7]==1 else 1)):
                bad=bytearray(original);bad[off]=value;self.run_handoff(build,payload=bad)
            for target in (0x1b00,0x1b07,0x3700,0x4000,0x1b00+len(original)):
                bad=bytearray(original);bad[3:5]=target.to_bytes(2,'little');self.run_handoff(build,payload=bad)


if __name__=='__main__':unittest.main()
