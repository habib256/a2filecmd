/* Internal format detection; source closed, sample in MAIN $0E00-$0FFF.
 * MEDIA_PLUGIN_MAGIC, OVERLAY_BIG. No source writes or AUX. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
#include "id_stage.h"
#include "id_context.h"
/* Explicit read-only DOS readers; other candidates keep the generic fallback. */
static void id_finish(const struct A2fcApi* a,const struct Entry* e,const char* what,const char* reader,unsigned char dos){
 if(a->arg=='O' || a->arg=='I' || a->arg==13){
  if(dos && strcmp(reader,"LISAV2") && strcmp(reader,"DOSFONT") &&
     strcmp(reader,"MERLIN") && strcmp(reader,"MAGWIN") && strcmp(reader,"PSFONT"))reader="DOSVIEW";
  a->strcpy(a->input,reader);return;
 }
 a->sprintf((char*)a->copy_buf,"%s (%lu bytes): %s",e->name,e->size,what);
 a->copy_buf[79]=0;a->strcpy(a->note,(char*)a->copy_buf);
}
struct Header {unsigned int signature;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[40];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={MEDIA_PLUGIN_MAGIC, OVERLAY_BIG,plugin_entry,
 {0,0,ID_CPU_TAG},"Internal 1.0 format detector"};
#pragma rodata-name(pop)
static struct Entry actual;
/* The entry is always the restored copy: a fixed address, not a pointer. */
#define e (&actual)
static unsigned char* b;
static unsigned int n;
static unsigned char id_dos;
static const char* reader;
static union {unsigned long l;unsigned int w[2];} sz;
static unsigned char suffix(const char* name,const char* end){unsigned char n=strlen(name),k=strlen(end);return n>k && !strcmp(name+n-k,end);}
#include "id_v1.h"
/* IDREAD retained the complete catalog name, stripped of high bits, at
 * context[10..39]. It is space padded, not NUL terminated. Never inspect
 * the following context bytes as part of the name. Display names can
 * truncate a suffix or replace spaces/punctuation; they remain the entry
 * identity used by the reader, together with the fresh T/S key. */
static unsigned char dos_suffix(const unsigned char* name,const char* end){
 unsigned char len=30,k=strlen(end),i,c;
 while(len && name[len-1]==' ')--len;
 if(len<=k)return 0;
 for(i=0;i<k;++i){
  c=name[(unsigned int)len-k+i];if(c>='a' && c<='z')c-=32;
  if(c!=(unsigned char)end[i])return 0;
 }
 return 1;
}
#include "id_merlin.h"
#include "id_psfont.h"
static const char* dos_named(const unsigned char* name){
 const char* what=psfont_content();if(what)return what;
 if(!id_dos)return merlin_content();
 if(e->type==6 && (sz.l==768 || sz.l==1024) &&
    (dos_suffix(name,".SET") || dos_suffix(name,".FONT"))){
  reader="DOSFONT";return "HRCG hi-res font";
 }
 if(e->type==6 && n>=256 && b[0]==0x8D && b[2]>=32 && dos_suffix(name,".MW")){
  reader="MAGWIN";return "Magic Window?";
 }
 if(e->type==4 && n && b[0]>=128 &&
    (dos_suffix(name,".ASM") || dos_suffix(name,".S"))){
  reader="MERLIN";return "Merlin assembler source?";
 }
 return merlin_content();
}
unsigned char __fastcall__ md_entrypoint(const struct A2fcApi* a){
 const char* what;const char* next;unsigned char* m=(unsigned char*)a->other_full;
 reader=NULL;b=ID_SAMPLE;id_dos=a->panels[*a->active].fs==FS_DOS33;
 if(!id_restore(a,&actual,&n))goto failed;
 sz.l=e->size;
 if(m[42]==4){
  what=dos_named(m+10);m[42]=1;next="IDENT.PLG";
  /* Return runs a ProDOS BAS or INT (RUN asks first) that no source
   * format has claimed: IDFORMATS found no S-C or LISA, nor this Merlin. */
  if(!what && a->arg=='O' && !id_dos && (actual.type==0xFC || actual.type==0xFA))what=reader="RUN";
 }else {
  if(m[42])goto failed;
  /* Return on a ProDOS SYS runs it (RUN asks first); I still reads it.
   * BAS and INT wait for the source formats: see the second visit. */
  if(a->arg=='O' && !id_dos && actual.type==0xFF)what=reader="RUN";
  else what=extra_v1();
  m[42]=3;next="IDFORMATS.PLG";
 }
 if(what){m[40]=m[41]=0;id_finish(a,e,what,reader,id_dos);return 0;}
#ifdef PLUGIN_HOST
 return 1;
#else
 if(id_open_stage(a,next))return 1;
#endif
failed:
 m[40]=m[41]=0;a->strcpy(a->note,"Invalid identification context/stage.");return 0;
}
