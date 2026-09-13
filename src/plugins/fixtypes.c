/* Attribute repair from explicit suffixes and validated Duet content.
 * API v5 supplies an immutable entry snapshot at $3000. Code and BSS are
 * linked below it. Only confirmed metadata/rename operations write a disk;
 * content is read-only, no AUX, and every metadata lookup must succeed. */
#include "../a2fc_plugin.h"
#include <string.h>
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header { unsigned int magic; unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3]; char desc[48]; };
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},
 "Review and repair file types; marked or selected"};
#pragma rodata-name(pop)
struct Rule { char suffix[8]; unsigned char type; unsigned int aux; unsigned char keep; };
static const struct Rule rules[]={
 {".SYSTEM",255,0x2000,1},{".PO",6,0,1},{".DSK",6,0,1},{".DO",6,0,1},
 {".2MG",6,0,1},{".HDV",6,0,1},{".ED",0xD5,0xD0E7,1},{".PT3",6,0,1},
 {".SHK",0xE0,0x8002,0},{".SDK",0xE0,0x8002,0},{".BXY",0xE0,0x8000,0},
 {".BNY",0xE0,0x8000,0},{".AWP",0x1A,0,0},{".ADB",0x19,0,0},{".ASP",0x1B,0,0},
 {".BAS",0xFC,0x0801,0},{".SYS",255,0x2000,0},{".TXT",4,0,0},{".MD",4,0,1},
 {".CSV",4,0,0},{".BIN",6,0,0},{".MB",6,0,1},{".PIC",6,0x2000,0},
 {".HGR",6,0x2000,0},{".DHR",6,0x2000,0}
};
struct Info { unsigned char n; unsigned char* path; unsigned char access,type;
 unsigned int aux; unsigned char storage; unsigned int blocks,mdate,mtime,cdate,ctime; };
struct Rename { unsigned char n; unsigned char* old; unsigned char* dest; };
static const struct A2fcApi* A;
static struct Info info, before;
static struct Rename rn;
static char path[PATH_LEN], question[80];
static unsigned char pas[PATH_LEN+1], dest[PATH_LEN+1];
static unsigned char type, keep, cut, entry_index, tagged_any;
static unsigned int aux, typed, renamed, skipped, failed;
static const struct Entry* e;
static const struct Panel* pan;
#define DP_READ A->fread
#include "../duet_probe.h"
static unsigned char getinfo(void) {
 info.n=10;info.path=pas;return A->mli(0xC4,&info);
}
static unsigned char same(void) {
 return info.access==before.access && info.type==before.type && info.aux==before.aux &&
  info.storage==before.storage && info.blocks==before.blocks &&
  info.mdate==before.mdate && info.mtime==before.mtime &&
  info.cdate==before.cdate && info.ctime==before.ctime;
}
/* 0 no proposal, 1 proposal, 2 read/close failure or invalid explicit Duet. */
static unsigned char propose(void) {
 unsigned char r,n,len,duet=0;
 FILE* f;
 type=info.type;aux=info.aux;keep=1;cut=0;
 n=A->strlen(e->name);
 for(r=0;r<sizeof rules/sizeof rules[0];++r) {
  len=A->strlen(rules[r].suffix);
  if(n>len && !A->strcmp(e->name+n-len,rules[r].suffix)) {
   type=rules[r].type;aux=rules[r].aux;keep=rules[r].keep;cut=len;
   /* A generic BIN suffix must not erase a DOS load address. */
   if(type==6 && !aux)aux=info.aux;
   if(type==0xD5)duet=1;
   break;
  }
 }
 if(duet || (info.type==6 && e->name[0]=='M' && e->name[1]=='.') ||
    (info.type==0xD5 && info.aux==0xD0E7)) {
  f=A->fopen(path,"rb");if(!f)return 2;
  r=duet_probe(f,A->copy_buf);
  if(ferror(f))r=2;
  if(A->fclose(f))r=2;
  if(r!=1)return 2;
  type=0xD5;aux=0xD0E7;keep=1;return 1;
 }
 return cut!=0;
}
static void one(void) {
 unsigned char r;
 if(e->type==15 || !A->build_full(path,pan,e)) {++skipped;return;}
 pas[0]=A->strlen(path);A->strcpy((char*)pas+1,path);
 if(getinfo()) {++failed;return;}
 if(info.storage<1 || info.storage>3 || !(info.access&2)) {++skipped;return;}
 before=info;
 r=propose();
 if(r!=1) {if(r==2)++failed;else ++skipped;return;}
 if(type==info.type && aux==info.aux) {++skipped;return;}
 A->sprintf(question,"%s: $%02X/$%04X -> $%02X/$%04X?",e->name,info.type,info.aux,type,aux);
 if(!A->confirm(question)) {++skipped;return;}
 /* No stale panel metadata, or changed disk after the question, may be used
  * for SET_FILE_INFO. This also preserves access bits and all timestamps. */
 if(getinfo() || !same()) {++failed;return;}
 info.n=7;info.type=type;info.aux=aux;
 if(A->mli(0xC3,&info)) {++failed;return;}
 if(getinfo() || info.type!=type || info.aux!=aux || info.access!=before.access) {++failed;return;}
 ++typed;
 if(keep || !cut || !(info.access&0x40))return;
 A->sprintf(question,"%s: drop suffix?",e->name);
 if(!A->confirm(question))return;
 before=info;
 if(getinfo() || !same()) {++failed;return;}
 dest[0]=pas[0]-cut;A->memcpy(dest+1,pas+1,dest[0]);
 /* GET_FILE_INFO must positively report absence; any other error refuses. */
 info.path=dest;info.n=10;
 if(A->mli(0xC4,&info)!=0x46) {++failed;return;}
 rn.n=2;rn.old=pas;rn.dest=dest;
 if(A->mli(0xC2,&rn)) {++failed;return;}
 ++renamed;
}
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
 A=api;
 if(A->version<5) {A->strcpy(A->note,"FIXTYPES needs A2FC API v5.");return;}
 pan=A->panels+*A->active;
 if(!pan->path[0] || pan->fs || pan->count>MAX_ENTRIES) {A->strcpy(A->note,"Open a ProDOS directory.");return;}
 typed=renamed=skipped=failed=tagged_any=0;
 for(entry_index=0;entry_index<sizeof pan->tags;++entry_index)tagged_any|=pan->tags[entry_index];
 for(entry_index=0;entry_index<pan->count;++entry_index) {
  if(tagged_any ? !(pan->tags[entry_index>>3]&(1U<<(entry_index&7))) : entry_index!=pan->cursor)continue;
  e=&ENTRY_SNAPSHOT[entry_index];one();
 }
 A->sprintf(A->note,"%u typed, %u renamed, %u skipped, %u failed",typed,renamed,skipped,failed);
 A->strcpy(A->reselect,A->selected->name);
}
