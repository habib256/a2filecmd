"""The tree walks (count, copy, delete) run without recursion on a bounded
state: order, bounds, refusals and error stops, on a fake file system."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_file_safety import SOURCE, section, ROOT

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MAX_ENTRIES 400          /* host structs are padded: keep the pool-fits check true */
#define PATH_LEN 65
#define remove fs_remove
#define rmdir fs_rmdir
#define mkdir fs_mkdir
struct Entry { unsigned char bytes[29]; };
''' + section('#define POOL_SIZE 213', '/* ---------------------------------------------------------------------- */\n/* MLI: GET_FILE_INFO') + r'''
static unsigned char table[MAX_ENTRIES * sizeof(struct Entry)];
static char full[PATH_LEN], other_full[PATH_LEN];
/* The fake file system: absolute paths, directories flagged. */
#define FS_MAX 600
static char fs_path[FS_MAX][80];   /* longer than a ProDOS path: the walk must refuse, not the harness */ static unsigned char fs_dir[FS_MAX], fs_gone[FS_MAX]; static unsigned fs_n;
static void add(const char* path, unsigned char dir){strcpy(fs_path[fs_n],path);fs_dir[fs_n]=dir;fs_gone[fs_n]=0;++fs_n;}
static int find(const char* path){unsigned i;for(i=0;i<fs_n;++i)if(!fs_gone[i]&&!strcmp(fs_path[i],path))return i;return -1;}
static int parent_is(const char* path,const char* dir){size_t d=strlen(dir);return !strncmp(path,dir,d)&&path[d]=='/'&&!strchr(path+d+1,'/');}
static char unreadable[PATH_LEN];
static unsigned char tree_room=1,fail_mkdir,fail_copy,abort_after;
static char fail_remove[PATH_LEN];
static unsigned lists,mkdirs,copies,removes,rmdirs,aborts,errors,toolongs,dirfails,bars,max_depth_seen;
static char log_[8192],errname[32];
static unsigned char progress_abort;static unsigned int progress_total,progress_done,a2fc_ops;
static unsigned char tree_stack_ok(void){return tree_room;}
static unsigned char dir_error;
static unsigned char list_dir(const char* path,unsigned char base,unsigned char* count){
 unsigned i,n=0;++lists;
 if(!tree_stack_ok()||find(path)<0||!strcmp(path,unreadable))return 0;
 for(i=0;i<fs_n;++i){
  if(fs_gone[i]||!parent_is(fs_path[i],path))continue;
  if(base+n>=POOL_SIZE)return 0;
  strcpy(pool[base+n].name,strrchr(fs_path[i],'/')+1);pool[base+n].type=fs_dir[i]?0x0F:4;pool[base+n].aux=i;++n;
 }
 *count=n;return 1;
}
''' + section('/* Appends "/name" to a path;', '/* GET_FILE_INFO: lighter than an fopen') + r'''
static unsigned char exists(const char* path){return find(path)>=0;}
static int mkdir(const char* path){++mkdirs;if(fail_mkdir)return -1;add(path,1);strcat(log_,"M ");strcat(log_,path);strcat(log_,"\n");return 0;}
static unsigned char copy_file(const char* name,unsigned char type,unsigned aux){
 ++copies;if(fail_copy&&copies>=fail_copy)return 0;
 if(strcmp(strrchr(full,'/')+1,name)||strcmp(strrchr(other_full,'/')+1,name))abort();
 if(find(full)<0||fs_dir[find(full)])abort();          /* the source file exists and is a file */
 { char parent[PATH_LEN];strcpy(parent,other_full);*strrchr(parent,'/')=0;if(find(parent)<0)abort(); }  /* its directory exists already */
 add(other_full,0);strcat(log_,"C ");strcat(log_,full);strcat(log_," > ");strcat(log_,other_full);strcat(log_,"\n");return 1;
}
static int remove(const char* path){int i=find(path);++removes;if(i<0||fs_dir[i]||!strcmp(path,fail_remove))return -1;fs_gone[i]=1;strcat(log_,"R ");strcat(log_,path);strcat(log_,"\n");return 0;}
static int rmdir(const char* path){int i=find(path);unsigned k;++rmdirs;if(i<0||!fs_dir[i])return -1;
 for(k=0;k<fs_n;++k)if(!fs_gone[k]&&parent_is(fs_path[k],path))return -1;   /* not empty: children must go first */
 fs_gone[i]=1;strcat(log_,"D ");strcat(log_,path);strcat(log_,"\n");return 0;}
static void report_error(const char* what){++errors;strcpy(errname,what);}
static void too_long(void){++toolongs;}
static void dir_fail(void){++dirfails;}
static unsigned char abort_key(void){++aborts;if(abort_after&&aborts>=abort_after)progress_abort=1;return progress_abort;}
static void progress_bar(const char* name,unsigned long a,unsigned long b){++bars;}
''' + section('/* Drops the last "/name" of a path. */', '/* The walk is resident, deleting included') + r'''
#include "src/tree_walk.h"
#define walk_count() walk_tree(WALK_COUNT)
#define walk_copy() walk_tree(WALK_COPY)
''' + section('static unsigned char delete_tree(void)', '/* The source of a moved directory') + r'''
static void deep(unsigned levels){ /* /V/T/A/A/... with a file at the bottom */
 char path[80];unsigned k;add("/V",1);add("/V/T",1);add("/D",1);add("/D/T",1);strcpy(path,"/V/T");
 for(k=0;k<levels;++k){strcat(path,"/A");add(path,1);}
 strcat(path,"/F");add(path,0);
}
static void bushy(void){unsigned k;char n[PATH_LEN];add("/V",1);add("/V/T",1);add("/D",1);add("/D/T",1);
 for(k=0;k<3;++k){sprintf(n,"/V/T/F%u",k);add(n,0);}
 add("/V/T/S",1);add("/V/T/S/G",0);add("/V/T/S/Q",1);add("/V/T/S/Q/H",0);add("/V/T/S/I",0);add("/V/T/Z",0);add("/V/T/E",1);
}
static unsigned alive(void){unsigned i,n=0;for(i=0;i<fs_n;++i)if(!fs_gone[i])++n;return n;}
int main(int argc,char** argv){
 int s=atoi(argv[1]);unsigned r;
 pool=(struct Mini*)table;strcpy(full,"/V/T");strcpy(other_full,"/D/T");
 if(s==1){ bushy();r=walk_count();if(r!=7||strcmp(full,"/V/T")||strcmp(other_full,"/D/T")||errors||toolongs||dirfails)return 1;return 0; }
 if(s==2){ deep(29);r=walk_count();if(r!=1||strcmp(full,"/V/T"))return 1;   /* a 64-character file path, walked */
  fs_n=0;strcpy(full,"/V/T");strcpy(other_full,"/D/T");deep(30);r=walk_count();if(r!=0xFFFF||dirfails||toolongs!=1)return 3;   /* the deepest directory is 64 characters, its file's path 66: the count refuses the tree before anything is copied or erased, and says "Path too long" (bug hunt 2: it said nothing, its callers "Directory unreadable or too large/deep.") */
  fs_n=0;strcpy(full,"/V/T");strcpy(other_full,"/D/T");toolongs=0;deep(31);r=walk_count();if(r!=0xFFFF||dirfails||toolongs!=1)return 2;  /* one more: the path bound */
  return 0; }
 if(s==3){ unsigned k;char n[PATH_LEN];add("/V",1);add("/V/T",1);for(k=0;k<200;++k){sprintf(n,"/V/T/F%03u",k);add(n,0);}
  add("/V/T/S",1);for(k=0;k<20;++k){sprintf(n,"/V/T/S/G%02u",k);add(n,0);}
  r=walk_count();if(r!=0xFFFF)return 1;     /* 201 + 20 entries along one path: the pool bound */
  fs_n=0;strcpy(full,"/V/T");strcpy(other_full,"/D/T");add("/V",1);add("/V/T",1);for(k=0;k<212;++k){sprintf(n,"/V/T/F%03u",k);add(n,0);}
  r=walk_count();if(r!=212)return 2;        /* 212 entries at one level fit */
  return 0; }
 if(s==4){ bushy();strcpy(unreadable,"/V/T/S/Q");r=walk_count();if(r!=0xFFFF||dirfails!=1)return 1;   /* the count says why itself now */
  r=walk_copy();if(r!=0xFFFF||dirfails!=2||copies>3)return 2;   /* copy stops where the walk cannot go on */
  return 0; }
 if(s==5){ bushy();add("/D/T/S",1);r=walk_copy();
  if(r!=1||copies!=7||mkdirs!=2||strcmp(full,"/V/T")||strcmp(other_full,"/D/T"))return 1;   /* S exists: filled in, not recreated; Q and E made */
  if(find("/D/T/S/Q/H")<0||find("/D/T/E")<0||find("/D/T/Z")<0||alive()!=fs_n)return 2;
  if(strstr(log_,"M /D/T/S/Q\nC /V/T/S/Q/H > /D/T/S/Q/H\n")==NULL)return 3;   /* a directory is made before its files */
  return 0; }
 if(s==6){ bushy();fail_copy=4;r=walk_copy();if(r!=0||copies!=4||errors)return 1;
  fs_n=0;strcpy(full,"/V/T");strcpy(other_full,"/D/T");memset(fs_gone,0,sizeof fs_gone);bushy();fail_mkdir=1;copies=0;r=walk_copy();if(r!=0||errors!=1||strcmp(errname,"Mkdir"))return 2;
  fs_n=0;strcpy(full,"/V/T");strcpy(other_full,"/D/T");memset(fs_gone,0,sizeof fs_gone);bushy();fail_mkdir=0;errors=0;abort_after=3;copies=0;r=walk_copy();if(r!=0||copies>2)return 3;
  return 0; }
 if(s==7){ bushy();r=delete_tree();
  if(r!=1||alive()!=3||removes!=7||rmdirs!=4||a2fc_ops!=11||progress_done!=11||progress_total!=10||strcmp(full,"/V/T"))return 1;   /* /D and /D/T remain */
  if(find("/V/T")>=0||find("/V")<0)return 2;
  return 0; }
 if(s==8){ bushy();strcpy(fail_remove,"/V/T/S/Q/H");r=delete_tree();
  if(r!=0||errors!=1||strcmp(errname,"Delete")||find("/V/T/S/Q/H")<0||find("/V/T/S")<0||find("/V/T")<0)return 1;   /* stops at the fault; nothing above is removed */
  return 0; }
 if(s==9){ bushy();strcpy(unreadable,"/V/T/E");r=delete_tree();
  if(r!=0||dirfails!=1||removes||rmdirs||alive()!=fs_n)return 1;   /* the count refuses first: nothing erased */
  return 0; }
 if(s==10){ deep(29);add("/V/T/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/A/LONGNAME",0);
  r=walk_copy();if(r!=0xFFFF||toolongs!=1||copies!=1)return 1;   /* F copied, then a 71-character file path: refused, reported (the callers count first, and the count now refuses this tree) */
  fs_n=0;strcpy(full,"/V/T");strcpy(other_full,"/D/T");memset(fs_gone,0,sizeof fs_gone);toolongs=0;copies=0;deep(31);r=walk_copy();
  if(r!=0xFFFF||toolongs!=1||copies)return 2;   /* a directory beyond 64 characters: the tree is refused */
  return 0; }
 if(s==11){ /* D on a tree one of whose FILES has a path that does not fit, its
  * directory fitting. Measured before the fix (tree_walk.h counted files
  * without checking their path): delete_tree=0, removes=2, toolongs=1 --
  * FIRST and SECOND erased, then "Path too long", the tree half deleted. */
  add("/V",1);add("/V/T",1);add("/V/T/FIRST",0);add("/V/T/SECOND",0);
  add("/V/T/DEEPDIRECTORY01",1);add("/V/T/DEEPDIRECTORY01/DEEPDIRECTORY02",1);
  add("/V/T/DEEPDIRECTORY01/DEEPDIRECTORY02/DEEPDIRECTORY03",1);
  add("/V/T/DEEPDIRECTORY01/DEEPDIRECTORY02/DEEPDIRECTORY03/LASTFILE.TXT",0);
  r=delete_tree();
  if(r!=0||dirfails||toolongs!=1||removes||rmdirs||alive()!=fs_n)return 1;   /* refused by the count: nothing erased, "Path too long" said */
  if(find("/V/T/FIRST")<0||find("/V/T/SECOND")<0)return 2;
  return 0; }
 if(s==12){ /* Bug hunt 2 (tools/probe_tree_walk_dest.py): the count walked the
  * source paths only. Source /V/T, short; destination 50 characters deep.
  * Measured before the fix: count=3, then copy=65535 copies=2 toolongs=1 --
  * AFILE and BFILE copied, LONGFILENAME15 "Path too long", a partial copy. */
  strcpy(other_full,"/DESTINATION01/DESTINATION02/DESTINATION03/DESTXX/T");
  add("/V",1);add("/V/T",1);add("/V/T/AFILE",0);add("/V/T/BFILE",0);add("/V/T/LONGFILENAME15",0);
  add("/DESTINATION01",1);add("/DESTINATION01/DESTINATION02",1);add("/DESTINATION01/DESTINATION02/DESTINATION03",1);
  add("/DESTINATION01/DESTINATION02/DESTINATION03/DESTXX",1);add(other_full,1);
  r=walk_count();
  if(r!=0xFFFF||toolongs!=1||dirfails||copies)return 1;   /* refused before the first byte */
  /* (a refused walk leaves the paths where it stopped: every caller gives up) */
  if(strcmp(other_full,"/DESTINATION01/DESTINATION02/DESTINATION03/DESTXX/T"))return 2;
  /* the same tree into a shallow destination: counted, all three */
  fs_n=0;toolongs=0;strcpy(full,"/V/T");strcpy(other_full,"/D/T");
  add("/V",1);add("/V/T",1);add("/D",1);add("/D/T",1);add("/V/T/AFILE",0);add("/V/T/BFILE",0);add("/V/T/LONGFILENAME15",0);
  r=walk_count();if(r!=3||toolongs||strcmp(other_full,"/D/T"))return 3;
  return 0; }
 return 9;
}
'''


class TreeWalk(unittest.TestCase):
    def test_walks(self):
        with tempfile.TemporaryDirectory(prefix='tree-walk-') as d:
            p = Path(d)
            (p / 'test.c').write_text(HARNESS)
            subprocess.run(['cc', '-std=c99', '-fsanitize=address,undefined', '-I', str(ROOT), str(p / 'test.c'), '-o', str(p / 'test')], check=True, capture_output=True)
            for scenario in range(1, 13):
                self.assertEqual(subprocess.run([str(p / 'test'), str(scenario)]).returncode, 0, 'scenario %d' % scenario)

    def test_a_directory_is_not_moved_onto_its_own_ancestor(self):
        """V on the directory A of /V/A with /V in the other panel: the real
        copy_one, walk_tree and delete_tree. Measured before the fix
        (copy_one only refused a target INSIDE the source): "copy ok",
        C /V/A/A/A/G > /V/A/A/G -- into the source tree -- and after the
        move's delete_tree only /V, /V/A and /V/A/KEEP were left: G, whose
        only copy it was, gone. paths_nested is assembly in the program
        (src/a2fc_mli.s); its model here is checked against it, pair by
        pair, by tools/test_keep_tags.py."""
        sys.path.insert(0, str(ROOT / 'tools'))
        from test_file_safety import section
        h = HARNESS
        old = 'struct Entry { unsigned char bytes[29]; };'
        self.assertEqual(h.count(old), 1)
        h = h.replace(old,
                      'struct Entry { char name[17]; unsigned char type; unsigned int aux; unsigned char pad[8]; };\n'
                      'struct Panel { char path[65]; struct Entry e[2]; };\n'
                      'static struct Panel panels[2]; static unsigned char active;\n'
                      'static struct Panel* pan_at(unsigned char p){return &panels[p];}\n'
                      'static void message(const char* m){printf("MSG %s\\n",m);}\n'
                      'const char msg_intoself[]="into itself";\n')
        copy_one = section('/* Copies the entry into the other panel', 'static const char msg_treekept')
        self.assertIn('paths_nested()', copy_one)
        extra = r'''
static unsigned char is_dir(const struct Entry* e){return e->type==0x0F;}
static unsigned char build_full(char* out,const struct Panel* pan,const struct Entry* e){
 if(strlen(pan->path)+1+strlen(e->name)>=PATH_LEN)return 0;sprintf(out,"%s/%s",pan->path,e->name);return 1;}
static unsigned char paths_nested(void){
 size_t a=strlen(full),b=strlen(other_full),n=a<b?a:b;const char* l=a<b?other_full:full;
 return !strncmp(full,other_full,n)&&(l[n]==0||l[n]=='/');}
''' + copy_one
        h = h[:h.index('int main(')] + extra + r'''
int main(int argc,char** argv){
 unsigned i;
 pool=(struct Mini*)table;
 add("/V",1);add("/V/A",1);add("/V/A/A",1);add("/V/A/A/A",1);add("/V/A/A/A/G",0);add("/V/A/A/KEEP",0);add("/W",1);
 strcpy(panels[0].path,"/V/A");strcpy(panels[0].e[0].name,"A");panels[0].e[0].type=0x0F;
 strcpy(panels[1].path,argv[1]);active=0;
 if(!copy_one(&panels[0].e[0]))puts("copy refused");
 else {
  printf("copy ok\n%s",log_);
  build_full(full,&panels[0],&panels[0].e[0]);
  puts(delete_tree()?"source deleted":"delete failed");
 }
 for(i=0;i<fs_n;++i)if(!fs_gone[i])printf("left %s\n",fs_path[i]);
 return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='tree-walk-') as d:
            p = Path(d)
            (p / 't.c').write_text(h)
            subprocess.run(['cc', '-std=c99', '-fsanitize=address,undefined', '-I', str(ROOT), str(p / 't.c'), '-o', str(p / 't')],
                           check=True, capture_output=True)
            run = lambda other: subprocess.run([str(p / 't'), other], capture_output=True, text=True, check=True).stdout.splitlines()
            before = ['left ' + n for n in ('/V', '/V/A', '/V/A/A', '/V/A/A/A', '/V/A/A/A/G', '/V/A/A/KEEP', '/W')]
            # onto the grandparent, onto itself, into itself: refused, nothing written or erased
            for other in ('/V', '/V/A', '/V/A/A', '/V/A/A/A'):
                with self.subTest(other=other):
                    self.assertEqual(run(other), ['MSG into itself', 'copy refused'] + before)
            # elsewhere: copied whole, then the source goes
            out = run('/W')
            self.assertEqual(out[0], 'copy ok')
            self.assertIn('C /V/A/A/A/G > /W/A/A/G', out)
            self.assertIn('C /V/A/A/KEEP > /W/A/KEEP', out)
            self.assertIn('source deleted', out)
            self.assertEqual([l for l in out if l.startswith('left ')],
                             ['left ' + n for n in ('/V', '/V/A', '/W', '/W/A', '/W/A/A', '/W/A/A/G', '/W/A/KEEP')])


if __name__ == '__main__':
    unittest.main()
