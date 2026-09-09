#define UTIL_INFO
#include "util.h"
#include "dirscan.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int magic;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[52];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},"Directory tree with cumulative file sizes"};
#pragma rodata-name(pop)
struct Frame {unsigned long pos,bytes;unsigned int blocks,files;unsigned char len;};
static struct Frame frames[16];
static char path[PATH_LEN],name[16];
static unsigned char depth,row,partial;
static unsigned long totalbytes;static unsigned int totalfiles;
static unsigned char line(void) {
    if(row==20) {
        a.gotoxy(0,22);a.cputs("SPACE Next page  ESC Back");
        if(a.cgetc()==KEY_ESC){cancelled=1;return 0;}
        a.clrscr();a.cputs("TREE - READ ONLY\r\n");row=2;
    }
    a.gotoxy(0,row++);return !stop();
}
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
    unsigned char r,i;unsigned long size;struct Frame* f;
    init(api);dir_reset();partial=0;row=2;depth=0;
    if(pan->fs){note("TREE needs a real ProDOS directory.");return;}
    a.strcpy(path,pan->path[0]?pan->path:a.selected->name);
    if(path[0]!='/' || !dir_begin(path,&frames[0].blocks)){note("Cannot read directory.");return;}
    frames[0].pos=frames[0].bytes=frames[0].files=0;frames[0].len=a.strlen(path);
    a.clrscr();a.cprintf("TREE - READ ONLY\r\n%s\r\n",path);
    for(;;) {
        f=&frames[depth];if(stop())break;
        r=dir_next(path,f->blocks,&f->pos);
        if(r==2){partial=1;r=0;}
        if(!r) {
            if(!line())break;
            a.cprintf("%s/ : %lu bytes, %u files",path,f->bytes,f->files);
            if(!depth){totalbytes=f->bytes;totalfiles=f->files;break;}
            frames[depth-1].bytes+=f->bytes;frames[depth-1].files+=f->files;
            --depth;path[frames[depth].len]=0;continue;
        }
        rawname(name);
        if((raw[0]>>4)==13) {
            if(depth==15 || !join(a.full,path,name)){partial=1;continue;}
            if(!dir_begin(a.full,&frames[depth+1].blocks)){partial=1;continue;}
            a.strcpy(path,a.full);++depth;f=&frames[depth];
            f->pos=f->bytes=f->files=0;f->len=a.strlen(path);
            if(!line())break;a.cprintf("%s/",path);
        }else {
            if((raw[0]>>4)>3){partial=1;continue;}
            size=rd24(raw+21);f->bytes+=size;++f->files;
            if(!line())break;
            for(i=0;i<depth*2;++i)a.cputc(' ');
            a.cprintf("%s  %lu bytes",name,size);
        }
    }
    if(cancelled)note("TREE cancelled; totals incomplete.");
    else {
        a.gotoxy(0,22);a.cputs(partial?"INCOMPLETE: unreadable directory/path/depth limit. ESC Back":"TREE complete. ESC/RETURN Back");
        do{r=a.cgetc();}while(r!=KEY_ESC && r!=KEY_RETURN);
        if(partial)note("TREE incomplete: some directories could not be scanned.");
        else a.sprintf(a.note,"TREE: %u files, %lu bytes (directory totals include descendants).",totalfiles,totalbytes);
    }
}
