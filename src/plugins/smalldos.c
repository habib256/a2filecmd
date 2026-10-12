/* SMALLDOS (Wilderness): read-only contiguous-sector extraction.
 * Only exclusive new ProDOS outputs are written; no raw writes or AUX.
 * Raw 35-track .DSK/.DO (DOS order) and .PO (ProDOS order) images.
 * Preserve every allocated byte: no exact byte length/load address exists
 * in the catalogue. Reference: wilderness/tools/smalldos.py in pom2games. */
#define UTIL_STUBS
#define UTIL_CREATE
#define UTIL_DISCARD
#include "util.h"
#include <string.h>

void __fastcall__ plugin_entry(const struct A2fcApi* api);
struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0,r1,r2; char desc[52];
};
#pragma rodata-name(push,"OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0,0,0,
    "SMALLDOS: extract contiguous files (Wilderness)"
};
#pragma rodata-name(pop)
#pragma static-locals(on)

static FILE* in;
static unsigned char po,flip,made,skipped,kept,bad;
static unsigned char catalog[640],back[256];
static char name[16],dest[PATH_LEN+1];
/* DOS logical 15-s -> physical sector -> ProDOS logical sector. */
static const unsigned char po_sector[16]={15,1,2,3,4,5,6,7,8,9,10,11,12,13,14,0};

static unsigned char sector(unsigned int logical)
{
    unsigned char t,s;
    unsigned long off;
    if(logical>=560 || stop())return 0;
    t=logical>>4;s=logical&15;
    if(flip)t=34-t;
    s=po?po_sector[s]:15-s;
    off=((unsigned long)t*16+s)*256;
    return !RF(fseek)(in,off,SEEK_SET) &&
        RF(fread)(buf,1,256,in)==256 && !ferror(in);
}

static unsigned char signature(void)
{
    return buf[0]==6 && !buf[1] && !buf[2] && !buf[3];
}

/* Validate the entire catalogue before CREATE. Unknown/unused entry
 * types are skipped, as in the reference; live entries must be bounded. */
static unsigned char directory(void)
{
    unsigned char i,j,c,n=0;
    unsigned char* e;
    unsigned int start;
    flip=0;
    if(!sector(0))return 0;
    if(!signature()) {
        flip=1;
        if(!sector(0) || !signature())return 0;
    }
    for(i=0;i<4;++i) {
        if(!sector(i))return 0;
        RF(memcpy)(catalog+160*i,buf+96,160);
    }
    for(i=0;i<20;++i) {
        e=catalog+32*i;
        if(e[0]!=0xC1 && e[0]!=0xC2)continue;
        start=(unsigned int)e[2]*16+e[3];
        if(!e[1] || e[2]>=35 || e[3]>=16 || e[4] || start+e[1]>560)return 0;
        n=0;
        for(j=5;j<32;++j) {
            c=e[j]&127;
            if(c<32 || c>126)return 0;
            if(c!=' ')n=1;
        }
        if(!n)return 0;
    }
    return 1;
}

static void set_name(const unsigned char* e)
{
    unsigned char j,k=0,c,end=32;
    while(end>5 && (e[end-1]&127)==' ')--end;
    for(j=5;j<end && k<15;++j) {
        c=e[j]&127;
        if(c>='a' && c<='z')c-=32;
        if(!((c>='A' && c<='Z') || (c>='0' && c<='9') || c=='.'))c='.';
        if(!k && !(c>='A' && c<='Z'))c='X';
        name[k++]=c;
    }
    name[k]=0;
}

static unsigned char pass(const unsigned char* e,FILE* out,unsigned char verify)
{
    unsigned int start=(unsigned int)e[2]*16+e[3];
    unsigned char j;
    if(stop())return 0;
    for(j=0;j<e[1];++j) {
        /* ESC can arrive during the sector read. Stop before writing its
         * bytes or starting read-back; only our exclusive output is owned.
         * The image and AUX remain untouched. */
        if(!sector(start+j) || stop())return 0;
        if(verify) {
            /* ESC during read-back must precede comparison and progress.
             * Only our exclusive output is read; image and AUX stay intact. */
            if(RF(fread)(back,1,256,out)!=256 || ferror(out) || stop() || memcmp(back,buf,256))return 0;
        } else if(RF(fwrite)(buf,1,256,out)!=256 || ferror(out))return 0;
        a.progress_bar(name,j+1,e[1]);
        if(stop())return 0;
    }
    if(verify && (RF(fread)(back,1,1,out) || ferror(out)))return 0;
    return !ferror(in);
}

static unsigned char one(const unsigned char* e)
{
    FILE* out;
    unsigned char ok;
    set_name(e);
    if(!join(dest,other->path,name))return 0;
    /* A = raw tokenized Applesoft; B = raw binary, unknown load address. */
    ok=newfile(dest,e[0]==0xC1?0xFC:6,e[0]==0xC1?0x0801:0,1);
    /* Only duplicate filename ($47) is a skip. Other CREATE errors grant
     * no ownership: stop without opening or deleting this destination. */
    if(ok) {
        if(ok!=0x47)return 0;
        ++skipped;return 1;
    }
    out=RF(fopen)(dest,"wb");
    ok=out!=0 && pass(e,out,0);
    if(out && RF(fclose)(out))ok=0;
    if(stop())ok=0;
    if(ok) {
        out=RF(fopen)(dest,"rb");
        ok=out!=0 && pass(e,out,1);
        if(out && RF(fclose)(out))ok=0;
        if(stop())ok=0;
    }
    if(!ok) { kept=!discard(dest);return 0; }
    ++made;
    return 1;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char i,n;
    unsigned int got;
    unsigned long size=0;
    init(api);made=skipped=kept=bad=0;
    if(pan->fs || !a.full[0] || !a.selected->name[0] || a.selected->type==0x0F ||
       other->fs || !other->path[0]) {
        note("Select SMALLDOS image; ProDOS folder opposite.");return;
    }
    n=RF(strlen)(a.selected->name);
    po=n>3 && !RF(strcmp)(a.selected->name+n-3,".PO");
    if(!po && !(n>3 && !RF(strcmp)(a.selected->name+n-3,".DO")) &&
       !(n>4 && !RF(strcmp)(a.selected->name+n-4,".DSK"))) {
        note("Use a raw .DSK/.DO or .PO image.");return;
    }
    in=RF(fopen)(a.full,"rb");
    if(!in) {note("Cannot open SMALLDOS image.");return;}
    /* Actual length, not stale panel metadata. All reads and seeks use
     * resident streams; no overlay-local descriptor table or AUX. */
    while((got=RF(fread)(buf,1,512,in))!=0) {
        size+=got;
        if(ferror(in) || size>143360UL || stop())break;
    }
    if(ferror(in) || size!=143360UL || stop() || !directory()) {
        RF(fclose)(in);
        note(cancelled?"Stopped: nothing extracted.":"Not a readable SMALLDOS catalogue.");return;
    }
    for(i=0;i<20;++i) {
        unsigned char* e=catalog+32*i;
        if(stop()) {bad=1;break;}
        if(e[0]!=0xC1 && e[0]!=0xC2)continue;
        if(!one(e)) {bad=1;break;}
    }
    if(ferror(in))bad=1;
    if(RF(fclose)(in))bad=1;
    if(stop())bad=1;
    if(kept)return;
    a.sprintf(a.note,"%u extracted, %u skipped%s",made,skipped,
        bad?(cancelled?"; stopped.":"; failed, stopped."):"; sector padding kept.");
}
