"""Run the actual SMALLDOS C against disposable images and stream faults."""
import subprocess
import tempfile
import unittest
from pathlib import Path

import smalldos_ref as ref
from test_pascal import C as IMAGE_HARNESS, ROOT

# Share the image-extractor service mocks (exclusive CREATE, streams,
# close/error/cancel faults), but compile the shipped SMALLDOS entry point.
HARNESS = IMAGE_HARNESS.replace('src/plugins/pascal.c','src/plugins/smalldos.c')
HARNESS = HARNESS.replace('#include <stdio.h>','#include <stdio.h>\n#include <errno.h>')
HARNESS = HARNESS.replace('if(mode==4 && creates==fail_at) return 0x27;',
    'if(creates==fail_at && (mode==4 || mode==29 || mode==30)) '
    'return mode==29?0x48:mode==30?0x4E:0x27;')
HARNESS = HARNESS.replace('f=fopen(path,"rb"); if(f){fclose(f);return 0x47;} /* the name is taken */\n f=fopen(path,"wb");',
                          'fprintf(stderr,"TYPE %u %u\\n",c->type,c->aux);\n f=fopen(path,"wx");')
HARNESS = HARNESS.replace('if(!f) return 0x27;', 'if(!f) return errno==EEXIST?0x47:0x27;')
HARNESS = HARNESS.replace('return fwrite(p,s,n,f);','if(mode==26)errored=f;return fwrite(p,s,n,f);')
HARNESS = HARNESS.replace('joinpath(path,p);f=fopen(path,m);', '''
 if(creates==fail_at && ((mode==27 && !strcmp(m,"wb")) || (mode==28 && !strcmp(m,"rb"))))return NULL;
 joinpath(path,p);f=fopen(path,m);''')
HARNESS = HARNESS.replace('static void progress_(const char* n,unsigned long d,unsigned long t){', '''
static int seeks;
static int seek_(FILE* f,long o,int w){if(mode==22 && ++seeks==fail_at)return -1;return fseek(f,o,w);}
static void progress_(const char* n,unsigned long d,unsigned long t){
 if(creates==fail_at && ((mode==23 && verify_file) || (mode==24 && !verify_file)))cancelled=1;
''')
HARNESS = HARNESS.replace('api.fseek=fseek;','api.fseek=seek_;')

# Keep the SMALLDOS reader independent of Pascal catalogue fault hooks.
# The shared service setup can evolve without importing Pascal globals.
read_start=HARNESS.index('static size_t read_(')
read_end=HARNESS.index('static size_t write_(',read_start)
HARNESS=HARNESS[:read_start]+r'''static size_t read_(void* p,size_t s,size_t n,FILE* f){
 size_t result;
 ++reads;if(mode==2 && reads==fail_at)return 0;
 if(f==image_file && ((mode==14 && reads==fail_at) ||
    ((mode==15 || mode==16) && verify_file && creates==fail_at)))errored=f;
 if(f==verify_file && creates==fail_at){
  if((mode==9 || mode==11) && n==1){errored=f;return 0;}
  if(mode==10 && n>1)errored=f;
 }
 result=fread(p,s,n,f);
 if(mode==25 && f==image_file && reads==fail_at)cancelled=1;
 if(mode==21 && f==verify_file && creates==fail_at && n>1)((unsigned char*)p)[0]^=1;
 if((mode==40 || mode==41 || mode==42) && f==image_file && creates==1 && n==256 && ++data_reads==fail_at){
  cancelled=1;if(mode==41)errored=f;
 }
 return result;
}
'''+HARNESS[read_end:]
HARNESS=HARNESS.replace('static int mode, reads, fail_at, creates, catalogue_reads;',
                        'static int mode, reads, fail_at, creates, catalogue_reads, data_reads, writes;')
HARNESS=HARNESS.replace(" strcpy(sel.name,strrchr(imagepath,'/')+1);",
                        ' strcpy(sel.name,argc>5?argv[5]:"VOL.DSK");')
HARNESS=HARNESS.replace('static size_t write_(const void* p,size_t s,size_t n,FILE* f){','static size_t write_(const void* p,size_t s,size_t n,FILE* f){++writes;')
HARNESS=HARNESS.replace('static int remove_(const char* p){','static int remove_(const char* p){if(mode==42)return -1;')
HARNESS=HARNESS.replace(' fprintf(stderr,"CREATES %d\\n",creates);',
                        ' fprintf(stderr,"CREATES %d\\n",creates);fprintf(stderr,"WRITES %d\\n",writes);')


FILES=[('MENU','A',b'\x08\x08\x0a\0\x80\0\0\0'),
       ('TOPO','B',bytes(range(256))*80),
       ('odd-name','B',b'odd'*100),
       ('LAST','A',b'x')]


