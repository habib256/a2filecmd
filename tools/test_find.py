"""Exercise FIND's resumable walk against ordered directories and text files."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS=PREFIX+r'''
#include "src/plugins/find.c"
struct MockEntry { char dir[64],name[16];unsigned char type,content; };
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
        strcpy(a.dir_entry->name,e->name);a.dir_entry->type=e->type;return 1;
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
static void message_(const char* p) {}
int main(int argc,char** argv) {
    FILE* manifest=fopen(argv[1],"r");char row[160],pbuf[80],dbuf[80],rbuf[17];
    unsigned char scratch[512];struct DirEntry de;int type,content,round=0,i;
    while(fgets(row,sizeof row,manifest)) {
        struct MockEntry* e=&entries[count++];
        if(sscanf(row,"%63s %15s %d %d",e->dir,e->name,&type,&content)!=4)abort();
        e->type=type;e->content=content;
    }
    fclose(manifest);
    a.sprintf=sprintf;a.strcpy=strcpy;a.strlen=strlen;a.memcpy=memcpy;a.message=message_;
    a.dir_open=open_dir;a.dir_next=next_dir;a.dir_close=close_dir;a.dir_entry=&de;
    a.fopen=open_file;a.fread=fread;a.fclose=fclose;a.copy_buf=scratch;
    path=pbuf;dir=dbuf;root=rbuf;strcpy(root,"/V");strcpy(QUEUE,root);
    text=atoi(argv[2]);strcpy(pat,text ? "NEEDLE ACROSS" : argv[3]);plen=strlen(pat);
    cancel_after=argc>4 ? atoi(argv[4]) : 0;
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
    def run_tree(self,entries,text=0,pattern='=',cancel_after=0):
        manifest=self.p/'tree';manifest.write_text(''.join('%s %s %d %d\n'%e for e in entries))
        lines=subprocess.check_output([self.exe,manifest,str(text),pattern,str(cancel_after)],text=True,timeout=15).splitlines()
        pages=[list(map(int,r.split()[1:])) for r in lines if r.startswith('PAGE ')]
        paths=[r for r in lines if r.startswith('/')];reads=int(lines[-1].split()[1])
        return pages,paths,reads
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
