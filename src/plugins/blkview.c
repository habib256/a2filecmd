/* Read-only block explorer for devices and PO/DSK/DO/2MG images.
 * H: hex and ASCII; D: directory interpretation; I: split-byte index.
 * Interpretations are explicit: arbitrary data is never called a directory. */
#define UTIL_FIXED_API
#define UTIL_CREATE
#define UTIL_VOLUME
#include "util.h"
#include "imageio.h"

#ifdef PLUGIN_HOST
#define v_cprintf (a.cprintf)
#define v_sprintf (a.sprintf)
#define v_cputs (a.cputs)
#define v_cputc (a.cputc)
#define v_gotoxy (a.gotoxy)
#define v_clrscr (a.clrscr)
#define v_cgetc (a.cgetc)
#define v_message (a.message)
#define v_prompt (a.prompt)
#define v_memcpy (a.memcpy)
#define v_strcpy (a.strcpy)
#define v_strcmp (a.strcmp)
#define v_strlen (a.strlen)
#define v_fopen (a.fopen)
#define v_fwrite (a.fwrite)
#define v_fclose (a.fclose)
#else
int __cdecl__ v_cprintf(const char*, ...);
int __cdecl__ v_sprintf(char*, const char*, ...);
void __fastcall__ v_cputs(const char*);
void __fastcall__ v_cputc(char);
void __fastcall__ v_gotoxy(unsigned char,unsigned char);
void __fastcall__ v_clrscr(void);
char __fastcall__ v_cgetc(void);
void __fastcall__ v_message(const char*);
unsigned char __fastcall__ v_prompt(const char*,const char*,unsigned char);
void* __fastcall__ v_memcpy(void*,const void*,size_t);
char* __fastcall__ v_strcpy(char*,const char*);
int __fastcall__ v_strcmp(const char*,const char*);
size_t __fastcall__ v_strlen(const char*);
FILE* __fastcall__ v_fopen(const char*,const char*);
size_t __fastcall__ v_fwrite(const void*,size_t,size_t,FILE*);
int __fastcall__ v_fclose(FILE*);
#endif
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

static unsigned char pattern[4], have_pattern, matched;
static unsigned int found_block, found_offset;
static unsigned long next_search;

/* Shift register search crosses block boundaries and finds overlapping matches.
 * Results are byte positions in normalized ProDOS order, never container offsets.
 * 0: exhausted; 1: found; 2: read error; 3: cancelled. */
static unsigned char search_bytes(unsigned long start)
{
    unsigned int b, i;
    unsigned long rolling = 0, wanted;
    unsigned char seen = 0;
    wanted = (unsigned long)pattern[0]<<24 | (unsigned long)pattern[1]<<16 |
             (unsigned int)pattern[2]<<8 | pattern[3];
    b = (unsigned int)(start>>9); i = (unsigned int)start & 511;
    for (; b < source.blocks; ++b) {
        if (stop()) return 3;
        if (!source_read(&source,b,buf)) return 2;
        for (; i < 512; ++i) {
            rolling = ((rolling<<8) | buf[i]) & 0xFFFFFFFFUL;
            if (seen < 4) ++seen;
            if (seen == 4 && rolling == wanted) {
                next_search = (unsigned long)b*512+i-2;
                found_block = (unsigned int)((next_search-1)>>9);
                found_offset = (unsigned int)(next_search-1)&511;
                return 1;
            }
        }
        i = 0;
    }
    next_search=(unsigned long)source.blocks*512;return 0;
}
static unsigned int number(const char* text, unsigned char n)
{
    unsigned int v=0;
    unsigned char c;
    while(n--) { c=*text++; v=(v<<4)|(c<='9' ? c-'0' : c-'A'+10); }
    return v;
}
static void search(unsigned char fresh)
{
    unsigned char i,r;
    if(fresh || !have_pattern) {
        if(!v_prompt("Find 4 bytes (8 hex digits)",NULL,8))return;
        for(i=0;i<4;++i)pattern[i]=(unsigned char)number(a.input+i*2,2);
        next_search=(unsigned long)block*512;
        have_pattern=1;
    }
    cancelled=0;
    v_message("Searching... ESC cancels");
    r=search_bytes(next_search);
    if(r==1) {
        block=found_block;page=found_offset>>8;mode='H';matched=1;
    } else {
        v_message(r==2 ? "Read error: search incomplete." : r==3 ? "Search cancelled." : "No further match.");
        v_cgetc();
    }
}
/* Extract whole blocks in normalized order. A partial file remains on errors.
 * One image stream plus one output stream fits ProDOS's two I/O buffers. */
static unsigned char extract_blocks(FILE* out,unsigned int count)
{
    unsigned int i;
    for(i=0;i<count;++i) {
        if(stop())return 3;
        if(!source_read(&source,block+i,buf))return 2;
        if(v_fwrite(buf,1,512,out)!=512)return 1;
    }
    return 0;
}
static void extract(void)
{
    unsigned int count;
    unsigned char r;
    FILE* out;
    if(other->fs || !other->path[0]) { v_message("Open destination in other panel."); v_cgetc(); return; }
    if(source.unit && source.unit==unit_of(other->path,0)) { v_message("Choose another destination volume.");v_cgetc();return; }
    if(!v_prompt("Block count (4 hex digits, max 7FFF)",NULL,4))return;
    count=number(a.input,4);
    if(!count || count>32767U || count>source.blocks-block) { v_message("Invalid block range."); v_cgetc(); return; }
    if(!v_prompt("New binary file (other panel)",NULL,0))return;
    if(!join(a.other_full,other->path,a.input)) { v_message("Path too long."); v_cgetc(); return; }
    if(newfile(a.other_full,6,0,1)) { v_message("Cannot create file (name in use?)."); v_cgetc(); return; }
    *a.filetype=6;*a.auxtype=0;
    out=v_fopen(a.other_full,"wb");
    if(!out) { v_message("Cannot open output; empty file remains."); v_cgetc(); return; }
    cancelled=0;v_message("Extracting... ESC cancels");
    r=extract_blocks(out,count);
    if(v_fclose(out))r=1;
    v_message(r ? "Extraction incomplete; partial file kept." : "Blocks extracted to other panel.");v_cgetc();
}