class SmallDos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='smalldos-build-')
        p=Path(cls.tmp.name);(p/'test.c').write_text(HARNESS);cls.exe=p/'test'
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),
                        str(p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def run_image(self,data,mode=0,at=1,order='dos',existing=None,filename=None):
        with tempfile.TemporaryDirectory(prefix='smalldos-case-') as tmp:
            p=Path(tmp);image=p/'disk';image.write_bytes(data);out=p/'out';out.mkdir()
            for name,body in (existing or {'KEEP':b'existing bytes'}).items():(out/name).write_bytes(body)
            name=filename or ('VOL.PO' if order=='prodos' else 'VOL.DSK')
            result=subprocess.run([str(self.exe),str(image),str(out)+'/',str(mode),str(at),name],
                                  check=True,capture_output=True,text=True)
            self.assertEqual(image.read_bytes(),data)
            trace=result.stderr.splitlines()
            self.creates=int(next(l.split()[1] for l in trace if l.startswith('CREATES ')))
            self.closes=int(next(l.split()[1] for l in trace if l.startswith('SOURCE-CLOSE ')))
            self.writes=int(next(l.split()[1] for l in trace if l.startswith('WRITES ')))
            self.types=[tuple(map(int,l.split()[1:])) for l in trace if l.startswith('TYPE ')]
            return result.stdout.strip(),{f.name:f.read_bytes() for f in out.iterdir()}

    def expected(self,data,order='dos'):
        return {e['output']:e['data'] for e in ref.volume(data,order)['files']}

    def test_cancel_during_sector_read_prevents_the_next_output_write(self):
        for size in (1,513,4097):
            payload=bytes(i%251 for i in range(size))
            sectors=(size+255)//256
            for flip in (False,True):
                for order in ('dos','prodos'):
                    data=ref.make([('TARGET','B',payload)],flip=flip,order=order)
                    padded=self.expected(data,order)['TARGET']
                    for mode in (40,41,42):
                        for at in range(1,sectors+1):
                            with self.subTest(size=size,flip=flip,order=order,mode=mode,at=at):
                                note,files=self.run_image(data,mode,at,order)
                                expected={'KEEP':b'existing bytes'}
                                if mode==42:expected['TARGET']=padded[:256*(at-1)]
                                self.assertEqual(files,expected)
                                self.assertEqual(self.writes,at-1)
                                self.assertEqual(self.creates,1);self.assertEqual(self.closes,1)
                                self.assertIn('Cleanup failed' if mode==42 else 'stopped',note)

    def test_both_track_directions_and_sector_orders(self):
        for flip in (False,True):
            for order in ('dos','prodos'):
                with self.subTest(flip=flip,order=order):
                    data=ref.make(FILES,flip=flip,order=order)
                    note,files=self.run_image(data,order=order)
                    self.assertEqual(files,{'KEEP':b'existing bytes',**self.expected(data,order)})
                    self.assertEqual(note,'4 extracted, 0 skipped; sector padding kept.')
                    self.assertEqual(self.closes,1)
                    self.assertEqual(self.types,[(0xFC,0x0801),(6,0),(6,0),(0xFC,0x0801)])

    def test_dos_extension_and_unsupported_sources_or_panels(self):
        good=ref.make(FILES)
        note,files=self.run_image(good,filename='VOL.DO')
        self.assertEqual(files,{'KEEP':b'existing bytes',**self.expected(good)})
        for mode,name in ((0,'VOL.WOZ'),(0,'VOL.2MG'),(6,'VOL.DSK'),(7,'VOL.DSK'),(8,'VOL.DSK')):
            with self.subTest(mode=mode,name=name):
                note,files=self.run_image(good,mode,filename=name)
                self.assertEqual(files,{'KEEP':b'existing bytes'})
                self.assertEqual(self.creates,0);self.assertEqual(self.closes,0)

    def test_existing_names_and_normalized_collisions_keep_original_bytes(self):
        data=ref.make([('a-b','B',b'first'),('A.B','B',b'second'),('KEEP','A',b'overwrite')])
        note,files=self.run_image(data)
        self.assertEqual(files,{'KEEP':b'existing bytes','A.B':b'first'.ljust(256,b'\0')})
        self.assertIn('1 extracted, 2 skipped',note)

    def test_creation_io_disk_full_and_access_errors_stop_extraction(self):
        good=ref.make(FILES)
        entries=list(self.expected(good).items())
        for mode in (4,29,30):
            for at in (1,2,4):
                with self.subTest(mode=mode,at=at):
                    note,files=self.run_image(good,mode,at)
                    self.assertEqual(files,{'KEEP':b'existing bytes',**dict(entries[:at-1])})
                    self.assertEqual(self.creates,at)
                    self.assertEqual(self.closes,1)
                    self.assertEqual(note,f'{at-1} extracted, 0 skipped; failed, stopped.')

    def test_all_twenty_entries_and_cross_track_extents(self):
        data=ref.make([(f'FILE{i}','B',bytes([i])*300) for i in range(20)])
        note,files=self.run_image(data)
        self.assertEqual(files,{'KEEP':b'existing bytes',**self.expected(data)})
        self.assertIn('20 extracted, 0 skipped',note)

    def test_malformed_catalogue_creates_nothing(self):
        good=ref.make(FILES)
        off=ref.offset(0,0,True,'dos')+96+3*32  # last entry: validate before any CREATE
        cases=[(1,0),(2,35),(3,16),(4,1),(5,0),(5,127)]
        for field,value in cases:
            with self.subTest(field=field,value=value):
                data=bytearray(good);data[off+field]=value
                note,files=self.run_image(bytes(data))
                self.assertEqual(files,{'KEEP':b'existing bytes'});self.assertEqual(self.creates,0)
                self.assertIn('Not a readable',note)
        data=bytearray(good);data[off+1:off+4]=bytes([2,34,15])
        note,files=self.run_image(bytes(data));self.assertEqual(self.creates,0)
        self.assertEqual(files,{'KEEP':b'existing bytes'})

    def test_bad_size_or_missing_catalogue_creates_nothing(self):
        good=ref.make(FILES)
        for data in (good[:-1],good+b'x',bytes(ref.SIZE)):
            with self.subTest(size=len(data)):
                note,files=self.run_image(data)
                self.assertEqual(files,{'KEEP':b'existing bytes'});self.assertEqual(self.creates,0)
                self.assertIn('Not a readable',note)

    def test_scan_directory_read_seek_errors_and_cancel_create_nothing(self):
        good=ref.make(FILES)
        # 280 scan blocks + EOF, then normal/reversed signature probes,
        # then all four catalogue sectors. Faults are never another skew.
        for mode,at in ([(2,i) for i in (1,282,283,284,285,286,287)]+
                        [(14,i) for i in (1,282,283,284,285,286,287)]+
                        [(22,i) for i in range(1,7)]+[(25,1)]):
            with self.subTest(mode=mode,at=at):
                note,files=self.run_image(good,mode,at)
                self.assertEqual(files,{'KEEP':b'existing bytes'});self.assertEqual(self.creates,0)
                self.assertEqual(self.closes,1)

    def test_write_readback_close_and_open_failures_clean_only_current_output(self):
        good=ref.make(FILES)
        for mode,at in ((3,2),(9,2),(10,2),(15,2),(17,2),(19,2),(21,2),
                        (23,2),(24,2),(26,1),(27,2),(28,2),(5,1)):
            with self.subTest(mode=mode,at=at):
                note,files=self.run_image(good,mode,at)
                expected={'KEEP':b'existing bytes'}
                if mode not in (26,5):expected['MENU']=self.expected(good)['MENU']
                self.assertEqual(files,expected)
                self.assertIn('stopped',note);self.assertEqual(self.closes,1)

    def test_source_data_read_and_seek_failures_do_not_validate_output(self):
        good=ref.make(FILES)
        # First file data (288), then its verification source read (289).
        for mode,at in ((2,288),(14,288),(22,7),(2,289),(14,289),(22,8)):
            with self.subTest(mode=mode,at=at):
                note,files=self.run_image(good,mode,at)
                self.assertEqual(files,{'KEEP':b'existing bytes'})
                self.assertEqual(self.creates,1);self.assertEqual(self.closes,1)
                self.assertIn('failed, stopped',note)

    def test_failed_cleanup_keeps_current_output_and_reports_it(self):
        good=ref.make(FILES)
        for mode in (11,16,18,20):
            with self.subTest(mode=mode):
                note,files=self.run_image(good,mode,2)
                expected=self.expected(good)
                self.assertEqual(files,{'KEEP':b'existing bytes','MENU':expected['MENU'],'TOPO':expected['TOPO']})
                self.assertIn('Cleanup failed',note);self.assertEqual(self.creates,2)

    def test_final_source_close_failure_retains_verified_outputs(self):
        good=ref.make(FILES)
        for mode in (12,13):
            with self.subTest(mode=mode):
                note,files=self.run_image(good,mode)
                self.assertEqual(files,{'KEEP':b'existing bytes',**self.expected(good)})
                self.assertIn('failed, stopped',note);self.assertEqual(self.closes,1)

    def test_real_wilderness_images_and_prodos_conversion(self):
        base=ROOT.parent/'pom2games/wilderness'
        sources=[(base/'build/SIERRA.dsk',True,20),
                 (base/'original/WILDERNESS_DEMO.dsk',False,10)]
        if not all(p.is_file() for p,_,_ in sources):self.skipTest('local Wilderness fixtures absent')
        for path,flip,count in sources:
            original=path.read_bytes();v=ref.volume(original)
            self.assertEqual(v['flip'],flip);self.assertEqual(len(v['files']),count)
            for order in ('dos','prodos'):
                with self.subTest(image=path.name,order=order):
                    data=original if order=='dos' else ref.convert(original,'dos','prodos')
                    note,files=self.run_image(data,order=order)
                    self.assertEqual(files,{'KEEP':b'existing bytes',**self.expected(data,order)})
                    self.assertIn(f'{count} extracted',note)
            self.assertEqual(path.read_bytes(),original)
        journey=base/'build/JOURNEY.dsk'
        if journey.is_file():
            note,files=self.run_image(journey.read_bytes())
            self.assertEqual(files,{'KEEP':b'existing bytes'});self.assertEqual(self.creates,0)


if __name__=='__main__':unittest.main()
