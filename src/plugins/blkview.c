/* Read-only block explorer for devices and PO/DSK/DO/2MG images.
 * H: hex and ASCII; D: directory interpretation; I: split-byte index.
 * Interpretations are explicit: arbitrary data is never called a directory. */
#define UTIL_VOLUME
#include "util.h"
#include "imageio.h"
void __fastcall__ plugin_entry(const struct A2fcApi* api);
struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char reserved[3]; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, {0,0,0},
    "Read-only blocks: hex, directories and indexes"
};
#pragma rodata-name (pop)
static struct Source source;
static unsigned int block;
static unsigned char page, mode;

static unsigned char is_image(const char* name)
{
    unsigned char n = a.strlen(name);
    return (n > 3 && (!a.strcmp(name+n-3,".PO") || !a.strcmp(name+n-3,".DO"))) ||
        (n > 4 && (!a.strcmp(name+n-4,".DSK") || !a.strcmp(name+n-4,".2MG") || !a.strcmp(name+n-4,".HDV")));
}
static void hex(void)
{
    unsigned int off;
    unsigned char r, c, ch;
    for (r=0; r<16; ++r) {
        off = (unsigned int)page*256 + (unsigned int)r*16;
        a.gotoxy(0,r+3); a.cprintf("%03X  ",off);
        for(c=0;c<16;++c) a.cprintf("%02X ",buf[off+c]);
        a.cputs(" ");
        for(c=0;c<16;++c) {
            ch=buf[off+c]&127; a.cputc(ch>=32 && ch<127 ? ch : '.');
        }
    }
}
static void directory(void)
{
    unsigned char i,n,kind;
    unsigned char* e;
    char name[16];
    a.cputs("Interpret as ProDOS directory: previous/next blocks ");
    a.cprintf("%u/%u\r\n",rd16(buf),rd16(buf+2));
    a.cputs(" #  Name             Kind Type   Key Blocks      EOF\r\n");
    for(i=0;i<13;++i) {
        e=buf+4+(unsigned int)i*39; kind=e[0]>>4; n=e[0]&15;
        a.memcpy(name,e+1,n); name[n]=0;
        /* Corrupt names must not send control codes to the terminal. */
        for(n=0;name[n];++n) if((unsigned char)name[n]<32 || (unsigned char)name[n]>126)name[n]='.';
        a.cprintf("%2u  %-15s  %X   ",i,kind ? name : "<deleted>",kind);
        if(kind>=14) a.cprintf("HEADER entries=%u\r\n",rd16(e+33));
        else a.cprintf("$%02X %5u %5u %8lu\r\n",e[16],rd16(e+17),rd16(e+19),rd24(e+21));
    }
}
static void index_view(void)
{
    unsigned char r,c;
    unsigned int i,b;
    a.cprintf("Interpret as ProDOS index: entries %u..%u (0 = hole)\r\n",(unsigned int)page*32,(unsigned int)page*32+31);
    for(r=0;r<16;++r) {
        for(c=0;c<2;++c) {
            i=(unsigned int)page*32+r+(unsigned int)c*16;
            b=buf[i]|((unsigned int)buf[i+256]<<8);
            a.gotoxy(c*38,r+3);
            a.cprintf("%3u -> %5u ($%04X)%s",i,b,b,b>=source.blocks ? " OUTSIDE" : "");
        }
    }
}
static void jump(void)
{
    unsigned char i,ch,n;
    unsigned int b=0;
    if(!a.prompt("Block number (4 hex digits)",NULL,4))return;
    n=a.strlen(a.input);
    if(n!=4)return;
    for(i=0;i<n;++i) {
        ch=a.input[i];
        if(ch>='0' && ch<='9')ch-='0';
        else { ch &= 0xDF; if(ch<'A' || ch>'F')return; ch-= 'A'-10; }
        b=(b<<4)|ch;
    }
    if(b>=source.blocks) { a.message("Block outside this disk/image."); a.cgetc(); return; }
    block=b; page=0;
}
void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char key,unit;
    init(api); block=0; page=0; mode='H';
    if(pan->fs) { note("Select a real ProDOS volume or an image file."); return; }
    if(pan->path[0] && is_image(a.selected->name)) {
        if(!a.full[0]) { note("Image path too long."); return; }
        a.strcpy(source.path,a.full);
        if(!image_open(&source)) { note("Invalid or unreadable image."); return; }
    } else {
        a.strcpy(source.path,pan->path[0] ? pan->path : a.selected->name);
        unit=pan->path[0] ? 0 : (unsigned char)(a.selected->mdate<<4);
        if(source.path[0]!='/' || !volume_open(&source,unit)) { note("Cannot open ProDOS volume."); return; }
    }
    do {
        if(!source_read(&source,block,buf)) { note("BLKVIEW: block read failed."); break; }
        a.clrscr(); a.cprintf("BLKVIEW - READ ONLY - %s\r\n",source.path);
        a.cprintf("Block %u ($%04X) / %u blocks   View %c   Page %u\r\n",block,block,source.blocks,mode,page+1);
        if(mode=='D') directory(); else if(mode=='I') index_view(); else hex();
        a.gotoxy(0,22); a.cputs("N/P Block  G Go(hex)  SPACE Page  H Hex  D Directory  I Index  ESC Back");
        key=a.cgetc();
        if(key==KEY_ESC)break;
        if(key==' ') { page=(page+1)&(mode=='I' ? 7 : mode=='H' ? 1 : 0); continue; }
        key &= 0xDF;
        if(key=='N' && block<source.blocks-1) { ++block; page=0; }
        if(key=='P' && block) { --block; page=0; }
        if(key=='G') jump();
        if(key=='H' || key=='D' || key=='I') { mode=key; page=0; }
    } while(1);
    source_close(&source);
}
