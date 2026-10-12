/* Create a new, empty ProDOS filesystem in a PO or 2MG file.
 * Writes only an exclusively created destination and MAIN buffers, never
 * AUX /RAM. Read back the closed image before claiming success; cleanup
 * failure retains the owned file and reports that it is incomplete. */
#define UTIL_CREATE
#define UTIL_DISCARD
#include "util.h"
#include <string.h>
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int magic;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[52];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},"Create an empty formatted .PO or .2MG image"};
#pragma rodata-name(pop)
static char path[PATH_LEN], name[16];
static unsigned int blocks, maps, b;
static unsigned char two;
static FILE* out;
static unsigned char check[512];
static const unsigned int sizes[]={280,1600,4000,8000,16000,32767};
static void makeheader(void) {
    unsigned long length=(unsigned long)blocks*512;
    a.memset(buf,0,64);a.memcpy(buf,"2IMGA2FC",8);buf[8]=64;buf[10]=buf[12]=1;
    wr16(buf+20,blocks);buf[24]=64;
    buf[28]=length;buf[29]=length>>8;buf[30]=length>>16;
}
static void makeblock(void) {
    unsigned int n,k; unsigned long v;
    a.memset(buf,0,512);
    if(b>=2 && b<=5) {
        wr16(buf,b==2?0:b-1);wr16(buf+2,b==5?0:b+1);
        if(b==2) {
            n=a.strlen(name);buf[4]=0xF0|n;a.memcpy(buf+5,name,n);
            buf[34]=0xC3;buf[35]=39;buf[36]=13;wr16(buf+39,6);wr16(buf+41,blocks);
        }
    } else if(b>=6 && b<6+maps) {
        for(n=0;n<4096;++n) {
            v=(unsigned long)(b-6)*4096+n;
            if(v>=6+maps && v<blocks) {k=n>>3;buf[k]|=0x80>>(n&7);}
        }
    }
}
static unsigned char matches(unsigned int n) {
    /* ESC can arrive during a full-count read. Stop before another read
     * of our exclusive image; only MAIN buffers are involved. */
    return a.fread(check,1,n,out)==n && !ferror(out) && !stop() && !memcmp(check,buf,n);
}
static unsigned char verify_image(void) {
    unsigned char ok=0;
    out=a.fopen(path,"rb");if(!out)return 0;
    if(two) {makeheader();if(!matches(64))goto done;}
    for(b=0;b<blocks;++b) {
        if(!(b&31)) {a.progress_bar("Checking image (ESC)",b,blocks);if(stop())goto done;}
        makeblock();if(!matches(512))goto done;
    }
    ok=!a.fread(check,1,1,out) && !ferror(out);
done:
    if(a.fclose(out))ok=0;
    if(stop())ok=0;
    return ok;
}
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
    unsigned char k;
    init(api);
    if(pan->fs || !pan->path[0]) {note("Open a ProDOS destination directory.");return;}
    a.message("\1MKIMAGE: P .PO  2 .2MG  ESC Cancel");
    do{k=a.cgetc();if(k==KEY_ESC)return;}while(k!='P'&&k!='p'&&k!='2');two=k=='2';
    a.message("\1Size: 1 140K  2 800K  3 2M  4 4M  5 8M  6 16M  ESC");
    do{k=a.cgetc();if(k==KEY_ESC)return;}while(k<'1'||k>'6');blocks=sizes[k-'1'];
    if(!a.prompt("Image base name (up to 11 characters)","NEW",0))return;
    if(a.strlen(a.input)>11) {note("Name too long.");return;}
    a.strcpy(name,a.input);a.sprintf(a.full,"%s%s",name,two?".2MG":".PO");
    if(!join(path,pan->path,a.full)) {note("Path too long.");return;}
    /* A completed prompt can still deliver ESC. No output is owned yet. */
    if(stop()) {note("Stopped: nothing created.");return;}
    if(newfile(path,6,0,1)) {note("Cannot create image: name exists or disk unavailable.");return;}
    *a.filetype=6;*a.auxtype=0;out=a.fopen(path,"wb");
    if(!out) {if(discard(path))note("Cannot open new image.");return;}
    /* CREATE/OPEN may deliver ESC too: before the 2MG header or blocks.
     * Cleanup owns only this exclusive file; no AUX memory is touched. */
    if(stop())goto fail;
    if(two) {
        makeheader();if(a.fwrite(buf,1,64,out)!=64 || ferror(out) || stop())goto fail;
    }
    maps=(blocks+4095U)/4096;
    for(b=0;b<blocks;++b) {
        if(!(b&31)) {a.progress_bar("New image (ESC)",b,blocks);if(stop())goto fail;}
        /* An ESC delivered by fwrite must stop before another block or
         * the verification pass. Only this exclusive image is owned. */
        makeblock();if(a.fwrite(buf,1,512,out)!=512 || ferror(out) || stop())goto fail;
    }
    if(a.fclose(out))goto closedfail;
    if(!verify_image())goto closedfail;
    a.sprintf(a.note,"Created %s: %u blocks, empty ProDOS volume.",name,blocks);return;
fail:a.fclose(out);
closedfail:if(discard(path))note("Image incomplete: removed (cancelled or I/O error).");
}
