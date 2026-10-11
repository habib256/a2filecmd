"""Execute RESCUE's full C entry point on disposable files and close faults."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
static int error_(FILE*);
static void clear_(FILE*);
#define ferror error_
#define clearerr clear_
#include "src/plugins/rescue.c"
#undef ferror
#undef clearerr
static FILE* errored;
static int error_(FILE* f){return f==errored || ferror(f);}
static void clear_(FILE* f){if(f==errored)errored=0;clearerr(f);}
static const char *input_path, *destination;
static char mapped[256], input[17], note_text[80], full[81], other_full[81];
static FILE* source_stream;
static unsigned int mode, source_closes, attempts, step;
static unsigned int file_opens,creates,questions,dir_closes;
static unsigned int file_closes,live_streams;
static unsigned char complete_log;
static unsigned char directory_error;
static unsigned char disk_mode;
static unsigned long actual_size;
static struct DirEntry directory_entry;
static const char* translate(const char* p) {
    if(!strcmp(p,"/V/DATA"))return input_path;
    if(strncmp(p,"/D/",3))abort();
    sprintf(mapped,"%s/%s",destination,p+3);return mapped;
}
static FILE* open_file(const char* p,const char* m) {
    ++file_opens;
    if(mode==41 && complete_log && !strcmp(p,logpath))return NULL;
    FILE* f=fopen(translate(p),m);
    if(f)++live_streams;
    if(!strcmp(p,"/V/DATA"))source_stream=f;
    return f;
}
static int close_file(FILE* f) {
    unsigned char failed=0;
    ++file_closes;if(!live_streams)abort();--live_streams;
    if(f==out && (mode==33 || mode==37)){cancelled=1;failed=mode==37;}
    if(f==logfile && complete_log && (mode==36 || mode==39 || mode>=41)){cancelled=1;failed=mode==39;}
    if(f==logfile && mode==43 && !complete_log && cancelled)failed=1;
    if(f==source_stream) {
        source_stream=0;
        ++source_closes;
        failed=(mode==1 || mode==2) && source_closes==1;
        if(mode==34 || mode==38){cancelled=1;failed=mode==38;}
    }
    if(f==errored)errored=0;
    if(fclose(f))return EOF;
    return failed?EOF:0;
}
static size_t read_file(void* p,size_t s,size_t n,FILE* f) {
    if(mode==32 && f==source_stream && n==1 && ftell(f)==actual_size)cancelled=1;
    if(f==source_stream && (mode==2 || mode==5) && ++attempts<=30)return 0;
    if(f==source_stream && mode==4 && n==1 && ftell(f)==actual_size) {
        fputc(0,f); /* genuine read-stream error, not a clean EOF */
        return 0;
    }
    {long at=ftell(f);size_t got=fread(p,s,n,f);
    if(f==source_stream && n>1 && !at &&
       ((mode==6 && ++attempts==1) || mode==7 || mode==12))errored=f;
    return got;}
}
static size_t write_file(const void* p,size_t s,size_t n,FILE* f){
    long at=ftell(f);size_t got=fwrite(p,s,n,f);
    if(f==logfile){
        complete_log=n>=9 && !memcmp(p,"COMPLETE ",9);
        if(mode==42 && n>=11 && !memcmp(p,"INCOMPLETE:",11))errored=f;
        if(complete_log && (mode==35 || mode==40)){
            cancelled=1;if(mode==40)errored=f;
        }
    }
    if((f==out && ((mode==8 && !at) || (mode==9 && at+n==actual_size))) ||
       (f==logfile && ((mode==10 && !at) ||
        (mode==11 && n>=9 && !memcmp(p,"COMPLETE ",9)) ||
        (mode==12 && n>=5 && !memcmp(p,"ZERO ",5)))))errored=f;
    return got;
}
static unsigned char mock_mli(unsigned char cmd,void* p) {
    FILE* f;
    if(cmd==0x80) {
        struct Block* b=p;size_t n;
        if(!disk_mode || b->unit!=0x60)abort();
        if(mode==24)return 0x27;
        f=fopen(input_path,"rb");if(!f)return 0x27;
        if(fseek(f,(unsigned long)b->block*512,SEEK_SET)){fclose(f);return 0x27;}
        n=fread(b->buffer,1,512,f);fclose(f);return n==512?0:0x27;
    }
    if(cmd==0xC5) {
        struct Online* o=p;memset(o->buffer,0,256);
        o->buffer[0]=0x61;o->buffer[1]='V';o->buffer[16]=0x71;o->buffer[17]='D';return 0;
    }
    if(cmd==0xC4) {
        struct Info* i=p;i->storage=mode==13?0:(mode>=17 && mode<=19?mode-16:2);
        if(mode>=20 && mode<=23)i->storage=mode==20?4:(mode==21?5:(mode==22?13:15));
        i->access=mode==14?0:(mode==15?2:1);
        return mode==16?0x27:0;
    }
    if(cmd==0xC0) {
        ++creates;
        struct Create* c=p;char name[65];
        memcpy(name,c->path+1,c->path[0]);name[c->path[0]]=0;
        f=fopen(translate(name),"wx");if(!f)return 0x47;
        return fclose(f)?0x27:0;
    }
    abort();
}
static unsigned char open_dir(const char* p){(void)p;step=0;return mode!=26;}
static unsigned char next_entry(void){
    if(mode==27){directory_error=0x27;return 0;}
    if(step++)return 0;
    if(mode==31)directory_error=0x27;
    strcpy(directory_entry.name,mode==28?"OTHER":"DATA");directory_entry.size=actual_size;return 1;
}
static unsigned char close_dir(void){++dir_closes;return mode==29?0x27:mode==30?1:directory_error;}
static char choose(void){return disk_mode?'V':'F';}
static void show(const char* s){(void)s;}
static unsigned char yes(const char* s){
    ++questions;
    FILE* f;(void)s;
    if(mode==3){f=fopen(input_path,"ab");fputs("added tail",f);fclose(f);}
    return 1;
}
static unsigned char prompt(const char* s,const char* initial,unsigned char hex)
{(void)s;(void)initial;(void)hex;strcpy(input,"RECOVER");return 1;}
static void clear_screen(void){}
static int print_screen(const char* s,...){(void)s;return 0;}
static void bar(const char* s,unsigned long d,unsigned long t){(void)s;(void)d;(void)t;}
int main(int argc,char** argv) {
    static struct A2fcApi api;static struct Panel panels[2];static struct Entry selected;
    static unsigned char active,scratch[512];FILE* f;
    (void)argc;input_path=argv[1];destination=argv[2];mode=atoi(argv[3]);
    disk_mode=argc>4;
    f=fopen(input_path,"rb");if(!f)return 2;
    fseek(f,0,SEEK_END);actual_size=ftell(f);fclose(f);
    strcpy(panels[0].path,"/V");strcpy(panels[1].path,"/D");
    strcpy(selected.name,"DATA");selected.type=4;strcpy(full,"/V/DATA");
    api.panels=panels;api.active=&active;api.selected=&selected;api.note=note_text;
    api.copy_buf=scratch;api.full=full;api.other_full=other_full;api.input=input;
    api.mli=mock_mli;api.memcpy=memcpy;api.memset=memset;api.strcpy=strcpy;
    api.strcmp=strcmp;api.strlen=strlen;api.sprintf=sprintf;api.message=show;
    api.cgetc=choose;api.confirm=yes;api.prompt=prompt;api.clrscr=clear_screen;
    api.cprintf=print_screen;api.progress_bar=bar;api.dir_entry=&directory_entry;
    api.dir_open=open_dir;api.dir_next=next_entry;api.dir_close=(void (*)(void))close_dir;
    api.fopen=open_file;api.fclose=close_file;api.fread=read_file;api.fwrite=write_file;api.fseek=fseek;
    plugin_entry(&api);puts(note_text);
    if(mode>=26)fprintf(stderr,"STATE %u %u %u %u\n",file_opens,creates,questions,dir_closes);
    if(mode>=32)fprintf(stderr,"STREAMS %u %u %u\n",file_opens,file_closes,live_streams);
    return 0;
}
'''


class RescueClose(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='rescue-build-')
        folder = Path(cls.build.name)
        source = folder / 'test.c'
        source.write_text(HARNESS)
        cls.exe = folder / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT), str(source), '-o', str(cls.exe)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def run_case(self, mode, size):
        with tempfile.TemporaryDirectory(prefix='rescue-close-') as folder:
            folder = Path(folder)
            payload = bytes(i % 251 for i in range(size))
            source = folder / 'DATA'
            source.write_bytes(payload)
            note = subprocess.check_output([str(self.exe), str(source), str(folder), str(mode)], text=True, timeout=10)
            self.assertEqual(source.read_bytes(), payload + (b'added tail' if mode == 3 else b''))
            output=folder/'RECOVER.REC'
            recovered=output.read_bytes() if output.exists() else None
            log = (folder / 'RECOVER.LOG').read_bytes()
            if mode in (6,7):
                self.assertNotIn('incomplete',note)
                self.assertIn(b'1 retried.',log)
                self.assertEqual(recovered,payload if mode==6 else bytes(min(512,size))+payload[512:])
                self.assertIn(b'0 zero-filled' if mode==6 else b'1 zero-filled',log)
            elif mode>=8:
                self.assertIn('incomplete',note)
                self.assertTrue(log.endswith(b'INCOMPLETE: cancelled, source changed, or I/O error. Keep partial output.\r'))
                if mode!=11:self.assertNotIn(b'COMPLETE ',log)
                expected={8:payload[:512],9:payload,10:None,11:payload,12:b''}[mode]
                self.assertEqual(recovered,expected)
            elif mode in (1, 2, 3, 4):
                self.assertIn('incomplete', note)
                self.assertNotIn(b'COMPLETE ', log)
                self.assertIn(b'INCOMPLETE:', log)
                self.assertEqual(recovered, b'' if mode == 2 else payload)
            else:
                self.assertNotIn('incomplete', note)
                self.assertIn(b'COMPLETE ', log)
                self.assertEqual(recovered, bytes(512) + payload[512:] if mode == 5 else payload)

    def test_full_count_read_errors_are_retried_and_logged(self):
        for mode in (6,7):
            for size in (100,1600):
                with self.subTest(mode=mode,size=size):self.run_case(mode,size)

    def test_source_metadata_must_allow_standard_file_reads(self):
        for mode in range(13,24):
            for size in (0,100,1600):
                with self.subTest(mode=mode,size=size), tempfile.TemporaryDirectory(prefix='rescue-metadata-') as folder:
                    folder=Path(folder);source=folder/'DATA'
                    payload=bytes(i%251 for i in range(size));source.write_bytes(payload)
                    sentinel=folder/'KEEP';sentinel.write_bytes(b'existing destination bytes')
                    note=subprocess.check_output([str(self.exe),str(source),str(folder),str(mode)],text=True,timeout=10)
                    self.assertEqual(source.read_bytes(),payload)
                    self.assertEqual(sentinel.read_bytes(),b'existing destination bytes')
                    if mode<=16 or mode>=20:
                        self.assertIn('readable standard file',note)
                        self.assertEqual(sorted(p.name for p in folder.iterdir()),['DATA','KEEP'])
                    else:
                        self.assertNotIn('incomplete',note)
                        self.assertEqual((folder/'RECOVER.REC').read_bytes(),payload)
                        self.assertIn(b'COMPLETE ',(folder/'RECOVER.LOG').read_bytes())

    def test_raw_volume_cannot_end_before_its_own_header(self):
        for total,mode in ((0,0),(1,0),(2,0),(7,24),(7,25),(3,0),(7,0),(280,0)):
            with self.subTest(total=total,mode=mode), tempfile.TemporaryDirectory(prefix='rescue-volume-') as folder:
                folder=Path(folder);source=folder/'disk.po';sentinel=folder/'KEEP'
                payload=bytearray(i%251 for i in range(max(3,total)*512))
                payload[1028]=0xD1 if mode==25 else 0xF1
                payload[1065:1067]=total.to_bytes(2,'little')
                source.write_bytes(payload);sentinel.write_bytes(b'existing destination bytes')
                note=subprocess.check_output([str(self.exe),str(source),str(folder),str(mode),'disk'],text=True,timeout=10)
                self.assertEqual(source.read_bytes(),payload)
                self.assertEqual(sentinel.read_bytes(),b'existing destination bytes')
                if total<3 or mode:
                    self.assertEqual(sorted(p.name for p in folder.iterdir()),['KEEP','disk.po'])
                    self.assertIn('volume size',note)
                else:
                    self.assertNotIn('incomplete',note)
                    self.assertEqual((folder/'RECOVER.P01').read_bytes(),payload)
                    self.assertIn(('COMPLETE %d bytes'%len(payload)).encode(),(folder/'RECOVER.LOG').read_bytes())

    def test_full_count_write_errors_never_report_success(self):
        for mode in (8,9,10,11):
            for size in (0,100,1600):
                with self.subTest(mode=mode,size=size):self.run_case(mode,size)
        self.run_case(12,1600)

    def test_growing_source_is_not_reported_complete(self):
        for size in (0, 100, 1600):
            with self.subTest(size=size):
                self.run_case(3, size)

    def test_final_probe_read_error_is_not_a_clean_eof(self):
        for size in (0, 100, 1600):
            with self.subTest(size=size):
                self.run_case(4, size)

    def test_logged_missing_chunk_can_still_complete(self):
        self.run_case(5, 1600)

    def test_closed_source_is_required_before_complete(self):
        for size in (100, 1600):
            with self.subTest(size=size):
                self.run_case(1, size)

    def test_source_close_error_before_zero_chunk_is_not_ignored(self):
        self.run_case(2, 1600)

    def test_successful_recovery_retains_exact_bytes(self):
        for size in (0, 100, 1600):
            with self.subTest(size=size):
                self.run_case(0, size)

    def test_uncertain_directory_size_refuses_before_any_creation(self):
        for mode in range(26,32):
            for size in (0,100,1600):
                for existing in (False,True):
                    with self.subTest(mode=mode,size=size,existing=existing), tempfile.TemporaryDirectory(prefix='rescue-directory-') as folder:
                        folder=Path(folder);source=folder/'DATA'
                        payload=bytes(i%251 for i in range(size));source.write_bytes(payload)
                        (folder/'KEEP').write_bytes(b'unrelated bytes')
                        if existing:
                            (folder/'RECOVER.LOG').write_bytes(b'previous log')
                            (folder/'RECOVER.REC').write_bytes(b'previous recovery')
                        before={p.name:p.read_bytes() for p in folder.iterdir()}
                        run=subprocess.run([str(self.exe),str(source),str(folder),str(mode)],text=True,capture_output=True,check=True,timeout=10)
                        self.assertIn("directory entry",run.stdout)
                        self.assertEqual(tuple(map(int,run.stderr.split()[1:])),(0,0,0,0 if mode==26 else 1))
                        self.assertEqual({p.name:p.read_bytes() for p in folder.iterdir()},before)

    def test_late_cancel_keeps_recovered_bytes_and_marks_log_incomplete(self):
        for disk in (False,True):
            for size in ((3*512,7*512,280*512) if disk else (0,1,512,1600)):
                for mode in range(32,44):
                    if disk and mode in (32,34,38):continue
                    with self.subTest(disk=disk,size=size,mode=mode), tempfile.TemporaryDirectory(prefix='rescue-cancel-') as folder:
                        folder=Path(folder);source=folder/'DATA'
                        payload=bytearray(i%251 for i in range(size))
                        if disk:
                            payload[1028]=0xF1
                            payload[1065:1067]=(size//512).to_bytes(2,'little')
                        source.write_bytes(payload)
                        (folder/'KEEP').write_bytes(b'unrelated bytes')
                        (folder/'PREVIOUS.REC').write_bytes(b'previous recovery')
                        args=[str(self.exe),str(source),str(folder),str(mode)]+(['disk'] if disk else [])
                        run=subprocess.run(args,text=True,capture_output=True,check=True,timeout=10)
                        self.assertIn('incomplete',run.stdout)
                        self.assertEqual(source.read_bytes(),payload)
                        self.assertEqual((folder/'KEEP').read_bytes(),b'unrelated bytes')
                        self.assertEqual((folder/'PREVIOUS.REC').read_bytes(),b'previous recovery')
                        self.assertEqual((folder/('RECOVER.P01' if disk else 'RECOVER.REC')).read_bytes(),payload)
                        log=(folder/'RECOVER.LOG').read_bytes()
                        if mode==41:
                            self.assertIn(b'COMPLETE ',log)
                            self.assertNotIn(b'INCOMPLETE:',log)
                        else:
                            self.assertTrue(log.endswith(b'INCOMPLETE: cancelled, source changed, or I/O error. Keep partial output.\r'),log)
                        if mode>=41:self.assertIn('log update failed',run.stdout)
                        if mode in (32,33,34,37,38):self.assertNotIn(b'COMPLETE ',log)
                        streams=tuple(map(int,run.stderr.splitlines()[-1].split()[1:]))
                        self.assertEqual(streams[0]-(mode==41),streams[1])
                        self.assertEqual(streams[2],0)


if __name__ == '__main__':
    unittest.main()
