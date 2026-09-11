/* Shared service-overlay helpers. No resident addresses or writable source disks. */
#include "../a2fc_plugin.h"
#if defined(UTIL_FIXED_API) && !defined(PLUGIN_HOST)
#define a (*(struct A2fcApi*)0x3F9E)
#else
static struct A2fcApi a;
#endif
static unsigned char* buf;
static unsigned char cancelled;
static struct Panel *pan, *other;
static unsigned int rd16(const unsigned char* p) { return p[0] | ((unsigned int)p[1]<<8); }
static unsigned long rd24(const unsigned char* p) { return rd16(p) | ((unsigned long)p[2]<<16); }
static void wr16(unsigned char* p, unsigned int v) { p[0]=v; p[1]=v>>8; }
static void init(const struct A2fcApi* api) {
    api->memcpy(&a,api,sizeof a); buf=a.copy_buf; cancelled=0;
    pan=a.panels+*a.active; other=a.panels+!(*a.active);
}
static void note(const char* s) { a.strcpy(a.note,s); }
static unsigned char stop(void) {
#ifndef PLUGIN_HOST
    if (*(volatile unsigned char*)0xC000 == (KEY_ESC|0x80)) {
        (void)*(volatile unsigned char*)0xC010; cancelled=1;
    }
#endif
    return cancelled;
}
static unsigned char join(char* out,const char* dir,const char* name) {
    unsigned int n=a.strlen(dir), m=a.strlen(name);
    if (!n || n+m+1>=PATH_LEN) return 0;
    a.memcpy(out,dir,n); out[n]='/'; a.strcpy(out+n+1,name); return 1;
}
static unsigned char pas[PATH_LEN+1];
static void ppath(const char* p) { pas[0]=a.strlen(p); a.strcpy((char*)pas+1,p); }
#ifdef UTIL_INFO
struct Info { unsigned char n; unsigned char* path; unsigned char access,type;
    unsigned int aux; unsigned char storage; unsigned int blocks,mdate,mtime,cdate,ctime; };
static struct Info info;
static unsigned char getinfo(const char* path) {
    ppath(path); info.n=10; info.path=pas; return a.mli(0xC4,&info);
}
#endif
#ifdef UTIL_CREATE
struct Create { unsigned char n; unsigned char* path; unsigned char access,type;
    unsigned int aux; unsigned char storage; unsigned int date,time; };
static struct Create create;
static unsigned char newfile(const char* path,unsigned char type,unsigned int aux,unsigned char storage) {
    ppath(path); create.n=7; create.path=pas; create.access=0xC3; create.type=type;
    create.aux=aux; create.storage=storage; create.date=create.time=0;
    return a.mli(0xC0,&create);
}
#endif
#ifdef UTIL_VOLUME
struct Block { unsigned char n,unit; unsigned char* buffer; unsigned int block; };
struct Online { unsigned char n,unit; unsigned char* buffer; };
static struct Block bio;
static struct Online online;
static unsigned char unit_of(const char* path,unsigned char requested) {
    unsigned int i; unsigned char n,j;
    for(n=1;path[n] && path[n]!='/';++n) if(n==16)return 0;
    online.n=2;online.unit=0;online.buffer=buf;
    if(a.mli(0xC5,&online))return 0;
    for(i=0;i<256;i+=16) {
        if((buf[i]&15)!=n-1 || (requested && (buf[i]&0xF0)!=requested))continue;
        for(j=1;j<n && path[j]==buf[i+j];++j);
        if(j==n)return buf[i]&0xF0;
    }
    return 0;
}
static unsigned char readblk(unsigned char unit,unsigned int b,unsigned char* out) {
    bio.n=3;bio.unit=unit;bio.buffer=out;bio.block=b;return a.mli(0x80,&bio);
}
#ifdef UTIL_WRITE
/* WRITE_BLOCK. Behind its own guard: an overlay that only reads must not
 * carry the call that writes. */
static unsigned char writeblk(unsigned char unit,unsigned int b,const unsigned char* in) {
    bio.n=3;bio.unit=unit;bio.buffer=(unsigned char*)in;bio.block=b;return a.mli(0x81,&bio);
}
#endif
#endif
