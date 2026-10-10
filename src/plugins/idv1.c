/* Internal format detection; source closed, sample in MAIN $0E00-$0FFF.
 * MEDIA_PLUGIN_MAGIC, OVERLAY_BIG. No source writes or AUX. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
#include "id_stage.h"
#include "id_context.h"
/* All 1.0 readers in this relay consume ProDOS files. DOS candidates keep
 * the read-only DOS text fallback; no generic routing table is needed here. */
static void id_finish(const struct A2fcApi* a,const struct Entry* e,const char* what,const char* reader,unsigned char dos){
 if(a->arg=='O' || a->arg=='I' || a->arg==13){if(dos)reader="DOSVIEW";a->strcpy(a->input,reader);return;}
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
static const struct Entry* e;
static unsigned char* b;
static unsigned int n;
static unsigned char id_dos;
static const char* reader;
static union {unsigned long l;unsigned int w[2];} sz;
static unsigned char suffix(const char* name,const char* end){unsigned int n=strlen(name),k=strlen(end);return n>k && !strcmp(name+n-k,end);}
#include "id_v1.h"
unsigned char __fastcall__ md_entrypoint(const struct A2fcApi* a){
 const char* what;unsigned char* m=(unsigned char*)a->other_full;
 reader=NULL;e=&actual;b=ID_SAMPLE;id_dos=a->panels[*a->active].fs==FS_DOS33;
 if(!id_restore(a,&actual,&n))goto failed;
 sz.l=e->size;
 if(m[42])goto failed;what=extra_v1();
 if(what){m[40]=m[41]=0;id_finish(a,e,what,reader,id_dos);return 0;}
 m[42]=3;
#ifdef PLUGIN_HOST
 return 1;
#else
 if(id_open_stage(a,"IDFORMATS.PLG"))return 1;
#endif
failed:
 m[40]=m[41]=0;a->strcpy(a->note,"Invalid identification context/stage.");return 0;
}