static void hex(void)
{
    unsigned int off;
    unsigned char r, c, ch;
    for (r=0; r<16; ++r) {
        off = (unsigned int)page*256 + (unsigned int)r*16;
        v_gotoxy(0,r+3); v_cprintf("%03X  ",off);
        for(c=0;c<16;++c) v_cprintf("%02X ",buf[off+c]);
        v_cputs(" ");
        for(c=0;c<16;++c) {
            ch=buf[off+c]&127; v_cputc(ch>=32 && ch<127 ? ch : '.');
        }
    }
}
static void directory(void)
{
    unsigned char i,n,kind;
    unsigned char* e;
    char name[16];
    v_cputs("Interpret as ProDOS directory: previous/next blocks ");
    v_cprintf("%u/%u\r\n",rd16(buf),rd16(buf+2));
    v_cputs(" #  Name             Kind Type   Key Blocks      EOF\r\n");
    for(i=0;i<13;++i) {
        e=buf+4+(unsigned int)i*39; kind=e[0]>>4; n=e[0]&15;
        v_memcpy(name,e+1,n); name[n]=0;
        /* Corrupt names must not send control codes to the terminal. */
        for(n=0;name[n];++n) if((unsigned char)name[n]<32 || (unsigned char)name[n]>126)name[n]='.';
        v_cprintf("%2u  %-15s  %X   ",i,kind ? name : "<deleted>",kind);
        if(kind>=14) v_cprintf("HEADER entries=%u\r\n",rd16(e+33));
        else v_cprintf("$%02X %5u %5u %8lu\r\n",e[16],rd16(e+17),rd16(e+19),rd24(e+21));
    }
}
static void index_view(void)
{
    unsigned char r,c;
    unsigned int i,b;
    v_cprintf("Interpret as ProDOS index: entries %u..%u (0 = hole)\r\n",(unsigned int)page*32,(unsigned int)page*32+31);
    for(r=0;r<16;++r) {
        for(c=0;c<2;++c) {
            i=(unsigned int)page*32+r+(unsigned int)c*16;
            b=buf[i]|((unsigned int)buf[i+256]<<8);
            v_gotoxy(c*38,r+3);
            v_cprintf("%3u -> %5u ($%04X)%s",i,b,b,b>=source.blocks ? " OUTSIDE" : "");
        }
    }
}
static void jump(void)
{
    unsigned int b;
    if(!v_prompt("Block number (4 hex digits)",NULL,4))return;
    b=number(a.input,4);
    if(b>=source.blocks) { v_message("Block outside this disk/image."); v_cgetc(); return; }
    block=b; page=0;
}
void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char key,unit;
    init(api); block=0; page=0; mode='H';have_pattern=matched=0;
    if(pan->fs) { note("Select a real ProDOS volume or an image file."); return; }
    if(pan->path[0] && image_kind(a.selected->name)) {
        if(!a.full[0]) { note("Image path too long."); return; }
        v_strcpy(source.path,a.full);
        if(!image_open(&source)) { note("Invalid or unreadable image."); return; }
    } else {
        v_strcpy(source.path,pan->path[0] ? pan->path : a.selected->name);
        unit=pan->path[0] ? 0 : (unsigned char)(a.selected->mdate<<4);
        if(source.path[0]!='/' || !volume_open(&source,unit)) { note("Cannot open ProDOS volume."); return; }
    }
    do {
        if(!source_read(&source,block,buf)) { note("BLKVIEW: block read failed."); break; }
        v_clrscr(); v_cprintf("BLKVIEW - READ ONLY - %s\r\n",source.path);
        v_cprintf("Block %u ($%04X) / %u blocks   View %c   Page %u\r\n",block,block,source.blocks,mode,page+1);
        if(mode=='D') directory(); else if(mode=='I') index_view(); else hex();
        v_gotoxy(0,22); v_cputs("N/P Block G Go SPACE Page H/D/I View F Find A Again X Extract ESC Back");
        if(matched) { v_gotoxy(0,20);v_cprintf("Match at block %u, offset $%03X",found_block,found_offset); }
        key=v_cgetc();matched=0;
        if(key==KEY_ESC)break;
        if(key==' ') { page=(page+1)&(mode=='I' ? 7 : mode=='H' ? 1 : 0); continue; }
        key &= 0xDF;
        if(key=='N' && block<source.blocks-1) { ++block; page=0; }
        if(key=='P' && block) { --block; page=0; }
        if(key=='G') jump();
        if(key=='F' || key=='A')search(key=='F');
        if(key=='X')extract();
        if(key=='H' || key=='D' || key=='I') { mode=key; page=0; }
    } while(1);
    source_close(&source);
}
