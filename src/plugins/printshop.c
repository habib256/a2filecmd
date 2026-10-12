/* Read-only DOS/ProDOS clip art. Validate and close the complete source
 * before MAIN HGR writes. Renderer and bitmap stay below $2000; no AUX. */
#include <stddef.h>
#define DS_SECTORS 3
#include "ps_source.h"
#pragma rodata-name(push,"OVLHDR")
const struct PsHeader __plugin_header={MEDIA_PLUGIN_MAGIC, OVERLAY_BIG,plugin_entry,
 {0,0,0},"Print Shop clip art (DOS/ProDOS)"};
#pragma rodata-name(pop)
const unsigned char ps_wait_offset=offsetof(struct A2fcApi,media_wait);
#ifdef PLUGIN_HOST
static unsigned char ps_bitmap[572];
unsigned char py;
void hv_clear(void);
void hv_show(void);
void __fastcall__ ps_draw(unsigned char*);
#else
extern unsigned char ps_bitmap[572];
#endif
unsigned char __fastcall__ ps_preflight(const struct A2fcApi* api){
 unsigned int n=0;int c;
 if(api->selected->type!=6){api->strcpy(api->note,"Select a Print Shop BIN file.");return 0;}
 if(!ps_select(api))return 0;
 if(!ps_open())goto bad;
 while((c=ps_get())>=0){
  if(n<572)ps_bitmap[n]=c;
  if(++n>576)break;
 }
 if(!ps_close())goto bad;
 if(n!=572 && n!=576)goto bad;
 api->strcpy(api->reselect,api->selected->name);
 return 1;
bad:api->strcpy(api->note,"Bad Print Shop data/read/close error.");return 0;
}
#ifdef PLUGIN_HOST
void __fastcall__ plugin_entry(const struct A2fcApi* api){
 unsigned int off=0;
 if(!ps_preflight(api))return;
 hv_clear();
 for(py=18;py<174;py+=3){ps_draw(ps_bitmap+off);off+=11;}
 hv_show();api->media_wait();api->strcpy(api->reselect,api->selected->name);
}
#endif
