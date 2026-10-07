/* Shared service-overlay helpers. No resident addresses or writable source disks. */
#include "../a2fc_plugin.h"
#include <stddef.h>
#if defined(UTIL_FIXED_API) && !defined(PLUGIN_HOST)
#define a (*(struct A2fcApi*)0x3F9E)
#define UTIL_API_COPY offsetof(struct A2fcApi,ram_format)
#elif !defined(PLUGIN_HOST)
/* The copy stops before the v6 services (aux_consent and later): a util.h
 * overlay does not use them, and its BSS keeps the size it had under v5.
 * One that needs them reads them through the api pointer. */
#define UTIL_API_COPY offsetof(struct A2fcApi,aux_consent)
static unsigned char util_api[UTIL_API_COPY];
#define a (*(struct A2fcApi*)util_api)
#define UTIL_API_SYM util_api
#else
static struct A2fcApi a;
#define UTIL_API_COPY sizeof a
#endif
#ifndef UTIL_API_SYM
#define UTIL_API_SYM a
#endif
#ifdef UTIL_STUBS
#define SERVICE_API UTIL_API_SYM
#include "service_stubs.h"
#endif
#ifndef RF
#define RF(name) a.name
#endif
static unsigned char* buf;
static unsigned char cancelled;
static struct Panel *pan, *other;
static unsigned int rd16(const unsigned char* p) { return p[0] | ((unsigned int)p[1]<<8); }
static unsigned long rd24(const unsigned char* p) { return rd16(p) | ((unsigned long)p[2]<<16); }
static void wr16(unsigned char* p, unsigned int v) { p[0]=v; p[1]=v>>8; }
static void init(const struct A2fcApi* api) {
    /* UTIL_FIXED_API: up to cfg_path, at $3F9E the fields after it would
     * land on the resident at $4000, and no util.h overlay reads them. */
    api->memcpy(&a,api,UTIL_API_COPY);
    buf=a.copy_buf; cancelled=0;
    pan=a.panels+*a.active; other=a.panels+!(*a.active);
}
static void note(const char* s) { RF(strcpy)(a.note,s); }
static unsigned char stop(void) {
#ifndef PLUGIN_HOST
    if (*(volatile unsigned char*)0xC000 == (KEY_ESC|0x80)) {
        *(volatile unsigned char*)0xC010 = 0; cancelled=1;
    }
#endif
    return cancelled;
}
static unsigned char join(char* out,const char* dir,const char* name) {
    unsigned int n=RF(strlen)(dir), m=RF(strlen)(name);
    if (!n || n+m+1>=PATH_LEN) return 0;
    RF(memcpy)(out,dir,n); out[n]='/'; RF(strcpy)(out+n+1,name); return 1;
}
#if defined(UTIL_INFO) || defined(UTIL_CREATE)
static unsigned char pas[PATH_LEN+1];
static void ppath(const char* p) { pas[0]=RF(strlen)(p); RF(strcpy)((char*)pas+1,p); }
#endif
#ifdef UTIL_INFO
struct Info { unsigned char n; unsigned char* path; unsigned char access,type;
    unsigned int aux; unsigned char storage; unsigned int blocks,mdate,mtime,cdate,ctime; };
static struct Info info;
static unsigned char getinfo(const char* path) {
    ppath(path); info.n=10; info.path=pas; return RF(mli)(0xC4,&info);
}
#endif
#ifdef UTIL_CREATE
#define FC_PATH pas
#define FC_PREPARE(path) ppath(path)
#include "file_create.h"
#endif
#ifdef UTIL_DISCARD
/* Removes an entry this run created and still owns (newfile returned zero).
 * On failure the note says the incomplete file stays and nothing may call
 * it removed: the caller stops, and a retry's exclusive creation cannot
 * touch it. The name is the one the user just gave or saw. 1: it is gone. */
static unsigned char discard(const char* path) {
    if (!RF(remove)(path)) return 1;
    note("Cleanup failed: the incomplete file stays.");
    return 0;
}
#endif
#ifdef UTIL_VOLUME
struct Block { unsigned char n,unit; unsigned char* buffer; unsigned int block; };
struct Online { unsigned char n,unit; unsigned char* buffer; };
static struct Block bio;
static struct Online online;
/* The unit (DSSS0000) of the volume that starts `path`, from ON_LINE on
 * unit 0; `requested`, when not 0, keeps only that unit's record. 0: not
 * on line, or not one volume. The table ends at the first record whose
 * byte 0 is zero: what lies after it is stale copy_buf, not a drive. Two
 * records with the name: ProDOS resolves the path to one of them and the
 * caller would read or write the other by unit, so the answer is 0 and the
 * note says why (a volume-list row is opened by its unit, which works). */
static unsigned char unit_of(const char* path,unsigned char requested) {
    static unsigned char *p,n,j,u,k;
    for(n=1;(j=path[n])!=0 && j!='/';++n) if(n==16)return 0;
    online.n=2;online.unit=0;online.buffer=buf;
    if(RF(mli)(0xC5,&online))return 0;
    u=0;p=buf;k=16;
    do {
        if(!(j=*p))break;
        if((unsigned char)((j&15)+1)==n && (!requested || (j&0xF0)==requested)) {
            for(j=1;j<n && path[j]==p[j];++j);
            if(j==n) {
                if(u) {
#ifdef UTIL_TWIN
                    RF(sprintf)(a.note,"Two volumes named %.*s: pick it in the volume list.",n,path);
#endif
                    return 0;
                }
                u=*p&0xF0;
            }
        }
        p+=16;
    } while(--k);
    return u;
}
static unsigned char readblk(unsigned char unit,unsigned int b,unsigned char* out) {
    bio.n=3;bio.unit=unit;bio.buffer=out;bio.block=b;return RF(mli)(0x80,&bio);
}
#ifdef UTIL_WRITE
/* WRITE_BLOCK. Behind its own guard: an overlay that only reads must not
 * carry the call that writes. */
static unsigned char writeblk(unsigned char unit,unsigned int b,const unsigned char* in) {
    bio.n=3;bio.unit=unit;bio.buffer=(unsigned char*)in;bio.block=b;return RF(mli)(0x81,&bio);
}
#endif
#endif
