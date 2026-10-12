#define UTIL_VOLUME
#define IMAGEIO_CHECK_CLOSE
#define IMAGEIO_CHECK_STREAM
#include "util.h"
#include "imageio.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int magic;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[52];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},"Compare volumes or disk images block by block"};
#pragma rodata-name(pop)
static struct Source src,dst;
static unsigned char pair[1024], onlinebuf[256];
static unsigned char mount_error;
/* Comparison only reads its two sources; no disk or AUX memory writes.
 * A complete byte count cannot establish a verdict on an errored stream. */
static unsigned char compare_read(struct Source* s,unsigned int b,unsigned char* out) {
    return source_read(s,b,out) && (!s->file || !ferror(s->file));
}
/* Raw PO/DO images end exactly after their blocks. Directory sizes can be
 * stale: check the stream itself. A 2MG container may have trailing chunks;
 * its header bounds the disk payload independently of those chunks. */
static unsigned char compare_end(struct Source* s) {
    if(!s->file || s->kind==2)return 1;
    return !a.fseek(s->file,(unsigned long)s->blocks*512,SEEK_SET) &&
           !a.fread(buf,1,1,s->file) && !ferror(s->file);
}
static unsigned char compare_close(struct Source* s) {
    unsigned char ok=1;
    if(s->file) {
        if(ferror(s->file))ok=0;
        if(a.fclose(s->file))ok=0;
        s->file=0;
    }
    return ok;
}
/* Exact comparison on one Disk II: two blocks per pair of exchanges. */
static unsigned char mount_source(struct Source* s) {
    struct Online on;unsigned char n,j,k;
    on.n=2;on.buffer=onlinebuf;
    for(;;) {
        on.unit=s->unit;
        if(!a.mli(0xC5,&on)) {
            n=onlinebuf[0]&15;
            for(j=1;j<=n && s->path[j]==onlinebuf[j];++j);
            if(n && j>n && !s->path[j]) {
                /* Once opened, revalidate each inserted disk before using
                 * the saved block count. buf is free; source pairs live in pair.
                 * Initial destination mounting precedes its volume_open. */
                if(s->blocks && (readblk(s->unit,2,buf) || (buf[4]>>4)!=15 ||
                   rd16(buf+41)!=s->blocks)) {mount_error=1;return 0;}
                return 1;
            }
        }
        a.sprintf(a.other_full,"\1Insert %s S6,D%u. 1/2 drive RET ESC",s->path,(s->unit>>7)+1);
        a.message(a.other_full);k=a.cgetc();if(k==KEY_ESC)return 0;
        if(k=='1'||k=='2')src.unit=dst.unit=k=='1'?0x60:0xE0;
    }
}
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
    unsigned char k,ok,request,single,j,count;unsigned int b,i,diff,first;
    init(api);src.file=dst.file=0;dst.blocks=0;mount_error=0;
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
        /* Two drives with that name: unit_of refuses a path it cannot tie
         * to one drive. A comparison only reads, and it is symmetrical: take
         * the first drive of the name, the other is found below. */
        /* A resolved unit with a bad/unreadable header is not absent.
         * Never skip it in favour of a different disk with the same name. */
        if(!ok && !request && !src.unit)for(j=0x10;j && !ok;j+=0x10) {
            ok=volume_open(&src,j);if(src.unit)break;
        }
        if(single && ok) {
            for(i=1;src.path[i] && src.path[i]!='/';++i);src.path[i]=0;
            if((src.unit&0x70)!=0x60 || !a.strcmp(src.path,dst.path))goto invalid;
            dst.unit=src.unit;
            if(!mount_source(&dst))goto cancelled;
            ok=volume_open(&dst,dst.unit);
        }else if(ok) {
            ok=volume_open(&dst,0);
            /* An original and its backup may share one name: the first unit
             * with it may be the source itself, so take another unit with
             * that name, or refuse -- a volume is never compared with itself. */
            if((!ok && !dst.unit) || (ok && dst.unit==src.unit))
                for(ok=0,j=0x10;j && !ok;j+=0x10)if(j!=src.unit) {
                    ok=volume_open(&dst,j);if(dst.unit)break;
                }
        }
    }
    if(!ok)goto invalid;
    if(src.blocks!=dst.blocks){note("Different sizes: volumes/images are not identical.");goto done;}
    a.clrscr();a.cprintf("DISKCMP - READ ONLY\r\n%s\r\n%s\r\n",src.path,dst.path);
    diff=0;first=65535U;
    for(b=0;b<src.blocks;) {
        a.progress_bar("Compare (ESC)",b,src.blocks);
        if(stop()){note("Comparison cancelled; no complete verdict.");goto done;}
        count=single && src.blocks-b>1?2:1;
        if(single && !mount_source(&src))goto cancelled;
        for(j=0;j<count;++j)if(!compare_read(&src,b+j,pair+512*j))goto readerror;
        if(single && !mount_source(&dst))goto cancelled;
        for(j=0;j<count;++j) {
            if(!compare_read(&dst,b,buf))goto readerror;
            for(i=0;i<512 && pair[512*j+i]==buf[i];++i);
            if(i<512){if(!diff)first=b;++diff;}++b;
        }
    }
    if(!compare_end(&src) || !compare_end(&dst)) {
        note("Image size/read error; comparison incomplete.");goto done;
    }
    /* ESC during the last block or EOF probe is still an interruption.
     * Comparison only reads sources and MAIN; disks and AUX stay intact. */
    if(stop())goto cancelled;
    if(diff)a.sprintf(a.note,"%u differing blocks; first at %u.",diff,first);
    else a.sprintf(a.note,"Identical: %u blocks compared.",src.blocks);
    goto done;
cancelled:note(mount_error ? "Disk changed/read error; comparison incomplete." :
               "Comparison cancelled; no complete verdict.");goto done;
readerror:a.sprintf(a.note,"Read error at block %u; comparison incomplete.",b);goto done;
invalid:note("Cannot compare: select valid volumes or .PO/.DSK/.2MG images.");
done:ok=compare_close(&src);
    if(!compare_close(&dst))ok=0;
    if(!ok)note("Stream error; comparison incomplete.");
    /* Closing may take time too. Always close both sources, then refuse
     * any complete verdict if ESC arrived during either close. */
    else if(stop())note("Comparison cancelled; no complete verdict.");
}
