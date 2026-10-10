"""Execute the production paired-score importer, without writing its inputs."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_mcs import HARNESS, ROOT
import mcs_ref as M
import mcs_score_ref as S

# Capture the normalized score exactly when the real player starts.
HARNESS = HARNESS.replace('return fault==1 || (fault==4 && reads>=2) || ferror(f);',
                         'return (fault>=100 && reads==fault-100) || ferror(f);')
HARNESS = HARNESS.replace('return fault==3?NULL:fopen(p,m);',
                         'return fault==3 && strstr(p,".OBJ")?NULL:fopen(p,m);')
HARNESS = HARNESS.replace('return fclose(f) || fault==2 ? EOF : 0;',
                         'return fclose(f) || fault==10+closes ? EOF : 0;')
HARNESS = HARNESS.replace('if(closes!=1 || s<1', 'if(closes!=2 || s<1')
HARNESS = HARNESS.replace('abort();++started;', 'abort();fwrite(host_song,1,2304,stdout);++started;')


class Score(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='mcs-score-')
        cls.p=Path(cls.tmp.name);cls.h=cls.p/'score.c';cls.h.write_text(HARNESS)
        cls.exe=cls.p/'host'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),
                        str(cls.h),'-o',str(cls.exe)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def run_pair(self,main,obj,good=False,fault=0,selected_obj=False,exe=None):
        src=self.p/'SONG';other=self.p/'SONG.OBJ'
        src.write_bytes(main)
        if obj is None:
            if other.exists():other.unlink()
        else:other.write_bytes(obj)
        command=[str(exe or self.exe),str(other if selected_obj else src),str(fault),'4','','1']
        if exe:command.insert(0,'sim65')
        r=subprocess.run(command,check=True,capture_output=True,timeout=30)
        self.assertEqual(src.read_bytes(),main)
        if obj is not None:self.assertEqual(other.read_bytes(),obj)
        counts=list(map(int,r.stderr.decode().split(maxsplit=7)[:7]))
        self.assertEqual(counts[:2],[1,1] if good else [0,0],r.stderr)
        if good:
            expected=S.score(main,obj)
            self.assertEqual(r.stdout[:2304],expected)
            self.assertEqual(r.stdout[2304:],b''.join(M.frames(expected)))
        else:self.assertEqual(r.stdout,b'')
        return counts

    def test_paired_import_selection_and_silent_staff(self):
        for top,bottom in ((None,None),([(31,10,16),(31,10,200)],None),
                           (None,[(31,10,16),(31,10,200)])):
            main,obj=S.fixture(top,bottom)
            for selected in (False,True):self.run_pair(main,obj,True,selected_obj=selected)

    def test_controls_and_chords(self):
        top=[(31,10,16),(15,10,20),(12,10,24),(14,10,28),
             (13,10,90),(17,10,92),(1,10,96),(2,12,96),
             (10,10,100),(21,10,104),(11,11,108),(25,11,112),
             (19,10,116),(9,10,120),(31,10,150),(0,10,160),(31,10,200)]
        bottom=[(31,10,16),(15,30,20),(11,30,24),(13,30,90),
                (17,30,92),(1,30,96),(22,32,104),(31,10,200)]
        for ts in range(4):self.run_pair(*S.fixture(top,bottom,ts),good=True)

    def test_every_io_stage_and_missing_pair(self):
        main,obj=S.fixture();counts=self.run_pair(main,obj,True)
        for fault in [3,11,12]+list(range(101,101+counts[2])):
            with self.subTest(fault=fault):self.run_pair(main,obj,fault=fault)
        self.run_pair(main,None)

    def test_sizes_and_header_pointers(self):
        main,obj=S.fixture()
        for n in range(len(main)):self.run_pair(main[:n],obj)
        for n in range(len(obj)):self.run_pair(main,obj[:n])
        self.run_pair(main+b'X',obj);self.run_pair(main,obj+b'X')
        for offset in (118,119,120,121,122,123,124,125,126):
            data=bytearray(main);data[offset]=255;self.run_pair(bytes(data),obj)

    def test_malformed_records_and_empty_score(self):
        main,obj=S.fixture()
        for staff in (0,1):
            for offset,value in ((0,32),(1,255),(2,0),(3,255)):
                a,b=bytearray(main),bytearray(obj)
                (a if not staff else b)[(256 if not staff else 0)+8+offset]=value
                self.run_pair(bytes(a),bytes(b))
        self.run_pair(*S.fixture([(31,10,16),(31,10,200)],[(31,10,16),(31,10,200)]))
        many=[(31,10,16)]+[(0,10,100+i) for i in range(600)]+[(31,10,1000)]
        self.run_pair(*S.fixture(many,None))

    def test_real_editor_conversion_when_available(self):
        disk=Path('/tmp/a2fc-mcs-player/dsk/Music Construction Set.dsk')
        if not disk.exists():self.skipTest('private reference disk unavailable')
        from take1_ref import DosImage
        d=DosImage(disk.read_bytes())
        for name in (b'YANKEE DOODLE',b'RACKET',b'ALLEGRO',b'SCALES',b'DIXIE',
                     b'DAISY',b'BUGGY',b'RHYTHM',b'PAT THE HAT'):
            with self.subTest(song=name):
                main=d.read_file(*d.find(name));obj=d.read_file(*d.find(name+b'.OBJ'))
                self.run_pair(main,obj,True)
                original=S.original_export(main,obj,disk.read_bytes())
                for staff,records in enumerate((main[256:],obj)):
                    converted=S.convert(records,staff,main[126])
                    self.assertEqual(converted[:len(original[staff])],original[staff])

    def test_production_c_on_both_cpus(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
        target_path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        main,obj=S.fixture()
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=(target_path.parent/'cfg'/(target+'.cfg')).read_text()
            cfg=cfg.replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1)
            config=self.p/(cpu+'.cfg');config.write_text(cfg);exe=self.p/cpu
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-O','-Cl','-C',str(config),
                            '-I',str(ROOT),'-o',str(exe),str(self.h)],check=True,capture_output=True)
            for selected in (False,True):self.run_pair(main,obj,True,selected_obj=selected,exe=exe)
            for fault in (3,11,12,101,105,110):self.run_pair(main,obj,fault=fault,exe=exe)


if __name__=='__main__':unittest.main()
