/* Private DOS identification source. MEDIA_PLUGIN_MAGIC, OVERLAY_BIG.
 * Validates full allocation, samples 512 logical bytes in MAIN $0E00,
 * closes the source, then loads IDENT through the returned low handoff. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
#include "id_stage.h"
#include "id_context.h"
struct Header {unsigned int signature;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[40];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={MEDIA_PLUGIN_MAGIC, OVERLAY_BIG,plugin_entry,
 {0,0,ID_CPU_TAG},"Internal DOS identification source"};
#pragma rodata-name(pop)
static const struct A2fcApi* A;
#define DS_OTHER_TYPES
#define DS_NO_SEEK
#define DS_DATA_BUFFER (A->copy_buf)
#define DS_MLI A->mli
#define DS_SEEK A->fseek
#define frd A->fread
#define fopn A->fopen
#define fcls A->fclose
static void id_capture(const unsigned char* e){
 unsigned char i;for(i=0;i<30;++i)A->other_full[10+i]=e[3+i]&127;
}
#define DS_CATALOG_ENTRY id_capture
#ifndef PLUGIN_HOST
#define ferror(f) (((unsigned char*)(f))[1]&4)
#endif
#include "dos_source.h"
unsigned char __fastcall__ md_entrypoint(const struct A2fcApi* a){
 unsigned int i;int c;unsigned char* m=(unsigned char*)a->other_full;
 A=a;dv_file=NULL;
#ifndef PLUGIN_HOST
 a->dir_close();
#endif
m[40]=m[41]=0;
 if(!a->selected->name[0] || !dv_open(a->panels+*a->active) || !ds_open(a->selected))goto bad;
 for(i=0;i<512;++i){c=ds_get();if(c<0)break;ID_SAMPLE[i]=c;}
 if(ds_bad || !dv_close())goto bad;
 memset(ID_SAMPLE+i,0,512-i);
 m[0]=i;m[1]=i>>8;
 m[2]=ds_length;m[3]=ds_length>>8;m[4]=ds_length>>16;m[5]=ds_length>>24;
 m[6]=ds_aux;m[7]=ds_aux>>8;m[8]=a->selected->type;m[9]=ds_kind;
 id_context(a,i,ds_length,ds_aux,a->selected->type);
#ifdef PLUGIN_HOST
 return 1;
#else
 if(id_open_stage(a,"IDFORMATS.PLG"))return 1;
#endif
bad:
 dv_close();m[40]=m[41]=0;a->strcpy(a->note,"DOS identification source/stage I/O or structure error.");return 0;
}
