/* Direct read-only DOS MCS importer. MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUDIO.
 * Only MAIN overlay/BSS, canonical song $3700-$3FFF, copy_buf and the
 * handoff at $0C00 are written. Close the DOS image before opening the
 * single sequencer file; never have two ProDOS FILE buffers live. No AUX. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int signature;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[38];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUDIO,
 plugin_entry,{0,0,0},"DOS 3.3 MCS editor scores and exports"};
#pragma rodata-name(pop)
#define STAFF_SIZE 1152
#define LIMIT 2304
#ifdef PLUGIN_HOST
extern unsigned char host_song[LIMIT];
#define SONG_BUFFER host_song
#else
#define SONG_BUFFER ((unsigned char*)0x3700)
#endif
#ifdef A2FC_6502
const unsigned char md_cpu_tag=1;
#else
const unsigned char md_cpu_tag=129;
#endif
FILE* md_player;
static unsigned char* SONG;
static const struct A2fcApi* A;
#include "hgr_io.h"
/* The handoff's resident callback offsets are verified in native tests. */
const unsigned char md_api_offsets[]={offsetof(struct A2fcApi,fread),
 offsetof(struct A2fcApi,fclose),offsetof(struct A2fcApi,note)};
#define MC_VALID_NO_END
#include "mcs_valid.h"
static unsigned char md_raw[30];
static void md_capture(const unsigned char* e){unsigned char i;for(i=0;i<30;++i)md_raw[i]=e[i+3]&127;}
#define DS_CATALOG_ENTRY md_capture
#define DS_SECTORS 13
#define DS_POSITION unsigned int
#define DS_NO_SEEK
#define DS_BINARY_ONLY
#define DS_DATA_BUFFER (A->copy_buf)
#ifndef PLUGIN_HOST
#pragma optimize(push,off)
#pragma warn(unused-param,push,off)
static unsigned char __fastcall__ md_mli(unsigned char cmd,void* p) STUB(mli)
static int __fastcall__ md_seek(FILE* f,long at,int whence) STUB(fseek)
#pragma warn(unused-param,pop)
#pragma optimize(pop)
#define DS_MLI md_mli
#define DS_SEEK md_seek
#else
#define DS_MLI A->mli
#define DS_SEEK A->fseek
#endif
#include "dos_source.h"
static struct Entry md_entry;
static unsigned char md_name[30],md_length;
/* Full DOS names, not the panel's truncated/normalised display name.
 * Scan the entire fresh catalog: duplicates or errors cannot prove a pair. */
static unsigned char md_find(void){
 unsigned char t,s,ct,cs,j,i,found=0;const unsigned char* e;
 memset(ds_seen,0,sizeof ds_seen);
 if(!sector_read(17,0,ds_ts))return 0;
 ds_claim(17,0);t=ds_ts[1];s=ds_ts[2];
 while(t){
  if(!ds_claim(t,s)||!sector_read(t,s,ds_ts))return 0;
  ct=ds_ts[1];cs=ds_ts[2];if((!ct&&cs)||(ct&&!ds_pair(ct,cs)))return 0;
  for(j=0;j<7;++j){
   e=ds_ts+11+(unsigned int)j*35;if(!e[0]){ct=0;break;}if(e[0]==255)continue;
   for(i=0;i<30 && (e[i+3]&127)==md_name[i];++i);
   if(i!=30)continue;
   if(++found!=1 || (e[2]&127)!=4)return 0;
   md_entry.mdate=((unsigned int)e[0]<<8)|e[1];md_entry.type=6;ds_name(e+3,md_entry.name);
  }
  t=ct;s=cs;
 }
 return found==1&&ds_open(&md_entry);
}
/* The assembly wrapper calls this, and returns here only before loading
 * the player. A failed source or close never reaches the hardware driver. */
