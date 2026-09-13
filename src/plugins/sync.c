/* One-way recursive update. Each replacement is copied and verified before
 * the old name is moved aside; a failed install attempts to restore it. */
#define UTIL_STUBS
#define UTIL_INFO
#define UTIL_CREATE
#include "util.h"
#include "dirscan.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int magic;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[52];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},"Copy missing or newer files to the other panel"};
#pragma rodata-name(pop)
struct Frame {unsigned long pos;unsigned int blocks;unsigned char slen,dlen;};
struct Rename {unsigned char n;unsigned char *old,*newpath;};
static struct Frame frames[16];
static struct Info meta;
static struct Rename rn;
/* Readback chunks need only half a block; leave room for error handling
 * without extending the overlay into memory owned by the resident. */
static unsigned char newpas[PATH_LEN+1], check[256];
static char source[PATH_LEN],target[PATH_LEN],tmp[PATH_LEN],bak[PATH_LEN],name[16];
static char sdir[PATH_LEN],ddir[PATH_LEN];
static unsigned int copied,skipped,errors;
static unsigned long size;
static unsigned char depth, recovery;
static unsigned char rename_file(const char* from,const char* to) {
    ppath(from);newpas[0]=RF(strlen)(to);RF(strcpy)((char*)newpas+1,to);
    rn.n=2;rn.old=pas;rn.newpath=newpas;return RF(mli)(0xC2,&rn);
}
#define FI_RENAME rename_file
#include "file_install.h"
/* Stop the tree at the first unresolved recovery operation, so its note is
 * not overwritten by another file or by the ordinary completion summary. */
