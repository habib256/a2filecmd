/* Internal DOS score decoder. MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUDIO.
 * Fresh file maps were validated by DOSMCS. Only MAIN is written; source
 * images are reopened read-only and closed before the single player FILE.
 * The assembly handoff never executes overwritten overlay code. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int signature;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[32];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={MEDIA_PLUGIN_MAGIC,OVERLAY_BIG | OVERLAY_AUDIO,
 plugin_entry,{0,0,
#ifdef A2FC_6502
 1
#else
 129
#endif
 },"MCS internal DOS score decoder"};
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
#define DS_SECTORS 13
#define DS_POSITION unsigned int
#define DS_NO_SEEK
#define DS_READ_ONLY
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
static unsigned int mi_map[13];
static unsigned char mi_select(unsigned char s){
 unsigned char i;unsigned char* context=(unsigned char*)A->other_full;
 for(i=0;i<13;++i)mi_map[i]=ds_word(context+(s?26:0)+i*2);
 ds_map=mi_map;ds_length=ds_word(context+52+s*2);ds_count=ds_word(context+56+s*2);
 ds_pos=0;ds_cache=65535U;
 if(!ds_count||ds_count>13||ds_length>ds_count*256U-4)return 0;
 for(i=0;i<13;++i)if(mi_map[i] && (!(mi_map[i]>>8)||(mi_map[i]>>8)>=35||(unsigned char)mi_map[i]>=16))return 0;
 return 1;
}
static unsigned char md_next(void){
 if(!mi_select(1))return 0;
 /* Re-read the BIN prefix as well; a changed header is not cached EOF. */
 if(!ds_map[0]||!sector_read(ds_map[0]>>8,ds_map[0],ds_data)||ds_word(ds_data+2)!=ds_length)return 0;
 ds_cache=0;return 1;
}
static unsigned char ms_read(void* p,unsigned int n,FILE* ignored){
 unsigned char* out=p;int c;(void)ignored;
 while(n--){c=ds_get();if(c<0)return 0;*out++=c;}return 1;
}
#define ms_eof(f) (!ds_bad&&ds_pos==ds_length)
#define ms_close(f) (!ds_bad)
#define MS_DOS
#include "mcs_score.h"
unsigned char __fastcall__ md_entrypoint(const struct A2fcApi* a){
 unsigned char ok=0;unsigned int n;
 A=a;SONG=SONG_BUFFER;
#ifndef PLUGIN_HOST
 A->dir_close();
#endif

 dv_file=NULL;
 if(A->other_full[62]!='M'||A->other_full[63]!='S')goto done;
 if(!dv_open(A->panels+*A->active)||!mi_select(0))goto done;
 ds_bad=0;ds_pos=0;ds_prefix=4;ds_cache=65535U;
 if(!ds_map[0]||!sector_read(ds_map[0]>>8,ds_map[0],ds_data)||ds_word(ds_data+2)!=ds_length)goto done;
 ds_cache=0;
 if(!ms_read(SONG,256,NULL))goto done;
 memcpy(A->copy_buf,SONG,256);
 ok=ms_score(NULL);
done:
 if(!dv_close())ok=0;
 if(!ok){scpy(A->note,"Bad DOS MCS score/export or I/O error.");return 0;}
#ifndef PLUGIN_HOST
 n=strlen(A->cfg_path);if(n>=PATH_LEN)goto player_bad;
 memcpy(A->full,A->cfg_path,n+1);while(n&&A->full[n-1]!='/')--n;
 if(!n||n+11>=PATH_LEN+NAME_LEN)goto player_bad;
 strcpy(A->full+n,"MCSPLAY.PLG");A->dir_close();md_player=fopn(A->full,"rb");
 if(!md_player)goto player_bad;
#endif
 return 1;
#ifndef PLUGIN_HOST
player_bad:scpy(A->note,"Cannot open MCSPLAY.PLG.");return 0;
#endif
}