unsigned char __fastcall__ md_entrypoint(const struct A2fcApi* a){
 unsigned int i,j,main_key;unsigned char ok=0,score=0;int c;
 unsigned char* context=(unsigned char*)a->other_full;
 A=a;SONG=SONG_BUFFER;dv_file=NULL;
#ifndef PLUGIN_HOST
 A->dir_close();
#endif

 if(!A->arg||A->arg>7||A->arg==3){scpy(A->note,"No Mockingboard.");return 0;}
 if(!A->selected->name[0]||!dv_open(A->panels+*A->active))goto done;
 if(!ds_open(A->selected))goto done;main_key=A->selected->mdate;
 memcpy(md_name,md_raw,30);md_length=30;
 while(md_length && md_name[md_length-1]==' ')--md_length;
 if(md_length>4&&!memcmp(md_name+md_length-4,".OBJ",4)){
  md_length-=4;memset(md_name+md_length,' ',30-md_length);
  if(!md_find())goto done;main_key=md_entry.mdate;
 }
 /* Read the header to distinguish editor state from exported music. */
 for(i=0;i<256;++i){c=ds_get();if(c<0)goto done;SONG[i]=c;}
 if(SONG[0]||SONG[1]){
  if(ds_length!=LIMIT||ds_count>10)goto done;
  for(i=256;i<LIMIT;++i){c=ds_get();if(c<0)goto done;SONG[i]=c;}
  ok=valid();
 }else{
  if(!md_length||md_length>26)goto done;
  /* Retain both validated maps outside the overlay. Neither a display
   * name nor a stale panel size identifies the neighbouring file. */
#ifdef __CC65__
  memcpy(context,ds_slots,26); /* cc65 unsigned int is a little-endian word */
#else
  for(i=0;i<13;++i){context[i*2]=ds_slots[i];context[i*2+1]=ds_slots[i]>>8;}
#endif
  memcpy(context+52,&ds_length,2);
  memcpy(context+56,&ds_count,2);memcpy(context+60,&main_key,2);
  memcpy(md_name+md_length,".OBJ",4);
  if(!md_find())goto done;
#ifdef __CC65__
  memcpy(context+26,ds_slots,26);
#else
  for(i=0;i<13;++i){context[26+i*2]=ds_slots[i];context[27+i*2]=ds_slots[i]>>8;}
#endif
  memcpy(context+54,&ds_length,2);
  memcpy(context+58,&ds_count,2);
  /* Distinct files must not alias each other's T/S lists/data sectors. */
  if(md_entry.mdate==ds_word(context+60))goto done;
  for(i=0;i<13;++i){
   if(ds_slots[i] && (ds_slots[i]==ds_word(context+60)))goto done;
   for(j=0;j<13;++j){
    unsigned int p=ds_word(context+j*2);
    if(p && (p==md_entry.mdate||p==ds_slots[i]))goto done;
   }
  }
  context[62]='M';context[63]='S';score=ok=1;
 }
done:
 if(!dv_close())ok=0;
 if(!ok){scpy(A->note,"Bad DOS MCS score/export or I/O error.");return 0;}
#ifndef PLUGIN_HOST
 /* cfg_path is bounded separately; no source-name/path aliasing. */
 i=strlen(A->cfg_path);if(i>=PATH_LEN)goto player_bad;
 memcpy(A->full,A->cfg_path,i+1);
 while(i&&A->full[i-1]!='/')--i;
 if(!i||i+14>=PATH_LEN+NAME_LEN)goto player_bad;
 strcpy(A->full+i,score?"MCSIMPORT.PLG":"MCSPLAY.PLG");
 /* Directory services may have left a descriptor open. Release it before
  * borrowing the SECOND file's $0C00 buffer; only the player stays open. */
 A->dir_close();md_player=fopn(A->full,"rb");if(!md_player)goto player_bad;
#endif
 return score?2:1;
#ifndef PLUGIN_HOST
player_bad:scpy(A->note,"Cannot open MCS stage.");return 0;
#endif
}
