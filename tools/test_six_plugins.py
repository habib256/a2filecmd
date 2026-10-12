"""Run actual overlay C routines against damaged images and failed writes."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_volinfo import fixture, entry, allocated, ptr
from prodos_read import Image
ROOT=Path(__file__).resolve().parents[1]
PREFIX='''#define __fastcall__
#define PLUGIN_HOST
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#undef memcpy
#undef memset
#undef strcpy
#undef sprintf
struct A2fcApi;
'''
UNDELETE=PREFIX+r'''
#include "src/plugins/undelete.c"
static FILE* diskfile;
static unsigned char mock(unsigned char cmd,void* p) {
    struct Block* b=p;if(cmd!=0x80)abort();
    if(fseek(diskfile,(long)b->block*512,SEEK_SET))return 0x27;
    return fread(b->buffer,1,512,diskfile)==512?0:0x27;
}
int main(int argc,char** argv) {
    unsigned char scratch[512];
    a.memcpy=memcpy;a.memset=memset;a.mli=mock;buf=scratch;
    diskfile=fopen(argv[1],"rb");fseek(diskfile,1024,SEEK_SET);fread(buf,1,512,diskfile);
    total=rd16(buf+41);bitmap=rd16(buf+39);memcpy(e,buf+43,39);
    printf("%u\n",valid());fclose(diskfile);return 0;
}
'''
MKIMAGE=PREFIX+r'''
#include "src/plugins/mkimage.c"
int main(int argc,char** argv) {
    unsigned char scratch[512];FILE* f=fopen(argv[1],"wb");
    a.memcpy=memcpy;a.memset=memset;a.strlen=strlen;buf=scratch;
    strcpy(name,"EMPTY");blocks=atoi(argv[2]);maps=(blocks+4095U)/4096;
    for(b=0;b<blocks;++b){makeblock();fwrite(buf,1,512,f);}fclose(f);return 0;
}
'''
SYNC=PREFIX+r'''
static int sync_ferror(FILE*);
#define ferror sync_ferror
#include "src/plugins/sync.c"
#undef ferror
static unsigned int mode, opens, closes;
static unsigned int renames, metadata_writes;
static unsigned int creates, removes;
static unsigned int io_target, io_counts[4];
static unsigned char tree;
static FILE* catalog;
static FILE *verify_source, *verify_target, *read_error;
static int sync_ferror(FILE* f) { return f == read_error || ferror(f); }
static FILE* sync_open(const char* p, const char* m) {
    FILE* f;
    if(tree && !strcmp(p,sdir)) {
        unsigned char data[512]={0},*e;unsigned int i;
        data[4]=0xE1;data[35]=39;data[36]=13;
        for(i=0;i<2;++i) {
            e=data+43+39*i;e[0]=0x24+i;memcpy(e+1,i?"DATA2":"DATA",4+i);
            if((mode==93 || mode==94) && !i)e[0]=0xD4;
            if(mode==34 && !i){e[0]=0x29;memcpy(e+1,"../VICTIM",9);}
            e[16]=6;e[19]=5;e[21]=0x40;e[22]=6;e[30]=0xE3;
            e[33]=33;e[34]=52;
            if(mode>=95 && mode<=102) {
                e[21]=size;e[22]=size>>8;
                e[33]=meta.mdate;e[34]=meta.mdate>>8;
            }
            if(mode==36)e[33]=1; /* month zero, date present */
            if(mode==37){e[33]=0xA1;e[34]=53;} /* month 13 */
            if(mode==38)e[33]=32; /* day zero */
            if(mode==39)e[36]=24; /* modification hour */
            if(mode==40)e[35]=60; /* modification minute */
            if(mode==41){e[24]=32;e[25]=52;} /* creation day zero */
            if(mode==42)e[27]=24; /* creation hour */
            if(mode==43){ /* Dec 31, 23:59; creation and modification */
                e[24]=e[33]=0x9F;e[25]=e[34]=53;
                e[26]=e[35]=59;e[27]=e[36]=23;
            }
        }
        catalog=tmpfile();if(!catalog)abort();
        fwrite(data,1,512,catalog);rewind(catalog);return catalog;
    }
    f = fopen(p,m);
    ++opens;
    if(opens==3)verify_source=f;if(opens==4)verify_target=f;
    return f;
}
static size_t sync_read(void* p,size_t z,size_t n,FILE* f) {
    if(mode>=64 && mode<=87) {
        unsigned int phase=opens==2?0:f==verify_source?2:3;
        unsigned int event=(mode-64)%6/2;
        ++io_counts[phase];
        if(phase==(mode-64)/6 && io_counts[phase]==io_target) {
            if(!event)cancelled=1;else read_error=f;
            if(event==2)return fread(p,z,n-1,f);
        }
    }
    if(n==1 && ((mode==6 && f==verify_source) || (mode==7 && f==verify_target))) {
        read_error=f;return 0;
    }
    {size_t got=fread(p,z,n,f);
    if(mode==35 && f==catalog)read_error=f;
    if((mode==92 || mode==94) && f==catalog)cancelled=1;
    return got;}
}
static int sync_close(FILE* f) {
    int r=fclose(f);
    if(f==catalog){catalog=NULL;read_error=NULL;return r;}
    ++closes;
    if(mode>=95 && mode<=100 && closes==4) {
        FILE* changed=fopen(target,"wb");if(!changed)abort();
        fputs("changed during copy",changed);fclose(changed);
    }
    if(mode>=54 && mode<=61 && closes==1+(mode-54)%4)cancelled=1;
    return ((mode>=8 && mode<=11 && closes==mode-7) || (mode==16 && closes==2)) ? EOF : r;
}
static int sync_remove(const char* p) {
    ++removes;
    if(mode==13 && strstr(p,"A2FC.BAK"))return -1;
    if(mode>=15 && mode<=17 && strstr(p,"A2FC.SYNC"))return -1;
    if(((mode>=58 && mode<=61) || mode==63) && strstr(p,"A2FC.SYNC"))return -1;
    if(mode>=64 && mode<=87 && (mode-64)%2 && strstr(p,"A2FC.SYNC"))return -1;
    return remove(p);
}
static char oldpath[80],newpath[80];
static unsigned char mock(unsigned char cmd,void* p) {
    FILE* f;unsigned char* pp;
    if(cmd==0xC0){++creates;pp=((struct Create*)p)->path;memcpy(oldpath,pp+1,pp[0]);oldpath[pp[0]]=0;
        f=fopen(oldpath,"wx");if(!f)return 0x47;fclose(f);return 0;}
    if(cmd==0xC4){pp=((struct Info*)p)->path;memcpy(oldpath,pp+1,pp[0]);oldpath[pp[0]]=0;
        if(mode==89 && !strcmp(oldpath,bak))cancelled=1;
        struct Info* ip=p;ip->access=0xE3;ip->storage=2;ip->mdate=ip->mtime=0;
        if(!strcmp(oldpath,target)) {
            if(mode>=95 && mode<=102 && closes>=4) {
                ip->mdate=meta.mdate;
                if(mode==96)ip->mtime=1;
                if(mode==97)++ip->mdate;
                if(mode==98)ip->mdate+=512;
                if(mode==99)ip->mdate=33;             /* 1999 -> 2000 */
                if(mode==100)ip->mdate=(39<<9)|33;   /* 1940 -> 2039 */
                if(mode==101)ip->mdate=(99<<9)|33;   /* 2000 > 1999 */
                if(mode==102)ip->mdate=(40<<9)|33;   /* 2039 > 1940 */
            }
            if(mode==91 || mode==93)cancelled=1;
            if((mode==62 || mode==63) && closes>=4)cancelled=1;
            if(mode==19 || (mode==20 && closes>=4))ip->access=0xC1;
            if(mode==21 && closes>=4)return 0x27;
            if(mode==22 && closes>=4)ip->storage=5;
            if(mode==23 && closes>=4)ip->access=0x83;
            if((mode>=44 && mode<=48) || (mode>=49 && mode<=53 && closes>=4)) {
                unsigned int bad=mode<=48 ? mode-44:mode-49;
                if(bad==0)ip->mdate=0x3201; /* month zero */
                if(bad==1)ip->mdate=0x33A1; /* month 13 */
                if(bad==2)ip->mdate=0x3220; /* day zero */
                if(bad==3)ip->mtime=0x1800; /* hour 24 */
                if(bad==4)ip->mtime=60; /* minute 60 */
            }
        }
        if(tree) {
            if(!strcmp(oldpath,sdir)){ip->storage=13;ip->blocks=1;return 0;}
        }
        f=fopen(oldpath,"rb");if(!f)return 0x46;fclose(f);return 0;}
    if(cmd==0xC2){++renames;pp=((struct Rename*)p)->old;memcpy(oldpath,pp+1,pp[0]);oldpath[pp[0]]=0;
        pp=((struct Rename*)p)->newpath;memcpy(newpath,pp+1,pp[0]);newpath[pp[0]]=0;
        if((mode==2 || mode==12) && strstr(oldpath,"A2FC.SYNC"))return 0x27;
        if(mode==12 && strstr(oldpath,"A2FC.BAK"))return 0x27;
        if(mode==14 && strstr(newpath,"A2FC.BAK"))return 0x27;
        if(mode==18 && strstr(oldpath,"A2FC.SYNC")) {
            f=fopen(newpath,"wx");if(!f)abort();fputs("late arrival",f);fclose(f);
        }
        /* ProDOS RENAME never replaces an existing destination. */
        f=fopen(newpath,"rb");if(f){fclose(f);return 0x47;}
        return rename(oldpath,newpath)?0x27:0;}
    if(cmd==0xC3){++metadata_writes;return mode==4?0x27:0;}
    abort();
}
static size_t write_fail(const void* p,size_t s,size_t n,FILE* f) {
    size_t written;
    if(mode>=64 && mode<=87) {
        unsigned int event=(mode-64)%6/2;
        ++io_counts[1];
        if((mode-64)/6==1 && io_counts[1]==io_target) {
            if(!event)cancelled=1;else read_error=f;
            if(event==2)return fwrite(p,s,n-1,f);
        }
    }
    if(mode==1 || mode==15)return 0;
    written=fwrite(p,s,n,f);
    if(mode==5 && ftell(f)==1600)fputc('X',f);
    return written;
}
static void clear_screen(void) {}
static int print_screen(const char* s,...) {return 0;}
static unsigned char confirm_sync(const char* s) {return 1;}
static void show_source(const char* s) {if(mode==17 || mode==90)cancelled=1;}
static void sync_bar(const char* s,unsigned long d,unsigned long t) {fprintf(stderr,"BAR %s %lu %lu\n",s,d,t);}
int main(int argc,char** argv) {
    unsigned char scratch[512], result;char msg[80]={0};
    static struct Panel panels[2];static unsigned char active;
    struct A2fcApi api;
    a.strlen=strlen;a.strcpy=strcpy;a.memcpy=memcpy;a.memset=memset;a.mli=mock;
    a.fopen=sync_open;a.fclose=sync_close;a.fread=sync_read;a.fwrite=write_fail;a.remove=sync_remove;
    a.note=msg;buf=scratch;a.progress_bar=sync_bar;strcpy(name,"DATA");
    strcpy(sdir,argv[1]);strcpy(ddir,argv[2]);join(source,sdir,"DATA");join(target,ddir,"DATA");
    if(!newer((30<<9)|33,0,(26<<9)|33,0) || newer((99<<9)|33,0,(0<<9)|33,0) ||
       !newer((26<<9)|33,0x0D00,(26<<9)|33,0x0C00))abort();
    mode=atoi(argv[3]);cancelled=mode==3 || mode==17 || mode==88;size=strtoul(argv[4],0,10);meta.type=6;meta.aux=0;meta.access=0xE3;
    meta.mdate=(26<<9)|33;meta.mtime=0;
    if(mode==99)meta.mdate=(99<<9)|33;
    if(mode==100)meta.mdate=(40<<9)|33;
    if(mode==101)meta.mdate=33;
    if(mode==102)meta.mdate=(39<<9)|33;
    if(mode>=1000){io_target=(mode-1000)/24;mode=64+(mode-1000)%24;}
    if(argc>5) {
        tree=1;strcpy(panels[0].path,sdir);strcpy(panels[1].path,ddir);
        a.panels=panels;a.active=&active;a.copy_buf=scratch;
        a.strcmp=strcmp;a.sprintf=sprintf;a.fseek=fseek;a.clrscr=clear_screen;
        a.cprintf=print_screen;a.confirm=confirm_sync;a.message=show_source;
        api=a;recovery=1; /* a fresh invocation must clear stale recovery state */
        plugin_entry(&api);result=copied;
    } else result=copy_file(1);
    fprintf(stderr,"STATE %u %u %u %u\n",renames,metadata_writes,opens,closes);
    fprintf(stderr,"IO %u %u %u %u\n",io_counts[0],io_counts[1],io_counts[2],io_counts[3]);
    fprintf(stderr,"OWNED %u %u\n",creates,removes);
    printf("%u\n%u\n%s\n",result,recovery,msg);return 0;
}
'''

RESCUE=PREFIX+r'''
#include "src/plugins/rescue.c"
static unsigned int attempts,failures;
static unsigned char mock(unsigned char cmd,void* p) {
    struct Block* b=p;if(cmd!=0x80)abort();++attempts;
    if(attempts<=failures)return 0x27;
    memset(b->buffer,0x5A,512);return 0;
}
static unsigned int bars;
static void rbar(const char* s,unsigned long d,unsigned long t){(void)s;(void)d;(void)t;++bars;}
int main(int argc,char** argv) {
    unsigned char scratch[512],r;
    buf=scratch;a.mli=mock;a.memset=memset;disk=1;unit=0x60;a.progress_bar=rbar;
    memset(buf,0xA5,512);failures=atoi(argv[1]);cancelled=argc>2;
    r=read_chunk(27,2);
    printf("%u %u %u %u %u\n",r,attempts,retried,buf[0],buf[27]);fprintf(stderr,"%u\n",bars);return 0;
}
'''

RESCUE_FILE=PREFIX+r'''
static void mock_clearerr(FILE*);
#define clearerr mock_clearerr
#include "src/plugins/rescue.c"
#undef clearerr
static unsigned int attempts,failures;
static unsigned char errflag;   /* cc65's _FERROR: fread refuses a flagged stream */
static void mock_clearerr(FILE* f){(void)f;errflag=0;}
static FILE* mock_open(const char* p,const char* m){return fopen(p,m);}
static size_t mock_read(void* p,size_t s,size_t n,FILE* f){
    if(errflag)return 0;
    if(++attempts<=failures){errflag=1;return 0;}
    return fread(p,s,n,f);
}
static int listed;static struct DirEntry dirent;
static unsigned char dopen(const char* p){printf("dir %s\n",p);listed=0;return 1;}
static unsigned char dnext(void){
    static const char* names[]={"OTHER","DATA"};static const unsigned long sizes[]={5,1234};
    if(listed==2)return 0;
    strcpy(dirent.name,names[listed]);dirent.size=sizes[listed];++listed;return 1;
}
static void dclose(void){}
static void rbar(const char* s,unsigned long d,unsigned long t){(void)s;(void)d;(void)t;}
int main(int argc,char** argv) {
    unsigned char scratch[512],r;
    buf=scratch;a.progress_bar=rbar;a.fopen=mock_open;a.fread=mock_read;a.fseek=fseek;a.fclose=fclose;a.memset=memset;
    a.strlen=strlen;a.strcmp=strcmp;a.dir_open=dopen;a.dir_next=dnext;a.dir_close=dclose;a.dir_entry=&dirent;
    if(!strcmp(argv[1],"size")){
        strcpy(source,argv[2]);size=99;r=fresh_size();printf("%u %lu %s\n",r,size,source);return 0;
    }
    disk=0;in=0;strcpy(source,argv[1]);failures=atoi(argv[2]);offset=520;memset(buf,0xA5,512);
    r=read_chunk(100,1);
    printf("%u %u %u %u %u\n",r,attempts,retried,buf[0],buf[99]);return 0;
}
'''

UNDELETE_ROOT=PREFIX+r'''
static int undelete_error(FILE*);
#define ferror undelete_error
#include "src/plugins/undelete.c"
static FILE* diskfile;static const char* dirfile;static char keypress;static unsigned int used;
static const char* table="";     /* argv[6]: "twin", "phantom", "" */
static FILE* directory_file;static unsigned int directory_closes,fail_close;
static unsigned char cancel_write,cancel_bar,cancel_close;
static unsigned int write_calls,fail_write,read_calls,fail_read;
static unsigned char keep_partial,show_creates;
static unsigned int creates,index_reads,bitmap_reads;
static unsigned int recovery_reads,cancel_data_read,error_data_read;
static unsigned int validation_bitmaps,validation_indexes,cancel_bitmap,cancel_index;
static FILE *recovery_output,*recovery_verify;
static unsigned int corrupt_write,verify_reads,verify_probes,verify_closes;
static unsigned int verify_error_at,verify_short_at,verify_cancel_at;
static unsigned char append_output,verify_eof_error,verify_close_error,verify_cancel_close;
static unsigned char verify_open_error;
static unsigned int verify_source_reads,verify_source_error,verify_source_cancel;
static unsigned char layout_fault;
static FILE* undelete_errored;
static int undelete_error(FILE* f){return f==undelete_errored;}
static size_t read_directory(void* p,size_t s,size_t n,FILE* f){
    if(f==recovery_verify) {
        if((unsigned long)ftell(f)<size) {
            ++verify_reads;
            if(verify_reads==verify_error_at)undelete_errored=f;
            if(verify_reads==verify_cancel_at)cancelled=1;
            if(verify_reads==verify_short_at)return fread(p,s,n-1,f);
        } else {
            ++verify_probes;
            if(verify_eof_error){undelete_errored=f;return 0;}
        }
    }
    size_t got=fread(p,s,n,f);
    if(f==directory_file && ++read_calls==fail_read)undelete_errored=f;
    return got;
}
static int remove_recovery(const char* p){return keep_partial ? -1:remove(p);}
static unsigned char mli(unsigned char cmd,void* p) {
    if(cmd==0x80) {
        struct Block* b=p;
        if(layout_fault && b->block==(layout_fault<=2 ? 20:6)) {
            unsigned int at=layout_fault<=2 ? ++index_reads:++bitmap_reads;
            unsigned char phase=(layout_fault-1)&1;
            if(at==1+phase || at==3+phase)return 0x27;
        }
        if(fseek(diskfile,(long)b->block*512,SEEK_SET))return 0x27;
        if(fread(b->buffer,1,512,diskfile)!=512)return 0x27;
        if(writing==2 && b->buffer==buf) {
            ++verify_source_reads;
            if(verify_source_reads==verify_source_cancel)cancelled=1;
            if(verify_source_reads==verify_source_error)return 0x27;
        }
        if(!writing && b->block==6 && ++validation_bitmaps==cancel_bitmap)cancelled=1;
        if(!writing && b->block==20 && b->buffer==idx && ++validation_indexes==cancel_index)cancelled=1;
        if(writing && b->buffer==buf) {
            ++recovery_reads;
            if(recovery_reads==cancel_data_read)cancelled=1;
            if(recovery_reads==error_data_read)return 0x27;
        }
        return 0;
    }
    if(cmd==0xC4) {                 /* the source volume: every block in use, as ProDOS says */
        struct Info* i=p;
        if(i->path[0]!=2 || memcmp(i->path+1,"/V",2))abort();
        i->storage=15;i->blocks=used;return 0;
    }
    if(cmd==0xC5) {
        struct Online* o=p;memset(o->buffer,0,256);
        o->buffer[0]=0x61;o->buffer[1]='V';o->buffer[16]=0x73;memcpy(o->buffer+17,"tmp",3);
        /* twin: a second drive named V; phantom: V only past the zero
         * terminator, in what a former ON_LINE left in copy_buf */
        if(!strcmp(table,"twin")){o->buffer[32]=0xE1;o->buffer[33]='V';}
        if(!strcmp(table,"phantom")){o->buffer[0]=0x73;memcpy(o->buffer+1,"tmp",3);o->buffer[16]=0;
            o->buffer[32]=0x61;o->buffer[33]='V';}
        return 0;
    }
    if(cmd==0xC0) {
        ++creates;
        struct Create* c=p;char path[81];FILE* f;
        memcpy(path,c->path+1,c->path[0]);path[c->path[0]]=0;
        f=fopen(path,"wx");if(!f)return 0x47;fclose(f);return 0;
    }
    abort();                        /* nothing may write to the source */
}
/* The volume directory read as a file: its linked blocks, end to end. */
static FILE* open_file(const char* path,const char* mode){
    if(verify_open_error && strcmp(path,"/V") && !strcmp(mode,"rb"))return NULL;
    FILE* f=fopen(strcmp(path,"/V")?path:dirfile,mode);
    if(strcmp(path,"/V")) {
        if(!strcmp(mode,"wb"))recovery_output=f;
        else if(!strcmp(mode,"rb"))recovery_verify=f;
    }
    if(!strcmp(path,"/V"))directory_file=f;return f;
}
static int close_file(FILE* f){
    unsigned char directory=f==directory_file,verify=f==recovery_verify;
    if(f==recovery_output && append_output)fputc('!',f);
    int result=fclose(f);
    if(f==recovery_output)recovery_output=0;
    if(verify){++verify_closes;recovery_verify=0;if(verify_cancel_close)cancelled=1;if(verify_close_error)result=EOF;}
    if(f==undelete_errored)undelete_errored=0;
    if(directory){directory_file=0;if(++directory_closes==fail_close)return EOF;}
    else if(cancel_close)cancelled=1;
    return result;
}
static size_t write_file(const void* p,size_t size,size_t count,FILE* f){
    size_t result;
    if(write_calls+1==corrupt_write) {
        unsigned char changed[512];memcpy(changed,p,count);changed[0]^=1;
        result=fwrite(changed,size,count,f);
    } else result=fwrite(p,size,count,f);
    if(++write_calls==fail_write)undelete_errored=f;
    if(cancel_write)cancelled=1;return result;
}
static void recovery_bar(const char* s,unsigned long done,unsigned long all){
    (void)s;(void)done;(void)all;if(cancel_bar)cancelled=1;
}
static char getkey(void){return keypress;}
static unsigned char yes(const char* s){(void)s;return 1;}
static void quiet(const char* s){(void)s;}
static void nothing(void){}
static int noprint(const char* f,...){(void)f;return 0;}
int main(int argc,char** argv) {
    static struct A2fcApi api;static struct Panel panels[2];static struct Entry selected;
    static unsigned char active,scratch[512];static char note[80];
    diskfile=fopen(argv[1],"rb");dirfile=argv[2];used=atoi(argv[3]);keypress=argv[4][0];
    strcpy(panels[0].path,"/V");strcpy(panels[1].path,argv[5]);
    if(argc>6)table=argv[6];
    /* argv[7] "list": the volume-list row /V, unit $60, instead of a path */
    for(int i=7;i<argc;++i){
        if(!strcmp(argv[i],"list")){panels[0].path[0]=0;strcpy(selected.name,"/V");selected.mdate=6;}
        else if(!strncmp(argv[i],"close=",6))fail_close=atoi(argv[i]+6);
        else if(!strncmp(argv[i],"write=",6))fail_write=atoi(argv[i]+6);
        else if(!strncmp(argv[i],"read=",5))fail_read=atoi(argv[i]+5);
        else if(!strcmp(argv[i],"keep-partial"))keep_partial=1;
        else if(!strcmp(argv[i],"create-count"))show_creates=1;
        else if(!strncmp(argv[i],"layout-fault=",13))layout_fault=atoi(argv[i]+13);
        else if(!strcmp(argv[i],"cancel-write"))cancel_write=1;
        else if(!strcmp(argv[i],"cancel-bar"))cancel_bar=1;
        else if(!strcmp(argv[i],"cancel-close"))cancel_close=1;
        else if(!strncmp(argv[i],"cancel-data-read=",17))cancel_data_read=atoi(argv[i]+17);
        else if(!strncmp(argv[i],"data-read-error=",16))error_data_read=atoi(argv[i]+16);
        else if(!strncmp(argv[i],"cancel-bitmap=",14))cancel_bitmap=atoi(argv[i]+14);
        else if(!strncmp(argv[i],"cancel-index=",13))cancel_index=atoi(argv[i]+13);
        else if(!strncmp(argv[i],"corrupt-write=",14))corrupt_write=atoi(argv[i]+14);
        else if(!strcmp(argv[i],"append-output"))append_output=1;
        else if(!strncmp(argv[i],"verify-read-error=",18))verify_error_at=atoi(argv[i]+18);
        else if(!strncmp(argv[i],"verify-short=",13))verify_short_at=atoi(argv[i]+13);
        else if(!strncmp(argv[i],"verify-cancel-read=",19))verify_cancel_at=atoi(argv[i]+19);
        else if(!strcmp(argv[i],"verify-eof-error"))verify_eof_error=1;
        else if(!strcmp(argv[i],"verify-close-error"))verify_close_error=1;
        else if(!strcmp(argv[i],"verify-cancel-close"))verify_cancel_close=1;
        else if(!strcmp(argv[i],"verify-open-error"))verify_open_error=1;
        else if(!strncmp(argv[i],"verify-source-error=",20))verify_source_error=atoi(argv[i]+20);
        else if(!strncmp(argv[i],"verify-source-cancel=",21))verify_source_cancel=atoi(argv[i]+21);
    }
    api.panels=panels;api.active=&active;api.selected=&selected;api.note=note;api.copy_buf=scratch;
    api.mli=mli;api.fopen=open_file;api.fread=read_directory;api.fwrite=write_file;api.fseek=fseek;api.fclose=close_file;
    api.progress_bar=recovery_bar;
    api.remove=remove_recovery;api.memcpy=memcpy;api.memset=memset;api.strcpy=strcpy;api.strlen=strlen;
    api.sprintf=sprintf;api.cgetc=getkey;api.confirm=yes;api.message=quiet;api.cputs=quiet;
    api.cprintf=noprint;api.clrscr=nothing;
    plugin_entry(&api);puts(note);fclose(diskfile);
    fprintf(stderr,"RECOVERY %u %u\n",recovery_reads,write_calls);
    fprintf(stderr,"CREATED %u\n",creates);
    fprintf(stderr,"VERIFY %u %u %u\n",verify_reads,verify_probes,verify_closes);
    if(show_creates)printf("%u\n",creates);
    if(cancel_bar && write_calls!=7)return 31;
    if(cancel_write && write_calls!=1)return 32;
    return 0;
}
'''

UNIT_OF=PREFIX+r'''
#define UTIL_VOLUME
#define UTIL_TWIN
#include "src/plugins/util.h"
static unsigned char table[512];
static unsigned char mli(unsigned char cmd,void* p) {
    struct Online* o=p;
    if(cmd!=0xC5 || o->n!=2 || o->unit)abort();
    memcpy(o->buffer,table,256);     /* ON_LINE writes 256 bytes; the rest is stale */
    return 0;
}
int main(int argc,char** argv) {
    static unsigned char scratch[512];static char note[80];unsigned int i;
    for(i=0;i<512;++i){unsigned int x;sscanf(argv[1]+2*i,"%2x",&x);table[i]=x;}
    memcpy(scratch,table,512);       /* copy_buf as a former ON_LINE left it */
    a.mli=mli;a.note=note;a.sprintf=sprintf;buf=scratch;
    i=unit_of(argv[2],(unsigned char)strtoul(argv[3],0,16));
    printf("%02X\n%s\n",i,note);return 0;
}
'''

RESCUE_ENTRY=PREFIX+r'''
#include "src/plugins/rescue.c"
static unsigned char twin;
static unsigned char mli(unsigned char cmd,void* p) {
    struct Online* o=p;
    if(cmd!=0xC5)abort();            /* no block is read, nothing is created */
    memset(o->buffer,0,256);
    o->buffer[0]=0x61;o->buffer[1]='V';o->buffer[16]=0x71;o->buffer[17]='D';
    if(twin){o->buffer[32]=0xE1;o->buffer[33]='V';}
    return 0;
}
static char key(void){return 'V';}
static void quiet(const char* s){(void)s;}
int main(int argc,char** argv) {
    static struct A2fcApi api;static struct Panel panels[2];static struct Entry selected;
    static unsigned char active,scratch[512];static char note[80],full[80];
    twin=argc>1;
    strcpy(panels[0].path,"/V/SUB");strcpy(panels[1].path,"/D");
    api.panels=panels;api.active=&active;api.selected=&selected;api.note=note;api.copy_buf=scratch;
    api.full=full;api.mli=mli;api.memcpy=memcpy;api.strcpy=strcpy;api.strlen=strlen;api.sprintf=sprintf;
    api.message=quiet;api.cgetc=key;
    plugin_entry(&api);puts(note);return 0;
}
'''

def online(*records, stale=()):
    """An ON_LINE table: (byte 0, name) records from offset 0, then a zero
    terminator, then `stale` records after it (copy_buf left by an older
    call), the whole 512 bytes of copy_buf as hex."""
    t=bytearray(512)
    for i,(b,name) in enumerate(records):
        t[16*i]=b;t[16*i+1:16*i+1+len(name)]=name
    for i,(b,name) in enumerate(stale,len(records)+1):
        t[16*i]=b;t[16*i+1:16*i+1+len(name)]=name
    return t.hex()


def root_volume(deleted=(), total=280):
    """/V with a FOUR-block root (2-5), its bitmap at 6, one live file whose
    block 10 makes the volume's used count larger than the root, and
    deleted entries given as (block, slot, name, key, blocks, eof, data)."""
    d=bytearray(total*512);chain=[2,3,4,5]
    for i,b in enumerate(chain):
        d[b*512:b*512+2]=(chain[i-1] if i else 0).to_bytes(2,'little')
        d[b*512+2:b*512+4]=(chain[i+1] if i+1<len(chain) else 0).to_bytes(2,'little')
    h=1028;d[h]=0xF1;d[h+1]=ord('V');d[h+0x1F]=39;d[h+0x20]=13
    d[h+0x21:h+0x23]=(1).to_bytes(2,'little');d[h+0x23:h+0x25]=(6).to_bytes(2,'little')
    d[h+0x25:h+0x27]=total.to_bytes(2,'little')
    live=h+39;d[live]=0x14;d[live+1:live+5]=b'LIVE';d[live+16]=4
    d[live+17:live+19]=(10).to_bytes(2,'little');d[live+19:live+21]=(1).to_bytes(2,'little');d[live+21]=3
    d[10*512:10*512+3]=b'abc'
    for b in range(total):d[6*512+(b>>3)]|=0x80>>(b&7)
    used=[0,1,2,3,4,5,6,10]
    for b in used:d[6*512+(b>>3)]&=~(0x80>>(b&7))
    for block,slot,name,key,blocks,eof,data in deleted:
        e=block*512+4+39*slot;d[e]=len(name);d[e+1:e+1+len(name)]=name;d[e+16]=4
        d[e+17:e+19]=key.to_bytes(2,'little');d[e+19:e+21]=blocks.to_bytes(2,'little')
        d[e+21:e+24]=eof.to_bytes(3,'little');d[key*512:key*512+len(data)]=data
    return bytes(d),len(used),b''.join(d[b*512:(b+1)*512] for b in chain)

class SixPlugins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='six-',dir='/tmp');cls.root=Path(cls.temp.name)
        cls.exe={}
        for name,text in [('undelete',UNDELETE),('mkimage',MKIMAGE),('sync',SYNC),('rescue',RESCUE),
                          ('rescue_file',RESCUE_FILE),('undelete_root',UNDELETE_ROOT),
                          ('unit_of',UNIT_OF),('rescue_entry',RESCUE_ENTRY)]:
            source=cls.root/(name+'.c');source.write_text(text);exe=cls.root/name
            subprocess.run(['cc','-std=c11','-Wno-unknown-pragmas','-I',str(ROOT),str(source),'-o',str(exe)],check=True)
            cls.exe[name]=exe
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def candidate(self,d):
        path=self.root/'candidate.po';path.write_bytes(d)
        result=subprocess.check_output([str(self.exe['undelete']),str(path)],timeout=10).strip()==b'1'
        self.assertEqual(path.read_bytes(),d);return result
    def test_undelete_seedling(self):self.assertTrue(self.candidate(fixture(entries=[entry()])))
    def test_undelete_reused(self):
        d=fixture(entries=[entry()]);allocated(d,4);self.assertFalse(self.candidate(d))
    def test_undelete_sapling(self):
        d=fixture(entries=[entry(2,4,3,1024)]);ptr(d,4,0,5);ptr(d,4,1,6)
        self.assertTrue(self.candidate(d))
    def test_undelete_swapped_index_after_destroy(self):
        d=fixture(entries=[entry(2,4,3,1024)]);ptr(d,4,0,5);ptr(d,4,1,6)
        d[2048:2560]=d[2304:2560]+d[2048:2304]
        self.assertTrue(self.candidate(d))
    def test_undelete_destroy_partial_bitmap_is_refused(self):
        d=fixture(entries=[entry(2,4,3,1024)]);ptr(d,4,0,5);ptr(d,4,1,6)
        d[2048:2560]=d[2304:2560]+d[2048:2304]
        allocated(d,6)
        self.assertFalse(self.candidate(d))
    def test_undelete_destroy_mixed_index_order_is_refused(self):
        d=fixture(1000,[entry(3,4,5,131073)])
        ptr(d,4,0,5);ptr(d,4,1,7);ptr(d,5,0,6);ptr(d,7,0,8)
        # DESTROY stopped between child indexes: only the first is swapped.
        d[2560:3072]=d[2816:3072]+d[2560:2816]
        self.assertFalse(self.candidate(d))
    def test_undelete_ambiguous_index_order_is_refused(self):
        d=fixture(4000,[entry(2,4,2,513)]);ptr(d,4,0,5)
        # Both block 5 and byte-swapped block 1280 are free and plausible.
        self.assertFalse(self.candidate(d))
    def test_undelete_duplicate(self):
        d=fixture(entries=[entry(2,4,3,1024)]);ptr(d,4,0,5);ptr(d,4,1,5)
        self.assertFalse(self.candidate(d))
    def test_undelete_outside_volume(self):self.assertFalse(self.candidate(fixture(entries=[entry(key=280)])))
    def test_undelete_wrong_count(self):self.assertFalse(self.candidate(fixture(entries=[entry(blocks=2)])))
    def test_undelete_xl_last_block(self):self.assertTrue(self.candidate(fixture(65535,[entry(key=65534)])))
    def test_undelete_tree_sparse(self):
        d=fixture(1000,[entry(3,4,3,131073)]);ptr(d,4,0,5);ptr(d,5,0,6)
        self.assertTrue(self.candidate(d))
    def rescue(self,failures,cancel=False):
        args=[str(self.exe['rescue']),str(failures)]
        if cancel:args.append('cancel')
        return [int(x) for x in subprocess.check_output(args).split()]
    def test_rescue_first_read(self):self.assertEqual(self.rescue(0),[1,1,0,90,90])
    def test_rescue_retry_success(self):self.assertEqual(self.rescue(29),[1,30,1,90,90])
    def test_rescue_retries_keep_the_screen_alive(self):
        # 30 slow retries of a bad block: each one after the first ticks the
        # resident's activity cell through the bar.
        run=subprocess.run([str(self.exe['rescue']),'29'],capture_output=True,check=True)
        self.assertEqual(run.stderr.split(),[b'29'])
    def test_rescue_zero_fill_after_30_failures(self):self.assertEqual(self.rescue(30),[0,30,1,0,165])
    def test_rescue_cancel_does_not_read(self):self.assertEqual(self.rescue(30,True),[0,0,0,165,165])
    def rescue_file(self,failures):
        path=self.root/'rescue.bin';path.write_bytes(bytes(range(256))*4)
        return [int(x) for x in subprocess.check_output([str(self.exe['rescue_file']),str(path),str(failures)]).split()]
    def test_rescue_file_retries_really_reread_after_a_failed_read(self):
        """cc65's fread refuses a stream with its error flag set, and fseek
        clears only EOF: every retry after the first failure must still
        reach the file, and a readable chunk must not be zero-filled."""
        self.assertEqual(self.rescue_file(0),[1,1,0,8,107])
        self.assertEqual(self.rescue_file(1),[1,2,1,8,107])
        self.assertEqual(self.rescue_file(29),[1,30,1,8,107])
        self.assertEqual(self.rescue_file(30),[0,30,1,0,0])
    def test_rescue_file_size_comes_from_the_directory_entry_now(self):
        out=subprocess.check_output([str(self.exe['rescue_file']),'size','/V/D/DATA'],text=True).split('\n')
        self.assertEqual(out[0],'dir /V/D');self.assertEqual(out[1],'1 1234 /V/D/DATA')
        out=subprocess.check_output([str(self.exe['rescue_file']),'size','/V/D/NONE'],text=True).split('\n')
        self.assertEqual(out[1],'0 99 /V/D/NONE')
    def undelete_root(self,deleted,key,*mode):
        image,used,directory=root_volume(deleted)
        if 'zero-name-length' in mode:
            image=bytearray(image)
            for block,slot,*_ in deleted:image[block*512+4+39*slot]=0
            directory=b''.join(image[b*512:(b+1)*512] for b in (2,3,4,5))
        img=self.root/'root.po';img.write_bytes(image);dirs=self.root/'root.dir';dirs.write_bytes(directory)
        out=self.root/'recovered';shutil.rmtree(out,ignore_errors=True);out.mkdir()
        if 'nested-output' in mode:
            (out/'A').mkdir();(out/'A'/'KEEP').write_bytes(b'preserve nested bytes')
        if 'keep-file' in mode:(out/'KEEP').write_bytes(b'preserve existing bytes')
        if 'existing-data' in mode:(out/'DATA').write_bytes(b'preserve existing DATA')
        run=subprocess.run([str(self.exe['undelete_root']),str(img),str(dirs),str(used),key,str(out)]+list(mode),
                           text=True,capture_output=True,check=True,timeout=20)
        note=run.stdout.strip()
        self.recovery_io=list(map(int,next(l.split()[1:] for l in run.stderr.splitlines() if l.startswith('RECOVERY '))))
        self.recovery_creates=int(next(l.split()[1] for l in run.stderr.splitlines() if l.startswith('CREATED ')))
        self.recovery_verification=list(map(int,next(l.split()[1:] for l in run.stderr.splitlines() if l.startswith('VERIFY '))))
        self.assertEqual(img.read_bytes(),image,'the source volume was written')
        self.assertEqual(dirs.read_bytes(),directory,'the source directory was written')
        return note,out
    def test_undelete_cancel_during_data_read_prevents_its_output_write(self):
        for size in (1,513,4097):
            payload=bytes(i%251 for i in range(size))
            blocks=(size+511)//512
            index=bytearray(512)
            for i in range(blocks):index[i]=21+i
            body=payload if blocks==1 else index+payload
            deleted=[(3,4,b'DATA',20,1 if blocks==1 else blocks+1,size,body)]
            for at in sorted({1,(blocks+1)//2,blocks}):
                for event in ('cancel','error','both'):
                    for keep in (False,True):
                        with self.subTest(size=size,at=at,event=event,keep=keep):
                            modes=['','keep-file']
                            if event!='error':modes.append(f'cancel-data-read={at}')
                            if event!='cancel':modes.append(f'data-read-error={at}')
                            if keep:modes.append('keep-partial')
                            note,out=self.undelete_root(deleted,'r',*modes)
                            self.assertEqual(self.recovery_io,[at,at-1])
                            expected={'KEEP':b'preserve existing bytes'}
                            if keep:expected['DATA']=payload[:512*(at-1)]
                            self.assertEqual({p.name:p.read_bytes() for p in out.iterdir()},expected)
                            self.assertNotIn('Recovered',note)
                            if keep:self.assertIn('Cleanup failed',note)

    def test_undelete_cancel_during_final_validation_prevents_create(self):
        for size in (0,1,513,4097):
            payload=bytes(i%251 for i in range(size))
            blocks=(size+511)//512
            index=bytearray(512)
            for i in range(blocks):index[i]=21+i
            body=payload if blocks<=1 else index+payload
            deleted=[(3,4,b'DATA',20,1 if blocks<=1 else blocks+1,size,body)]
            events=['cancel-bitmap=2'] if blocks<=1 else ['cancel-bitmap=4','cancel-index=4']
            for event in events:
                for keep in (False,True):
                    for collision in (False,True):
                        with self.subTest(size=size,event=event,keep=keep,collision=collision):
                            modes=['','keep-file',event]
                            if keep:modes.append('keep-partial')
                            if collision:modes.append('existing-data')
                            note,out=self.undelete_root(deleted,'r',*modes)
                            self.assertEqual(self.recovery_creates,0)
                            self.assertEqual(self.recovery_io,[0,0])
                            expected={'KEEP':b'preserve existing bytes'}
                            if collision:expected['DATA']=b'preserve existing DATA'
                            self.assertEqual({p.name:p.read_bytes() for p in out.iterdir()},expected)
                            self.assertIn('Cancelled',note)

    def test_undelete_verifies_closed_output_bytes_eof_and_io_before_success(self):
        for size in (0,1,513,4097):
            payload=bytes(i%251 for i in range(size))
            blocks=(size+511)//512
            index=bytearray(512)
            for i in range(blocks):index[i]=21+i
            body=payload if blocks<=1 else index+payload
            deleted=[(3,4,b'DATA',20,1 if blocks<=1 else blocks+1,size,body)]
            faults=['append-output','verify-eof-error','verify-close-error','verify-cancel-close','verify-open-error']
            for at in sorted({1,(blocks+1)//2,blocks}) if blocks else ():
                faults.extend(f'{kind}={at}' for kind in ('corrupt-write','verify-read-error','verify-short','verify-cancel-read','verify-source-error','verify-source-cancel'))
            for fault in faults:
                for keep in (False,True):
                    with self.subTest(size=size,fault=fault,keep=keep):
                        modes=['','keep-file',fault]
                        if keep:modes.append('keep-partial')
                        note,out=self.undelete_root(deleted,'r',*modes)
                        self.assertNotIn('Recovered',note)
                        self.assertEqual(self.recovery_verification[2],0 if fault=='verify-open-error' else 1)
                        expected={'KEEP':b'preserve existing bytes'}
                        if keep:
                            actual=bytearray(payload)
                            if fault=='append-output':actual+=b'!'
                            if fault.startswith('corrupt-write='):actual[512*(int(fault.split('=')[1])-1)]^=1
                            expected['DATA']=bytes(actual)
                            self.assertIn('Cleanup failed',note)
                        self.assertEqual({p.name:p.read_bytes() for p in out.iterdir()},expected)

    def test_undelete_verifies_empty_seedling_and_sparse_index_layouts(self):
        cases=[(0,1,b'',b''),(1,1,b'x',b'x')]
        for tree in (False,True):
            size=131073 if tree else 513
            data=b'A'*512
            index=bytearray(512);index[0]=22 if tree else 21
            master=bytearray(512);master[0]=21
            for swapped in (False,True):
                transform=lambda b:b[256:]+b[:256] if swapped else b
                body=(transform(master) if tree else b'')+transform(index)+data
                cases.append((size,3 if tree else 2,body,data+bytes(size-512)))
        for size,blocks,body,payload in cases:
            with self.subTest(size=size,body=body[:2]):
                note,out=self.undelete_root([(3,4,b'DATA',20,blocks,size,body)],'r','','keep-file')
                self.assertIn('Recovered DATA',note)
                self.assertEqual({p.name:p.read_bytes() for p in out.iterdir()},
                                 {'KEEP':b'preserve existing bytes','DATA':payload})
                self.assertEqual(self.recovery_verification,[(size+511)//512,1,1])

    def test_undelete_refuses_directory_close_errors(self):
        for block,slot,name,close in [(2,1,b'EARLY',1),(2,1,b'EARLY',2),(5,12,b'LAST',52)]:
            with self.subTest(block=block,slot=slot,close=close):
                note,out=self.undelete_root([(block,slot,name,20,1,5,b'hello')],'r','','close=%d'%close)
                self.assertIn('Directory read failed',note)
                self.assertEqual(list(out.iterdir()),[],'untrusted metadata created a recovery file')
    def test_undelete_full_count_directory_errors_refuse_recovery(self):
        for block,slot,name,at in ((2,1,b'EARLY',1),(2,1,b'EARLY',4),
                                   (2,1,b'EARLY',5),(5,12,b'LAST',55)):
            with self.subTest(read=at):
                note,out=self.undelete_root([(block,slot,name,20,1,5,b'hello')],
                                            'r','','read=%d'%at)
                self.assertIn('Directory read failed',note)
                self.assertEqual(list(out.iterdir()),[])

    def test_undelete_full_count_write_errors_preserve_source_and_owned_partial(self):
        payload=b''.join(bytes([b])*512 for b in range(8))
        index=bytearray(512)
        for b in range(8):index[b]=21+b
        deleted=[(3,4,b'DATA',20,9,len(payload),index+payload)]
        for at in (1,4,8):
            for keep in (False,True):
                with self.subTest(write=at,cleanup_failed=keep):
                    modes=['','write=%d'%at]
                    if keep:modes.append('keep-partial')
                    note,out=self.undelete_root(deleted,'r',*modes)
                    self.assertNotIn('Recovered',note)
                    if keep:
                        self.assertIn('Cleanup failed',note)
                        self.assertEqual((out/'DATA').read_bytes(),payload[:at*512])
                    else:self.assertEqual(list(out.iterdir()),[])

    def test_undelete_invalid_declared_names_never_reach_create(self):
        names=(b'A/B',b'A/../../V01',b'A\0B',b'A B',b'A\\B',b'A\x80',b'A\x1B',b'Ab')
        for name in names:
            with self.subTest(name=name):
                note,out=self.undelete_root([(3,4,name,20,1,5,b'hello')],
                    'r','','nested-output','create-count')
                self.assertNotIn('Recovered',note)
                self.assertEqual(note.splitlines()[-1],'0')
                self.assertEqual((out/'A'/'KEEP').read_bytes(),b'preserve nested bytes')
                self.assertEqual(sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file()),['A/KEEP'])
                self.assertFalse((self.root/'V01').exists())

    def test_undelete_valid_names_and_inferred_lengths_still_recover(self):
        for name in (b'A',b'A.9',b'ABCDEFGHIJKLMNO',b'A23456789.12345'):
            for inferred in (False,True):
                with self.subTest(name=name,inferred=inferred):
                    modes=['']
                    if inferred:modes.append('zero-name-length')
                    note,out=self.undelete_root([(3,4,name,20,1,5,b'hello')],'r',*modes)
                    self.assertIn('Recovered',note)
                    self.assertEqual((out/name.decode()).read_bytes(),b'hello')

    def test_undelete_layout_io_errors_do_not_select_an_ambiguous_index(self):
        index=bytearray(512);index[0]=index[256]=1 # $0101 is unchanged by half swap
        data=bytes(range(256))*2
        for size,last in ((1024,data),(131073,bytes(512))):
            # Sapling index, or tree master with an all-hole child index.
            stored=index+bytes((257-21)*512)+last
            deleted=[(3,4,b'DATA',20,2,size,stored)]
            for fault in range(1,5):
                with self.subTest(size=size,fault=fault):
                    note,out=self.undelete_root(deleted,'r','','create-count','layout-fault=%d'%fault)
                    self.assertNotIn('Recovered',note)
                    self.assertEqual(note.splitlines()[-1],'0')
                    self.assertEqual(list(out.iterdir()),[])

    def test_undelete_walks_a_volume_root_by_its_own_blocks(self):
        """GET_FILE_INFO on a volume counts its used blocks, not the root's
        four: the walk must stop at the end of the chain, not fail past it."""
        note,_=self.undelete_root([],'n')
        self.assertIn('No more deleted entries',note)
        note,out=self.undelete_root([(5,12,b'LAST',20,1,5,b'hello')],'r')
        self.assertIn('Recovered LAST',note)
        self.assertEqual((out/'LAST').read_bytes(),b'hello')
    def unit_of(self,table,path,requested=0):
        out=subprocess.check_output([str(self.exe['unit_of']),table,path,'%X'%requested],text=True).split('\n')
        return int(out[0],16),out[1]
    def test_unit_of_finds_one_volume(self):
        t=online((0x61,b'V'),(0x72,b'DD'),(0xE4,b'LONG'))
        self.assertEqual(self.unit_of(t,'/DD/SUB/FILE'),(0x70,''))
        self.assertEqual(self.unit_of(t,'/LONG'),(0xE0,''))
        self.assertEqual(self.unit_of(t,'/LON'),(0,''))
        self.assertEqual(self.unit_of(t,'/V',0x60),(0x60,''))
        self.assertEqual(self.unit_of(t,'/V',0x70),(0,''))
    def test_unit_of_stops_at_the_terminator(self):
        """Before: the scan ran over all sixteen records, past the zero
        byte that ends the table, and a record left there by an older call
        (stale copy_buf) passed for a volume on line: here /V at unit $E0."""
        t=online((0x72,b'DD'),stale=[(0xE1,b'V')])
        self.assertEqual(self.unit_of(t,'/V'),(0,''))
        self.assertEqual(self.unit_of(t,'/V',0xE0),(0,''))
    def test_unit_of_refuses_two_volumes_of_one_name(self):
        """Before: the first record named V won (unit $50) while ProDOS could
        resolve /V to the other drive -- the WIPE/MOVE data loss of the bug
        hunt. Now 0 and the note says why; a requested unit (a volume-list
        row) still finds its own drive."""
        t=online((0x51,b'V'),(0x72,b'DD'),(0xE1,b'V'))
        self.assertEqual(self.unit_of(t,'/V/SUB'),(0,'Two volumes named /V: pick it in the volume list.'))
        self.assertEqual(self.unit_of(t,'/V',0xE0),(0xE0,''))
        self.assertEqual(self.unit_of(t,'/V',0x50),(0x50,''))
        self.assertEqual(self.unit_of(t,'/DD'),(0x70,''))
    def test_rescue_refuses_two_volumes_of_one_name(self):
        """V (whole volume) from a panel inside /V with two drives named V:
        refused before any block is read, with the twin note."""
        out=subprocess.check_output([str(self.exe['rescue_entry']),'twin'],text=True).strip()
        self.assertEqual(out,'Two volumes named /V: pick it in the volume list.')
    def test_undelete_refuses_two_volumes_of_one_name(self):
        """The directory is read through ProDOS by its path, the blocks by
        unit: with two drives named V they could be two disks. Refused from a
        path and from a volume-list row alike (before: the row's unit was
        read whatever ProDOS made of /V); nothing written, nothing recovered."""
        for mode in (('twin',),('twin','list')):
            with self.subTest(mode=mode):
                note,out=self.undelete_root([(5,12,b'LAST',20,1,5,b'hello')],'r',*mode)
                self.assertEqual(note,'Use another online destination volume.')
                self.assertFalse((out/'LAST').exists())
        note,out=self.undelete_root([(5,12,b'LAST',20,1,5,b'hello')],'r','','list')
        self.assertIn('Recovered LAST',note)
    def test_undelete_ignores_a_record_past_the_terminator(self):
        note,out=self.undelete_root([(5,12,b'LAST',20,1,5,b'hello')],'r','phantom')
        self.assertEqual(note,'Use another online destination volume.')
        self.assertFalse((out/'LAST').exists())
    def test_undelete_recovers_a_deleted_empty_file(self):
        note,out=self.undelete_root([(3,4,b'EMPTY',20,1,0,b'')],'r')
        self.assertIn('Recovered EMPTY',note)
        self.assertEqual((out/'EMPTY').read_bytes(),b'')
    def test_undelete_cancel_during_seedling_write_is_not_success(self):
        for mode in ('cancel-write','cancel-close'):
            with self.subTest(mode=mode):
                note,out=self.undelete_root([(3,4,b'DATA',20,1,5,b'hello')],'r','',mode)
                self.assertNotIn('Recovered',note)
                self.assertIn('cancelled',note.lower())
                self.assertEqual(list(out.iterdir()),[])
    def test_undelete_cancel_during_sapling_recovery_removes_owned_output(self):
        index=bytearray(512)
        for i in range(8):index[i]=21+i
        payload=bytes(range(256))*16
        for mode in ('','cancel-bar','cancel-write','cancel-close'):
            with self.subTest(mode=mode):
                note,out=self.undelete_root([(3,4,b'DATA',20,9,len(payload),index+payload)],'r','',mode)
                if mode:
                    self.assertNotIn('Recovered',note)
                    self.assertIn('cancelled',note.lower())
                    self.assertEqual(list(out.iterdir()),[])
                else:
                    self.assertIn('Recovered DATA',note)
                    self.assertEqual((out/'DATA').read_bytes(),payload)
    def test_undelete_empty_file_whose_key_block_is_reused_is_refused(self):
        note,out=self.undelete_root([(3,4,b'EMPTY',10,1,0,b'')],'r')   # block 10 belongs to LIVE
        self.assertNotIn('Recovered',note)
        self.assertFalse((out/'EMPTY').exists())
    def test_mkimage_sizes(self):
        for size in (280,1600,4000,8000,16000,32767):
            with self.subTest(size=size):
                path=self.root/'empty.po';subprocess.run([str(self.exe['mkimage']),str(path),str(size)],check=True)
                im=Image(path.read_bytes());self.assertEqual(im.header()['blocks'],size)
                self.assertEqual(im.header()['name'],'EMPTY');self.assertEqual(im.entries(2),[])
                self.assertEqual(im.free_blocks(),size-6-(size+4095)//4096)
                bits=im.d[6*512:(6+(size+4095)//4096)*512]
                self.assertTrue(all(not(bits[b>>3]&(0x80>>(b&7))) for b in range(size,len(bits)*8)))
    def sync(self,mode,reserved=None,cached_size=1600,payload=None):
        with tempfile.TemporaryDirectory(prefix='s-',dir='/tmp') as t:
            root=Path(t);s=root/'S';d=root/'D';s.mkdir();d.mkdir()
            original=b'original destination';replacement=bytes(range(200))*8 if payload is None else payload
            (s/'DATA').write_bytes(replacement);(d/'DATA').write_bytes(original)
            if reserved:(d/reserved).write_bytes(b'preexisting')
            output=subprocess.check_output([str(self.exe['sync']),str(s),str(d),str(mode),
                                        str(cached_size)]).splitlines()
            ok=output[0]==b'1'
            self.assertEqual(output[1], b'1' if mode in (2,4,12,13,14,15,16,18,19,20,21,22,23) and not reserved else b'0')
            self.assertEqual((s/'DATA').read_bytes(),replacement)
            if mode==12:self.assertFalse((d/'DATA').exists())
            elif mode==18:self.assertEqual((d/'DATA').read_bytes(),b'late arrival')
            else:self.assertEqual((d/'DATA').read_bytes(),replacement if ok else original)
            if reserved:self.assertEqual((d/reserved).read_bytes(),b'preexisting')
            else:
                if mode in (2,12,14,16,18,19,20,21,22,23):self.assertEqual((d/'A2FC.SYNC').read_bytes(),replacement)
                elif mode==15:self.assertEqual((d/'A2FC.SYNC').read_bytes(),b'')
                else:self.assertFalse((d/'A2FC.SYNC').exists())
                if mode in (4,12,13,18):self.assertEqual((d/'A2FC.BAK').read_bytes(),original)
                else:self.assertFalse((d/'A2FC.BAK').exists())
            if mode in (15,16):self.assertIn(b'cleanup failed',output[2])
            if mode in (12,18):self.assertIn(b'restore failed',output[2])
            return ok
    def test_sync_verified_replace(self):self.assertTrue(self.sync(0))
    def test_sync_rechecks_destination_protection_before_replacing(self):
        for mode in (19,20,21,22,23):
            with self.subTest(mode=mode):self.assertFalse(self.sync(mode))
    def test_sync_tree_skips_write_locked_targets_before_creating_output(self):
        with tempfile.TemporaryDirectory(prefix='sync-lock-',dir='/tmp') as t:
            root=Path(t);s=root/'S';d=root/'D';s.mkdir();d.mkdir()
            payload=bytes(range(200))*8;original=b'write-locked original'
            for name in ('DATA','DATA2'):
                (s/name).write_bytes(payload);(d/name).write_bytes(original)
            run=subprocess.run([str(self.exe['sync']),str(s),str(d),'19','1600','tree'],
                               capture_output=True,text=True,check=True)
            self.assertIn('0 copied',run.stdout)
            for name in ('DATA','DATA2'):
                self.assertEqual((s/name).read_bytes(),payload)
                self.assertEqual((d/name).read_bytes(),original)
            self.assertEqual(sorted(p.name for p in d.iterdir()),['DATA','DATA2'])
    def test_sync_directory_stream_error_preserves_existing_files(self):
        with tempfile.TemporaryDirectory(prefix='sync-dir-error-',dir='/tmp') as t:
            root=Path(t);s=root/'S';d=root/'D';s.mkdir();d.mkdir()
            payload=bytes(range(200))*8;original=b'original must survive'
            for name in ('DATA','DATA2'):
                (s/name).write_bytes(payload);(d/name).write_bytes(original)
            run=subprocess.run([str(self.exe['sync']),str(s),str(d),'35','1600','tree'],
                               capture_output=True,text=True,check=True)
            self.assertIn('0 copied',run.stdout)
            self.assertIn('1 errors',run.stdout)
            for name in ('DATA','DATA2'):
                self.assertEqual((s/name).read_bytes(),payload)
                self.assertEqual((d/name).read_bytes(),original)
            self.assertEqual(sorted(p.name for p in d.iterdir()),['DATA','DATA2'])

    def test_sync_malformed_dates_do_not_create_or_replace_files(self):
        for mode in range(36,43):
            for exists in (False,True):
                with self.subTest(mode=mode,exists=exists):
                    with tempfile.TemporaryDirectory(prefix='sync-date-',dir='/tmp') as t:
                        root=Path(t);s=root/'S';d=root/'D';s.mkdir();d.mkdir()
                        payload=bytes(range(200))*8;original=b'original date safety'
                        for name in ('DATA','DATA2'):
                            (s/name).write_bytes(payload)
                            if exists:(d/name).write_bytes(original)
                        run=subprocess.run([str(self.exe['sync']),str(s),str(d),str(mode),'1600','tree'],
                                           capture_output=True,text=True,check=True)
                        self.assertIn('0 copied',run.stdout)
                        self.assertIn('2 errors',run.stdout)
                        for name in ('DATA','DATA2'):
                            self.assertEqual((s/name).read_bytes(),payload)
                            if exists:self.assertEqual((d/name).read_bytes(),original)
                        self.assertEqual(sorted(p.name for p in d.iterdir()),['DATA','DATA2'] if exists else [])

    def test_sync_invalid_destination_dates_preserve_originals(self):
        for mode in range(44,54):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory(prefix='sync-dest-date-',dir='/tmp') as t:
                    root=Path(t);s=root/'S';d=root/'D';s.mkdir();d.mkdir()
                    payload=bytes(range(200))*8;original=b'original destination date'
                    for name in ('DATA','DATA2'):
                        (s/name).write_bytes(payload);(d/name).write_bytes(original)
                    run=subprocess.run([str(self.exe['sync']),str(s),str(d),str(mode),'1600','tree'],
                                       capture_output=True,text=True,check=True)
                    for name in ('DATA','DATA2'):
                        self.assertEqual((s/name).read_bytes(),payload)
                        self.assertEqual((d/name).read_bytes(),original)
                    if mode<49:
                        self.assertIn('0 copied',run.stdout)
                        self.assertIn('2 errors',run.stdout)
                        expected=['DATA','DATA2']
                    else:
                        self.assertIn('SYNC stopped:',run.stdout)
                        self.assertEqual((d/'A2FC.SYNC').read_bytes(),payload)
                        expected=['A2FC.SYNC','DATA','DATA2']
                    self.assertEqual(sorted(p.name for p in d.iterdir()),expected)

    def test_sync_valid_timestamp_limits_still_replace_files(self):
        with tempfile.TemporaryDirectory(prefix='sync-date-ok-',dir='/tmp') as t:
            root=Path(t);s=root/'S';d=root/'D';s.mkdir();d.mkdir()
            payload=bytes(range(200))*8
            for name in ('DATA','DATA2'):
                (s/name).write_bytes(payload);(d/name).write_bytes(b'older original')
            run=subprocess.run([str(self.exe['sync']),str(s),str(d),'43','1600','tree'],
                               capture_output=True,text=True,check=True)
            self.assertIn('2 copied',run.stdout)
            self.assertIn('0 errors',run.stdout)
            for name in ('DATA','DATA2'):
                self.assertEqual((s/name).read_bytes(),payload)
                self.assertEqual((d/name).read_bytes(),payload)
            self.assertEqual(sorted(p.name for p in d.iterdir()),['DATA','DATA2'])

    def test_sync_malformed_entry_cannot_overwrite_outside_destination(self):
        with tempfile.TemporaryDirectory(prefix='names-',dir='/tmp') as t:
            root=Path(t);s=root/'A'/'S';d=root/'B'/'D';s.mkdir(parents=True);d.mkdir(parents=True)
            payload=bytes(range(200))*8;original=b'outside destination: keep these bytes'
            (s.parent/'VICTIM').write_bytes(payload);(d.parent/'VICTIM').write_bytes(original)
            run=subprocess.run([str(self.exe['sync']),str(s),str(d),'34','1600','tree'],
                               capture_output=True,text=True,check=True)
            self.assertEqual((d.parent/'VICTIM').read_bytes(),original)
            self.assertEqual((s.parent/'VICTIM').read_bytes(),payload)
            self.assertIn('0 copied',run.stdout)
            self.assertEqual(list(s.iterdir()),[])
            self.assertEqual(list(d.iterdir()),[])
    def test_sync_bar_covers_copy_and_check(self):
        # 1,600 bytes, 256 at a time: seven steps of copy, then seven of the
        # read-back, which restarts the bar at 0 instead of leaving it full.
        with tempfile.TemporaryDirectory(prefix='s-',dir='/tmp') as t:
            root=Path(t);s=root/'S';d=root/'D';s.mkdir();d.mkdir()
            (s/'DATA').write_bytes(bytes(range(200))*8);(d/'DATA').write_bytes(b'old')
            run=subprocess.run([str(self.exe['sync']),str(s),str(d),'0','1600'],capture_output=True,check=True)
            bars=[l.split()[1:] for l in run.stderr.decode().splitlines() if l.startswith('BAR ')]
            steps=[int(k) for k in range(0,1600,256)]
            self.assertEqual(bars,[['DATA',str(k),'1600'] for k in steps*2])
    def test_sync_cancel_during_close_or_fresh_target_check_preserves_original(self):
        for size in (0,1,1600):
            replacement=bytes(i&255 for i in range(size))
            for mode in range(54,64):
                with self.subTest(size=size,mode=mode), tempfile.TemporaryDirectory(prefix='sync-stop-',dir='/tmp') as t:
                    s=Path(t)/'S';d=Path(t)/'D';s.mkdir();d.mkdir()
                    (s/'DATA').write_bytes(replacement)
                    (d/'DATA').write_bytes(b'original')
                    (d/'KEEP').write_bytes(b'untouched')
                    run=subprocess.run([str(self.exe['sync']),str(s),str(d),str(mode),str(size)],
                                       capture_output=True,text=True,check=True)
                    self.assertEqual(run.stdout.splitlines()[0],'0')
                    state=next(l.split()[1:] for l in run.stderr.splitlines() if l.startswith('STATE '))
                    early=mode<=61 and (mode-54)%4<2
                    self.assertEqual(list(map(int,state)),[0,0,2 if early else 4,2 if early else 4])
                    self.assertEqual((s/'DATA').read_bytes(),replacement)
                    keep=mode>=58 and mode<=61 or mode==63
                    files={p.name:p.read_bytes() for p in d.iterdir()}
                    self.assertEqual(files,{'DATA':b'original','KEEP':b'untouched',
                                            **({'A2FC.SYNC':replacement} if keep else {})})
                    if keep:self.assertIn('cleanup failed',run.stdout)

    def test_sync_faulted_block_stops_before_any_later_io(self):
        for size in (1,257,1600):
            payload=bytes(i&255 for i in range(size))
            blocks=(size+255)//256
            for target in sorted({1,min(2,blocks),(blocks+1)//2,blocks}):
                for phase in range(4):
                    for event in range(3):
                        for cleanup in range(2):
                            with self.subTest(size=size,target=target,phase=phase,event=event,cleanup=cleanup), tempfile.TemporaryDirectory(prefix='sync-io-',dir='/tmp') as t:
                                s=Path(t)/'S';d=Path(t)/'D';s.mkdir();d.mkdir()
                                (s/'DATA').write_bytes(payload);(d/'DATA').write_bytes(b'original')
                                (d/'KEEP').write_bytes(b'untouched')
                                mode=1000+24*target+6*phase+2*event+cleanup
                                run=subprocess.run([str(self.exe['sync']),str(s),str(d),str(mode),str(size)],
                                                   capture_output=True,text=True,check=True)
                                self.assertEqual(run.stdout.splitlines()[0],'0')
                                io=next(l.split()[1:] for l in run.stderr.splitlines() if l.startswith('IO '))
                                expected=([target,target-1,0,0] if phase==0 else
                                          [target,target,0,0] if phase==1 else
                                          [blocks,blocks,target,target-1] if phase==2 else
                                          [blocks,blocks,target,target])
                                self.assertEqual(list(map(int,io)),expected)
                                state=next(l.split()[1:] for l in run.stderr.splitlines() if l.startswith('STATE '))
                                self.assertEqual(list(map(int,state)),[0,0,2 if phase<2 else 4,2 if phase<2 else 4])
                                prefix=(256*(target-1) if phase==0 else
                                        min(256*target,size)-(event==2) if phase==1 else size)
                                self.assertEqual({p.name:p.read_bytes() for p in d.iterdir()},
                                                 {'DATA':b'original','KEEP':b'untouched',
                                                  **({'A2FC.SYNC':payload[:prefix]} if cleanup else {})})
                                self.assertEqual((s/'DATA').read_bytes(),payload)
                                if cleanup:self.assertIn('cleanup failed',run.stdout)

    def test_sync_cancel_before_create_never_mutates_destination(self):
        for size in (0,1,1600):
            payload=bytes(i&255 for i in range(size))
            for mode in range(88,95):
                for reserved in (None,'A2FC.SYNC','A2FC.BAK'):
                    with self.subTest(size=size,mode=mode,reserved=reserved), tempfile.TemporaryDirectory(prefix='sync-create-stop-',dir='/tmp') as t:
                        s=Path(t)/'S';d=Path(t)/'D';s.mkdir();d.mkdir()
                        for name in ('DATA','DATA2'):(s/name).write_bytes(payload)
                        original={'KEEP':b'untouched'}
                        if mode<93:original.update(DATA=b'original',DATA2=b'another original')
                        if reserved:original[reserved]=b'preexisting reserved file'
                        for name,data in original.items():(d/name).write_bytes(data)
                        args=[str(self.exe['sync']),str(s),str(d),str(mode),str(size)]
                        if mode>=90:args.append('tree')
                        run=subprocess.run(args,capture_output=True,text=True,check=True)
                        owned=next(l.split()[1:] for l in run.stderr.splitlines() if l.startswith('OWNED '))
                        self.assertEqual(list(map(int,owned)),[0,0])
                        self.assertEqual(run.stdout.splitlines()[0],'0')
                        self.assertEqual({p.name:p.read_bytes() for p in d.iterdir()},original)
                        self.assertEqual({p.name:p.read_bytes() for p in s.iterdir()},
                                         {'DATA':payload,'DATA2':payload})
                        state=next(l.split()[1:] for l in run.stderr.splitlines() if l.startswith('STATE '))
                        self.assertEqual(list(map(int,state)),[0,0,0,0])

    def test_sync_rechecks_newer_timestamp_before_replacing_changed_target(self):
        for size in (0,1,1600):
            payload=bytes(i&255 for i in range(size))
            for mode in range(95,103):
                for tree in (False,True):
                    with self.subTest(size=size,mode=mode,tree=tree), tempfile.TemporaryDirectory(prefix='sync-newer-',dir='/tmp') as t:
                        s=Path(t)/'S';d=Path(t)/'D';s.mkdir();d.mkdir()
                        names=('DATA','DATA2') if tree else ('DATA',)
                        for name in names:
                            (s/name).write_bytes(payload);(d/name).write_bytes(b'original')
                        (d/'KEEP').write_bytes(b'untouched')
                        args=[str(self.exe['sync']),str(s),str(d),str(mode),str(size)]
                        if tree:args.append('tree')
                        run=subprocess.run(args,capture_output=True,text=True,check=True)
                        refused=mode<=100
                        self.assertEqual(int(run.stdout.splitlines()[0]),0 if refused else len(names))
                        state=list(map(int,next(l.split()[1:] for l in run.stderr.splitlines() if l.startswith('STATE '))))
                        self.assertEqual(state[:2],[0,0] if refused else [2*len(names),len(names)])
                        expected={'KEEP':b'untouched'}
                        if refused:
                            expected.update(DATA=b'changed during copy',**{'A2FC.SYNC':payload})
                            if tree:expected['DATA2']=b'original'
                            self.assertIn('SYNC stopped:',run.stdout)
                        else:expected.update({name:payload for name in names})
                        self.assertEqual({p.name:p.read_bytes() for p in d.iterdir()},expected)
                        self.assertEqual({p.name:p.read_bytes() for p in s.iterdir()},
                                         {name:payload for name in names})

    def test_sync_empty_file_replace(self):self.assertTrue(self.sync(0,cached_size=0,payload=b''))
    def test_sync_write_failure_keeps_original(self):self.assertFalse(self.sync(1))
    def test_sync_install_failure_rolls_back(self):self.assertFalse(self.sync(2))
    def test_sync_cancel_keeps_original(self):self.assertFalse(self.sync(3))
    def test_sync_metadata_failure_retains_original_backup(self):self.assertTrue(self.sync(4))
    def test_sync_preexisting_temp_is_preserved(self):self.assertFalse(self.sync(0,'A2FC.SYNC'))
    def test_sync_preexisting_backup_is_preserved(self):self.assertFalse(self.sync(0,'A2FC.BAK'))
    def test_sync_stale_size_preserves_both_files(self):
        for size in (0,512,1599,1601):
            with self.subTest(size=size):self.assertFalse(self.sync(0,cached_size=size))
    def test_sync_extra_output_bytes_preserve_destination(self):self.assertFalse(self.sync(5))

    def test_sync_source_final_error_with_stale_size_preserves_both_files(self):
        for size in (0,512,1599,1600):
            with self.subTest(size=size):self.assertFalse(self.sync(6,cached_size=size))
    def test_sync_target_final_error_preserves_both_files(self):self.assertFalse(self.sync(7))
    def test_sync_every_close_failure_preserves_both_files(self):
        for mode in range(8,12):
            with self.subTest(close=mode-7):self.assertFalse(self.sync(mode))
    def test_sync_install_and_rollback_failure_preserves_backup(self):self.assertFalse(self.sync(12))
    def test_sync_backup_cleanup_failure_preserves_backup(self):self.assertTrue(self.sync(13))
    def test_sync_backup_rename_failure_preserves_original(self):self.assertFalse(self.sync(14))

    def test_sync_combined_failure_and_cleanup_failure_keeps_output(self):
        for mode in (15,16):
            with self.subTest(mode=mode):self.assertFalse(self.sync(mode))

    def test_sync_already_cancelled_needs_no_cleanup(self):self.assertFalse(self.sync(17))

    def test_sync_late_collision_preserves_arrival_and_recovery_files(self):
        self.assertFalse(self.sync(18))

    def test_sync_tree_stops_before_next_file_and_keeps_recovery_note(self):
        for mode in (0,2,4,12,13,14,15,16,17,18):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix='sync-tree-',dir='/tmp') as t:
                s=Path(t)/'S';d=Path(t)/'D';s.mkdir();d.mkdir()
                replacement=bytes(range(200))*8
                for name in ('DATA','DATA2'):
                    (s/name).write_bytes(replacement);(d/name).write_bytes(b'original')
                output=subprocess.check_output([str(self.exe['sync']),str(s),str(d),str(mode),'1600','tree'],timeout=10).splitlines()
                for name in ('DATA','DATA2'):self.assertEqual((s/name).read_bytes(),replacement)
                self.assertEqual((d/'DATA2').read_bytes(),b'original' if mode else replacement)
                self.assertEqual(output[1],b'1' if mode and mode!=17 else b'0')
                if mode==17:self.assertIn(b'SYNC cancelled:',output[2])
                elif mode:self.assertIn(b'SYNC stopped:',output[2])
                else:self.assertIn(b'2 copied',output[2])
                if mode in (12,18):self.assertIn(b'restore failed',output[2])
                if mode in (15,16):self.assertIn(b'cleanup failed',output[2])
                if mode in (2,12,14,16,18):self.assertEqual((d/'A2FC.SYNC').read_bytes(),replacement)
                if mode==15:self.assertEqual((d/'A2FC.SYNC').read_bytes(),b'')
                if mode==17:self.assertFalse((d/'A2FC.SYNC').exists())
                if mode in (4,12,13,18):self.assertEqual((d/'A2FC.BAK').read_bytes(),b'original')

if __name__=='__main__':unittest.main()
