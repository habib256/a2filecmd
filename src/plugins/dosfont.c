/* Direct read-only DOS HRCG adapter for FONTVIEW's existing raw renderer.
 * Fully read/close first, then split the validated font between copy_buf
 * and HGRSAFE storage. No disk/AUX writes or RAM-disk reconstruction. */
#include <stddef.h>
#define DS_SECTORS 5
#include "ps_source.h"
#pragma rodata-name(push,"OVLHDR")
const struct PsHeader __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG,plugin_entry,
 {0,0,0},"Hi-res font preview from DOS"};
#pragma rodata-name(pop)
static unsigned char raw_font[1024];
#ifdef PLUGIN_HOST
static unsigned char df_tail[512],df_count;
static unsigned char* df_buf;
extern void host_font(const unsigned char*,unsigned int);
#else
extern unsigned char df_tail[512],df_count;
extern unsigned char* df_buf;
const unsigned char df_wait_offset=offsetof(struct A2fcApi,wait_key);
#endif
unsigned char __fastcall__ df_preflight(const struct A2fcApi* api){
 unsigned int n=0;int c;
 ps_api=*api;
 ps_dos=api->panels!=NULL && api->active!=NULL && api->panels[*api->active].fs==FS_DOS33;
 if(!ps_dos || api->selected->type!=6 || !api->selected->name[0])goto bad;
 if(!ps_open())goto bad;
 while((c=ps_get())>=0){
  if(n<sizeof raw_font)raw_font[n]=c;
  if(++n>sizeof raw_font)break;
 }
 if(!ps_close())goto bad;
 if(n!=768 && n!=1024)goto bad;
 /* copy_buf was sector scratch until close; only now may it hold glyphs. */
 memcpy(api->copy_buf,raw_font,512);
 memcpy(df_tail,raw_font+512,n-512);
 df_buf=api->copy_buf;df_count=n/8;
 api->strcpy(api->reselect,api->selected->name);
 return 1;
bad:api->strcpy(api->note,"Bad hi-res font/DOS read/close error.");return 0;
}
#ifdef PLUGIN_HOST
void __fastcall__ plugin_entry(const struct A2fcApi* api){
 if(df_preflight(api))host_font(raw_font,(unsigned int)df_count*8);
}
#endif
