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
static unsigned char depth,row,partial,boot;
/* The common ProDOS file types by name, anything else in hex. */
static const unsigned char codes[]={0x04,0x06,0x0F,0x19,0x1A,0x1B,0xB3,0xFA,0xFB,0xFC,0xFD,0xFE,0xFF};
static const char names[]="TXTBINDIRADBAWPASPS16INTIVRBASVARRELSYS";
static char tname[4];
static void typename(unsigned char t) {
    unsigned char i;
    for(i=0;i<sizeof codes;++i)if(codes[i]==t){a.memcpy(tname,names+i*3,3);tname[3]=0;return;}
    a.sprintf(tname,"$%02X",t);
}
static void indent(unsigned char n){while(n--)a.cputs("  ");}
static unsigned long totalbytes;static unsigned int totalfiles;
static unsigned char line(void) {
    if(row==20) {
        a.gotoxy(0,22);a.cputs("SPACE Next page  ESC Back");
        if(a.cgetc()==KEY_ESC){cancelled=1;return 0;}
        a.clrscr();a.cputs("TREE - READ ONLY, DISK ORDER\r\n");row=2;
    }
    a.gotoxy(0,row++);return !stop();
}
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
    unsigned char r,i;unsigned long size;struct Frame* f;
    init(api);dir_reset();partial=0;row=2;depth=0;
    if(pan->fs){note("TREE needs a real ProDOS directory.");return;}
    a.strcpy(path,pan->path[0]?pan->path:a.selected->name);
    if(path[0]!='/' || !dir_begin(path,&frames[0].blocks)){note("Cannot read directory.");return;}
    /* Only a volume's own directory is searched at boot. */
    boot=info.storage==15;
    frames[0].pos=frames[0].bytes=frames[0].files=0;frames[0].len=a.strlen(path);
    a.clrscr();a.cprintf("TREE - READ ONLY, DISK ORDER\r\n%s\r\n",path);
    for(;;) {
        f=&frames[depth];if(stop())break;
        r=dir_next(path,f->blocks,&f->pos);
        if(r==2){partial=1;r=0;}
        if(!r) {
            if(!line())break;
            if(!depth){
                a.cprintf("%s/ : %lu bytes, %u files",path,f->bytes,f->files);
                totalbytes=f->bytes;totalfiles=f->files;break;
            }
            indent(depth);
            a.cprintf("= %s/ : %lu bytes, %u files",path+frames[depth-1].len+1,f->bytes,f->files);
            frames[depth-1].bytes+=f->bytes;frames[depth-1].files+=f->files;
            --depth;path[frames[depth].len]=0;continue;
        }
        rawname(name);
        if((raw[0]>>4)==13) {
            if(depth==15 || !join(a.full,path,name)){partial=1;continue;}
            if(!dir_begin(a.full,&frames[depth+1].blocks)){partial=1;continue;}
            a.strcpy(path,a.full);++depth;f=&frames[depth];
            f->pos=f->bytes=f->files=0;f->len=a.strlen(path);
            if(!line())break;indent(depth-1);a.cprintf("%s/",name);
        }else {
            /* Seedling, sapling, tree, and 5: a forked (GS/OS extended)
             * file, a file like any other with the size its entry gives,
             * as the panels show it -- its forks are not opened. It used to
             * be taken for an unreadable directory: every GS/OS volume
             * ended INCOMPLETE. Anything else is not known to be a file. */
            r=raw[0]>>4;
            /* ProDOS 8 starts the first $FF file whose name ends in
             * .SYSTEM in the volume directory, in this disk order. An
             * unknown or forked entry before it: no guess, no mark. */
            i=raw[0]&15;
            if(!depth && (r>3 || raw[16]==0xFF && i>7 && !a.strcmp(name+i-7,".SYSTEM"))){i=r<4 && boot;boot=0;}
            else i=0;
            if(r>3 && r!=5){partial=1;continue;}
            size=rd24(raw+21);f->bytes+=size;++f->files;
            if(!line())break;
            indent(depth);typename(raw[16]);
            a.cprintf(r==5?"%-15s %s %lu bytes (forked)":"%-15s %s %lu bytes",name,tname,size);
            if(i)a.cputs("  <- boots");
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
