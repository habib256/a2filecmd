"""Actual read-only DOSREC C: sparse records, I/O faults and both CPUs."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_dos_stream import HARNESS, Streams, ROOT, make_disk, offset, DosImage

H=HARNESS.replace('src/plugins/dosview.c','src/plugins/dosrec.c')
# New reader consumes decimal digits/Return and uses N for next record.
H=H.replace("c=='N'?' ':c", "c=='T'?KEY_RETURN:c")
H=H.replace('static void clear(void){}','static void clear(void){puts("CLEAR");}')

class Records(unittest.TestCase):
    run_disk=Streams.run_disk
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dos-record-tests-',dir='/tmp');cls.p=Path(cls.tmp.name)
        (cls.p/'h.c').write_text(H);cls.exe=cls.p/'host'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'h.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_holes_nul_not_eof_and_stale_sizes(self):
        disk=bytearray(make_disk([('TEXT',0,b'A\0END'+bytes(251)+b'B'*256+b'C'*256)]))
        t,s=DosImage(disk).find(b'TEXT');ts=offset(t,s);disk[ts+14:ts+16]=b'\0\0'
        for image in (0,1,2):
            for size in (0,1,0xffffff):
                out,_,_=self.run_disk(bytes(disk),image=image,size=size,keys='TNNPE',mode='view')
                self.assertIn(b'41 00 45 4E 44',out);self.assertIn(b'-- -- --',out);self.assertIn(b'43 43 43',out)
                self.assertIn(b'DOS record 2',out);self.assertIn(b'EOF unknown',out)
    def test_skipped_ts_range_and_last_partial_record(self):
        disk=bytearray(make_disk([('TEXT',0,b'A'*256)]));t,s=DosImage(disk).find(b'TEXT');ts=offset(t,s)
        disk[ts+5:ts+7]=(244).to_bytes(2,'little')
        for image in (0,1,2):
            out,_,_=self.run_disk(bytes(disk),image=image,mode='stream')
            self.assertEqual(out,bytes(244*256)+b'A'*256)
            out,_,_=self.run_disk(bytes(disk),image=image,keys='4096T'+'N'*15+' '*4+'E',mode='view')
            self.assertIn(b'Allocated extent 62720 B',out);self.assertIn(b'41 41 41',out)
    def test_navigation_length_edit_cancel_and_empty(self):
        disk=make_disk([('TEXT',0,b'X'*2048)])
        out,_,_=self.run_disk(disk,mode='view',keys='600T BRL0T128TNPE')
        self.assertIn(b'length 600, +288',out);self.assertIn(b'length 128',out);self.assertIn(b'DOS record 1',out)
        out,_,_=self.run_disk(disk,mode='view',keys='E');self.assertNotIn(b'DOS record 0',out)
        disk=bytearray(disk);t,s=DosImage(disk).find(b'TEXT');disk[offset(t,s)+12:offset(t,s)+256]=bytes(244)
        out,_,note=self.run_disk(bytes(disk),mode='view',good=False);self.assertIn('no allocated',note);self.assertNotIn(b'CLEAR',out)
    def test_structure_errors_before_display(self):
        disk=make_disk([('TEXT',0,b'X'*256)]);t,s=DosImage(disk).find(b'TEXT');ts=offset(t,s)
        for at,value in ((ts+5,b'\1\0'),(ts+5,(610).to_bytes(2,'little')),(ts+12,b'\0\1'),(ts+14,disk[ts+12:ts+14]),(ts+1,bytes([t,s]))):
            bad=bytearray(disk);bad[at:at+len(value)]=value
            out,_,_=self.run_disk(bytes(bad),mode='view',keys='TE',good=False);self.assertNotIn(b'CLEAR',out)
        self.run_disk(make_disk([('TEXT',4,b'\0 \1\0X')]),typ=6,mode='view',keys='TE',good=False)
    def test_all_read_open_seek_close_errors_preserve_source(self):
        disk=make_disk([('TEXT',0,b'X'*768)])
        for image in (0,1,2):
            _,counts,_=self.run_disk(disk,image=image,mode='view',keys='TE')
            faults=list(range(1,counts[1]+1))
            if image:faults += [1001,1002,1003,1004]
            for fault in faults:
                out,_,note=self.run_disk(disk,image=image,mode='view',keys='TE',fault=fault,good=False)
                self.assertIn('error',note);self.assertNotIn(b'DOS record 0',out)
    def test_cc65_both_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
        targetpath=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        disk=make_disk([('TEXT',0,b'A\0B'+bytes(253)+b'Z'*512)])
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=(targetpath.parent/'cfg'/(target+'.cfg')).read_text();config=self.p/(target+'.cfg');config.write_text(cfg.replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
            exe=self.p/target
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(config),'-I',str(ROOT),'-o',str(exe),str(self.p/'h.c')],check=True,capture_output=True)
            for image in (0,1,2):
                expected,_,_=self.run_disk(disk,image=image,keys='128TNNE',mode='view')
                actual,_,_=self.run_disk(disk,image=image,keys='128TNNE',mode='view',exe=exe)
                self.assertEqual(actual,expected)

if __name__=='__main__':unittest.main()
