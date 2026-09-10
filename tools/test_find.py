"""Exercise FIND's resumable walk against ordered directories and text files."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS=PREFIX+r'''
#include <stddef.h>
#include "src/plugins/find.c"
struct MockEntry { char dir[64],name[16];unsigned char type,content;unsigned int date; };
static struct MockEntry entries[1024];
static int count,cursor,opened,reads,cancel_after;
static char current[64];
static unsigned char open_dir(const char* p) {
    strcpy(current,p);cursor=0;opened=1;memset(a.copy_buf,0xA5,512);
    return strcmp(p,"/V/BROKEN")!=0;
}
static unsigned char next_dir(void) {
    while(cursor<count) {
        struct MockEntry* e=&entries[cursor++];
        if(strcmp(e->dir,current))continue;
        strcpy(a.dir_entry->name,e->name);a.dir_entry->type=e->type;a.dir_entry->mdate=e->date;return 1;
    }
    return 0;
}
static void close_dir(void) { opened=0; }
static FILE* open_file(const char* p,const char* mode) {
    int i,j;char full[81];FILE* f;
    if(opened)abort();
    for(i=0;i<count;++i) {
        sprintf(full,"%s/%s",entries[i].dir,entries[i].name);
        if(strcmp(full,p))continue;
        ++reads;
        if(cancel_after && reads==cancel_after)aborted=1;
        if(entries[i].content==2)return NULL;
        f=tmpfile();
        for(j=0;j<507;++j)fputc('x',f);
        fputs(entries[i].content ? "needle across boundary" : "nothing",f);
        rewind(f);return f;
    }
    abort();return NULL;
}
static unsigned char viewing;
static const char* view_keys;
static void message_(const char* p) { if(viewing)printf("\nMSG %s\n",p); }
static void puts_(const char* p) { printf("%s",p); }
static void putc_(char c) { putchar(c); }
static void xy_(unsigned char x,unsigned char y) { printf("\n"); }
static void clear_(void) { puts("\nCLEAR"); }
static char key_(void) { return *view_keys ? *view_keys++ : KEY_ESC; }
int main(int argc,char** argv) {
    FILE* manifest;char row[160],pbuf[80],dbuf[80],rbuf[17];
    unsigned char scratch[512];struct DirEntry de;int type,content,round=0,i,date;
    if(argc>2 && !strcmp(argv[1],"view")) {
        viewing=1;view_keys=argc>4 ? argv[4] : "";
        a.fopen=fopen;a.fread=fread;a.fclose=fclose;a.copy_buf=scratch;
        a.cprintf=printf;a.cputs=puts_;a.cputc=putc_;a.gotoxy=xy_;
        a.clrscr=clear_;a.cgetc=key_;a.message=message_;
        strcpy(pat,argv[3]);plen=strlen(pat);
        memset(QUEUE,0xA5,sizeof host_queue);memset(RESULTS,0xA5,sizeof host_results);memset(POOL,0xA5,sizeof host_pool);
        file_has(argv[2],1);
        for(i=0;i<sizeof host_queue;++i)if((unsigned char)QUEUE[i]!=0xA5)abort();
        for(i=0;i<sizeof host_results;++i)if((unsigned char)RESULTS[i]!=0xA5)abort();
        for(i=0;i<sizeof host_pool;++i)if((unsigned char)POOL[i]!=0xA5)abort();
        return 0;
    }
    if(argc==2) {
        printf("message %zu\n",2+(offsetof(struct A2fcApi,message)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("prompt %zu\n",2+(offsetof(struct A2fcApi,prompt)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("keys_bar %zu\n",2+(offsetof(struct A2fcApi,keys_bar)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("bar_begin %zu\n",2+(offsetof(struct A2fcApi,bar_begin)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("dir_open %zu\n",2+(offsetof(struct A2fcApi,dir_open)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("dir_next %zu\n",2+(offsetof(struct A2fcApi,dir_next)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("dir_close %zu\n",2+(offsetof(struct A2fcApi,dir_close)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("fopen %zu\n",2+(offsetof(struct A2fcApi,fopen)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("fread %zu\n",2+(offsetof(struct A2fcApi,fread)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("fclose %zu\n",2+(offsetof(struct A2fcApi,fclose)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("cprintf %zu\n",2+(offsetof(struct A2fcApi,cprintf)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("sprintf %zu\n",2+(offsetof(struct A2fcApi,sprintf)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("cputc %zu\n",2+(offsetof(struct A2fcApi,cputc)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("cputs %zu\n",2+(offsetof(struct A2fcApi,cputs)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("gotoxy %zu\n",2+(offsetof(struct A2fcApi,gotoxy)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("revers %zu\n",2+(offsetof(struct A2fcApi,revers)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("clrscr %zu\n",2+(offsetof(struct A2fcApi,clrscr)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("cgetc %zu\n",2+(offsetof(struct A2fcApi,cgetc)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("memcpy %zu\n",2+(offsetof(struct A2fcApi,memcpy)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("strcpy %zu\n",2+(offsetof(struct A2fcApi,strcpy)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        printf("strlen %zu\n",2+(offsetof(struct A2fcApi,strlen)-offsetof(struct A2fcApi,panels))/sizeof(void*)*2);
        return 0;
    }
    manifest=fopen(argv[1],"r");
    while(fgets(row,sizeof row,manifest)) {
        struct MockEntry* e=&entries[count++];
        date=0;if(sscanf(row,"%63s %15s %d %d %d",e->dir,e->name,&type,&content,&date)<4)abort();
        e->type=type;e->content=content;e->date=date;
    }
    fclose(manifest);
    a.sprintf=sprintf;a.strcpy=strcpy;a.strlen=strlen;a.memcpy=memcpy;a.message=message_;
    a.dir_open=open_dir;a.dir_next=next_dir;a.dir_close=close_dir;a.dir_entry=&de;
    a.fopen=open_file;a.fread=fread;a.fclose=fclose;a.copy_buf=scratch;
    path=pbuf;dir=dbuf;strcpy(root,"/V");strcpy(QUEUE,root);
    text=atoi(argv[2]);strcpy(pat,text ? "NEEDLE ACROSS" : argv[3]);plen=strlen(pat);
    cancel_after=argc>4 ? atoi(argv[4]) : 0;
    if(argc>5 && atoi(argv[5])>=0) { type_on=1;filter_type=atoi(argv[5]); }
    if(argc>6) { date_on=1;date_from=parse_date(argv[6]);date_to=parse_date(argv[7]);
        printf("DATES %u %u\n",date_from,date_to); }
    nres=0;qhead=0;qtail=1;aborted=cut=0;pool_count=pool_pos=dir_active=ready=0;dir_skip=0;total=0;
    do {
        next_page();printf("PAGE %u %u %u %lu\n",nres,ready,cut,total);
        for(i=0;i<nres;++i)puts(RESULTS+i*RLEN);
        if(++round>100)abort();
    } while(ready);
    printf("READS %d\n",reads);return 0;
}
'''

class Find(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='find-');cls.p=Path(cls.tmp.name);cls.exe=cls.p/'test'
        (cls.p/'test.c').write_text(HARNESS)
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-I',str(ROOT),str(cls.p/'test.c'),'-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_tree(self,entries,text=0,pattern='=',cancel_after=0,filetype=-1,dates=None):
        manifest=self.p/'tree';manifest.write_text(''.join(' '.join(map(str,e))+'\n' for e in entries))
        lines=subprocess.check_output([self.exe,manifest,str(text),pattern,str(cancel_after),str(filetype)]+(list(dates) if dates else []),text=True,timeout=15).splitlines()
        pages=[list(map(int,r.split()[1:])) for r in lines if r.startswith('PAGE ')]
        paths=[r for r in lines if r.startswith('/')];reads=int(lines[-1].split()[1])
        return pages,paths,reads
    def view(self,data,pattern,keys='NNNN'):
        f=self.p/'content';f.write_bytes(data)
        output=subprocess.check_output([self.exe,'view',f,pattern,keys],text=True,timeout=15)
        hits=[(int(m[0],16),m[1]) for m in re.findall(r'^([0-9A-F]{6}) (.*)$',output,re.M)]
        return output,hits
    def test_occurrence_offsets_overlap_boundary_and_24bit(self):
        data=b'x'*507+b'aaaa'+b'x'*66000+b'AAAA'
        output,hits=self.view(data,'AAA')
        self.assertEqual([p for p,_ in hits],[507,508,66511,66512])
        self.assertTrue(all('AAA' in excerpt for _,excerpt in hits))
        self.assertIn('End. ESC Back',output)
    def test_occurrence_pages_and_early_return(self):
        data=b'needle\r'*45
        output,hits=self.view(data,'NEEDLE')
        self.assertEqual([p for p,_ in hits],list(range(0,len(data),7)))
        self.assertEqual(output.count('N Next occurrences'),2)
        _,hits=self.view(data,'NEEDLE','\x1b')
        self.assertEqual(len(hits),20)
        output,hits=self.view(b'needle\r'*20,'NEEDLE')
        self.assertEqual(len(hits),20);self.assertNotIn('N Next occurrences',output)
    def test_occurrence_normalization_eof_and_no_match(self):
        output,hits=self.view(b'\x00\x81'+bytes(c|128 for c in b'needle'),'NEEDLE')
        self.assertEqual(hits,[(2,'..NEEDLE')])
        output,hits=self.view(b'nothing','NEEDLE')
        self.assertEqual(hits,[]);self.assertIn('No occurrences.',output)
    def test_resident_service_addresses_match_api_layout(self):
        offsets=dict(line.split() for line in subprocess.check_output([self.exe,'api'],text=True).splitlines())
        assembly=(ROOT/'src/plugins/find.s').read_text()
        jumps=re.findall(r'_f_(\w+): jmp \(\$(\w+)\)',assembly)
        self.assertEqual(len(jumps),len(offsets))
        for name,address in jumps:self.assertEqual(int(address,16),0x3F9E+int(offsets[name]),name)
    def test_type_and_dates_across_pages_and_directories(self):
        def packed(y,m,d):return (y%100)<<9|m<<5|d
        entries=[('/V',f'F{i:03}',4 if i%2 else 6,1,packed(2000,1,1)) for i in range(100)]
        entries += [('/V','SUB',15,0,0),('/V/SUB','LAST',4,1,packed(1999,12,31)),
                    ('/V','OLD',4,1,packed(1999,12,30)),('/V','NEW',4,1,packed(2000,1,2)),
                    ('/V','UNKNOWN',4,1,0),('/V','BAD',4,1,packed(2001,2,29))]
        for text in (0,1):
            pages,paths,reads=self.run_tree(entries,text,filetype=4,dates=('19991231','20000101'))
            self.assertEqual(paths,[f'/V/F{i:03}' for i in range(1,100,2)]+['/V/SUB/LAST'])
            self.assertEqual([p[0] for p in pages],[20,20,11])
            self.assertEqual(reads,51 if text else 0)
    def test_date_calendar_and_type_zero(self):
        valid=['19400101','19991231','20000229','20240229','20391231']
        for date in valid:
            y,m,d=int(date[:4]),int(date[4:6]),int(date[6:])
            entries=[('/V','MATCH',0,1,(y%100)<<9|m<<5|d)]
            self.assertEqual(self.run_tree(entries,filetype=0,dates=(date,date))[1],['/V/MATCH'])
        for date in ['19391231','20400101','19000229','20010229','20260431','20260001','20260100','20261301','202A0101']:
            self.assertEqual(self.run_tree([('/V','F',4,1,0)],dates=(date,date))[1],[])
            output=subprocess.check_output([self.exe,self.p/'tree','0','=','0','-1',date,date],text=True)
            self.assertIn('DATES 0 0',output)
    def test_page_boundaries_with_truthful_lookahead(self):
        for text in (0,1):
            for n in (0,1,19,20,21,40,41,65):
                entries=[('/V',f'F{i:03}',4,1) for i in range(n)]
                pages,paths,reads=self.run_tree(entries,text)
                self.assertEqual(paths,[f'/V/F{i:03}' for i in range(n)])
                self.assertEqual(pages[-1][1],0)
                self.assertEqual(pages[-1][3],n)
                self.assertEqual([p[1] for p in pages[:-1]],[1]*(len(pages)-1))
                self.assertEqual(reads,n if text else 0)
    def test_large_directory_and_late_subdirectory(self):
        entries=[('/V',f'F{i:03}',4,1) for i in range(300)]
        entries.insert(280,('/V','LATE',15,0))
        entries+=[('/V/LATE','DEEP',15,0),('/V/LATE/DEEP','FOUND',4,1)]
        for text in (0,1):
            pages,paths,reads=self.run_tree(entries,text)
            self.assertEqual(len(paths),301);self.assertEqual(len(set(paths)),301)
            self.assertEqual(paths[-1],'/V/LATE/DEEP/FOUND')
            self.assertFalse(any(p[2] for p in pages))
            self.assertEqual(reads,301 if text else 0)
    def test_sparse_text_matches_do_not_rescan_contents(self):
        entries=[('/V',f'F{i:03}',4,int(i%3==0)) for i in range(100)]
        pages,paths,reads=self.run_tree(entries,1)
        self.assertEqual(paths,[f'/V/F{i:03}' for i in range(0,100,3)])
        self.assertEqual(reads,100)
    def test_queue_overflow_stays_explicit(self):
        entries=[('/V',f'D{i:02}',15,0) for i in range(40)]
        entries += [(f'/V/D{i:02}','F',4,1) for i in range(40)]
        pages,paths,_=self.run_tree(entries)
        self.assertEqual(len(paths),32);self.assertTrue(pages[-1][2])
    def test_unreadable_paths_mark_results_incomplete(self):
        for entries,text in (([('/V','BROKEN',15,0)],0),([('/V','BAD',4,2)],1)):
            pages,paths,_=self.run_tree(entries,text)
            self.assertEqual(paths,[]);self.assertTrue(pages[-1][2])
    def test_long_file_path_is_reported_and_skipped(self):
        d='/V';entries=[]
        for i in range(3):
            name='D'*15;entries.append((d,name,15,0));d+='/'+name
        entries.append((d,'F'*15,4,1))
        pages,paths,_=self.run_tree(entries)
        self.assertEqual(paths,[]);self.assertTrue(pages[-1][2])
    def test_abort_on_later_page_preserves_partial_matches(self):
        entries=[('/V',f'F{i:03}',4,1) for i in range(100)]
        pages,paths,reads=self.run_tree(entries,1,cancel_after=25)
        self.assertEqual(paths,[f'/V/F{i:03}' for i in range(24)])
        self.assertEqual(reads,25);self.assertEqual(pages[-1][1],0)

if __name__=='__main__':unittest.main()