static void recovery_note(const char* message) {
    recovery=1;note(message);
}
/* Convert ProDOS's 1940..2039 year convention before comparing dates. */
static unsigned char newer(unsigned int sd,unsigned int st,unsigned int dd,unsigned int dt) {
    unsigned int sy,dy;
    if(!sd)return 0;if(!dd)return 1;
    sy=sd>>9;dy=dd>>9;sy=sy<40?sy+60:sy-40;dy=dy<40?dy+60:dy-40;
    if(sy!=dy)return sy>dy;
    sd &= 511;dd &= 511;if(sd!=dd)return sd>dd;
    return st>dt;
}
static unsigned char copy_file(unsigned char exists) {
    FILE *in,*out;unsigned long left;unsigned int n,i;unsigned char error;
    if(!join(tmp,ddir,"A2FC.SYNC") || !join(bak,ddir,"A2FC.BAK"))return 0;
    /* Reserved siblings are never overwritten or removed unless we own them. */
    if(getinfo(bak)!=0x46 || newfile(tmp,meta.type,meta.aux,1))return 0;
    in=RF(fopen)(source,"rb");out=RF(fopen)(tmp,"wb");
    if(!in || !out){if(in)RF(fclose)(in);if(out)RF(fclose)(out);goto fail;}
    left=size;error=0;
    while(left && !error) {
        n=left>sizeof check?sizeof check:(unsigned int)left;
        if(stop() || RF(fread)(buf,1,n,in)!=n || RF(fwrite)(buf,1,n,out)!=n)error=1;
        left-=n;
    }
    if(ferror(in) || ferror(out))error=1;
    if(RF(fclose)(in))error=1;if(RF(fclose)(out))error=1;if(error)goto fail;
    in=RF(fopen)(source,"rb");out=RF(fopen)(tmp,"rb");
    if(!in || !out){if(in)RF(fclose)(in);if(out)RF(fclose)(out);goto fail;}
    left=size;
    while(left && !error) {
        n=left>sizeof check?sizeof check:(unsigned int)left;
        if(stop() || RF(fread)(buf,1,n,in)!=n || RF(fread)(check,1,n,out)!=n)error=1;
        else for(i=0;i<n;++i)if(buf[i]!=check[i]){error=1;break;}
        left-=n;
    }
    /* A matching prefix is not a verified file. A stale directory size or
     * extra output bytes must not replace the destination and its backup. */
    if(!error && (RF(fread)(buf,1,1,in) || RF(fread)(check,1,1,out)))error=1;
    if(ferror(in) || ferror(out))error=1;
    if(RF(fclose)(in))error=1;if(RF(fclose)(out))error=1;if(error)goto fail;
    error=file_install(tmp,target,bak,exists);
    if(error!=FILE_INSTALLED) {
        recovery_note(error==FILE_RESTORE_FAILED ?
            "SYNC stopped: restore failed; A2FC.BAK and A2FC.SYNC kept." :
            "SYNC stopped: install failed; A2FC.SYNC kept.");
        return 0;
    }
    ppath(target);meta.n=7;meta.path=pas;
    if(RF(mli)(0xC3,&meta)) {
        ++errors;recovery_note("SYNC stopped: metadata failed; check output and A2FC.BAK.");return 1;
    }
    if(exists && RF(remove)(bak)) {
        ++errors;recovery_note("SYNC stopped: copied; A2FC.BAK cleanup failed.");
    }
    return 1;
fail:
    if(RF(remove)(tmp))recovery_note("SYNC stopped: cleanup failed; A2FC.SYNC kept.");
    return 0;
}
static unsigned char overlap(const char* x,const char* y) {
    unsigned char i;for(i=0;x[i] && x[i]==y[i];++i);
    return !x[i] && (!y[i] || y[i]=='/');
}
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
    unsigned char r,exists;struct Frame* f;
    init(api);dir_reset();copied=skipped=errors=depth=recovery=0;
    if(pan->fs || other->fs || !pan->path[0] || !other->path[0] ||
       overlap(pan->path,other->path) || overlap(other->path,pan->path)) {
        note("SYNC needs distinct, non-nested ProDOS directories.");return;
    }
    RF(strcpy)(sdir,pan->path);RF(strcpy)(ddir,other->path);
    a.clrscr();a.cprintf("SYNC - ONE WAY\r\nSOURCE: %s\r\nDESTINATION: %s\r\n",sdir,ddir);
    if(!RF(confirm)("Copy missing/newer files, replacing older destination files?"))return;
    if(!dir_begin(sdir,&frames[0].blocks)){note("Cannot read source directory.");return;}
    frames[0].pos=0;frames[0].slen=RF(strlen)(sdir);frames[0].dlen=RF(strlen)(ddir);
    for(;;) {
        if(stop())break;f=&frames[depth];r=dir_next(sdir,f->blocks,&f->pos);
        if(r==2){++errors;r=0;}
        if(!r){if(!depth)break;--depth;sdir[frames[depth].slen]=ddir[frames[depth].dlen]=0;continue;}
        rawname(name);
        if(!RF(strcmp)(name,"A2FC.SYNC") || !RF(strcmp)(name,"A2FC.BAK")){++skipped;continue;}
        if(!join(source,sdir,name)||!join(target,ddir,name)){++errors;continue;}
        r=getinfo(target);exists=r==0;
        if(r && r!=0x46){++errors;continue;}
        if((raw[0]>>4)==13) {
            if(depth==15 || (exists && info.storage!=13) || (!exists && newfile(target,15,0,13)) ||
               !dir_begin(source,&frames[depth+1].blocks)){++errors;continue;}
            ++depth;RF(strcpy)(sdir,source);RF(strcpy)(ddir,target);
            frames[depth].slen=RF(strlen)(sdir);frames[depth].dlen=RF(strlen)(ddir);frames[depth].pos=0;continue;
        }
        if((raw[0]>>4)>3 || (exists && (info.storage>3 || !(info.access&0x80)))){++errors;continue;}
        if(exists && !newer(rd16(raw+33),rd16(raw+35),info.mdate,info.mtime)){++skipped;continue;}
        meta.access=raw[30];meta.type=raw[16];meta.aux=rd16(raw+31);meta.storage=raw[0]>>4;
        meta.blocks=rd16(raw+19);meta.mdate=rd16(raw+33);meta.mtime=rd16(raw+35);
        meta.cdate=rd16(raw+24);meta.ctime=rd16(raw+26);size=rd24(raw+21);
        RF(message)(source);
        if(copy_file(exists))++copied;else ++errors;
        if(recovery)return;
    }
    a.sprintf(a.note,"SYNC%s: %u copied, %u skipped, %u errors. Backups: A2FC.BAK.",cancelled?" cancelled":"",copied,skipped,errors);
}
