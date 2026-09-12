#define UTIL_VOLUME
#include "util.h"
#include "imageio.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int magic;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[52];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},"Compare volumes or disk images block by block"};
#pragma rodata-name(pop)
static struct Source src,dst;
static unsigned char pair[1024], onlinebuf[256];
/* Exact comparison on one Disk II: two blocks per pair of exchanges. */
static unsigned char mount_source(struct Source* s) {
    struct Online on;unsigned char n,j,k;
    on.n=2;on.buffer=onlinebuf;
    for(;;) {
        on.unit=s->unit;
        if(!a.mli(0xC5,&on)) {
            n=onlinebuf[0]&15;
            for(j=1;j<=n && s->path[j]==onlinebuf[j];++j);
            if(n && j>n && !s->path[j])return 1;
        }
        a.sprintf(a.other_full,"\1Insert %s S6,D%u. 1/2 drive RET ESC",s->path,(s->unit>>7)+1);
        a.message(a.other_full);k=a.cgetc();if(k==KEY_ESC)return 0;
        if(k=='1'||k=='2')src.unit=dst.unit=k=='1'?0x60:0xE0;
    }
}
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
    unsigned char k,ok,request,single,j,count;unsigned int b,i,diff,first;
    init(api);src.file=dst.file=0;
    if(pan->fs || other->fs){note("Use real ProDOS panels.");return;}
    a.message("\1DISKCMP: V Volumes  I Images  S Single drive  ESC Cancel");
    do{k=a.cgetc();if(k==KEY_ESC)return;}while(k!='v'&&k!='V'&&k!='i'&&k!='I'&&k!='s'&&k!='S');single=k=='s'||k=='S';
    if(k=='i'||k=='I') {
        if(!pan->path[0] || !other->path[0] || !a.full[0])goto invalid;
        a.strcpy(src.path,a.full);
        if(!a.prompt("Image in OTHER panel",a.selected->name,0))return;
        if(!join(dst.path,other->path,a.input))goto invalid;
        ok=image_open(&src);if(ok)ok=image_open(&dst);
    }else {
        a.strcpy(src.path,pan->path[0]?pan->path:a.selected->name);
        if(src.path[0]!='/')goto invalid;
        if(!a.prompt("Second volume name (without /)","",0))return;
        dst.path[0]='/';a.strcpy(dst.path+1,a.input);
        request=pan->path[0]?0:(unsigned char)(a.selected->mdate<<4);
        ok=volume_open(&src,request);
        if(single && ok) {
            for(i=1;src.path[i] && src.path[i]!='/';++i);src.path[i]=0;
            if((src.unit&0x70)!=0x60 || !a.strcmp(src.path,dst.path))goto invalid;
            dst.unit=src.unit;
            if(!mount_source(&dst)){note("Comparison cancelled.");goto done;}
            ok=volume_open(&dst,dst.unit);
        }else if(ok)ok=volume_open(&dst,0);
    }
    if(!ok)goto invalid;
    if(src.blocks!=dst.blocks){note("Different sizes: volumes/images are not identical.");goto done;}
    a.clrscr();a.cprintf("DISKCMP - READ ONLY\r\n%s\r\n%s\r\n",src.path,dst.path);
    diff=0;first=65535U;
    for(b=0;b<src.blocks;) {
        a.progress_bar("Comparing (ESC cancels)",b,src.blocks);
        if(stop()){note("Comparison cancelled; no complete verdict.");goto done;}
        count=single && src.blocks-b>1?2:1;
        if(single && !mount_source(&src))goto cancelled;
        for(j=0;j<count;++j)if(!source_read(&src,b+j,pair+512*j))goto readerror;
        if(single && !mount_source(&dst))goto cancelled;
        for(j=0;j<count;++j) {
            if(!source_read(&dst,b,buf))goto readerror;
            for(i=0;i<512 && pair[512*j+i]==buf[i];++i);
            if(i<512){if(!diff)first=b;++diff;}++b;
        }
    }
    if(diff)a.sprintf(a.note,"%u differing blocks; first at %u.",diff,first);
    else a.sprintf(a.note,"Identical: %u blocks compared.",src.blocks);
    goto done;
cancelled:note("Comparison cancelled; no complete verdict.");goto done;
readerror:a.sprintf(a.note,"Read error at block %u; comparison incomplete.",b);goto done;
invalid:note("Cannot compare: select valid volumes or .PO/.DSK/.2MG images.");
done:source_close(&src);source_close(&dst);
}
