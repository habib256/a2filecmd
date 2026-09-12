/* LZ4FH: https://github.com/fadden/fhpack . Absolute match offsets,
 * one extension byte, 253 empty match and 254 end marker. Main HGR only. */
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
void hv_clear(void);
void hv_show(void);
struct Header { unsigned int signature; unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3]; char desc[14]; };
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={MEDIA_PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},"LZ4FH picture"};
#pragma rodata-name(pop)
static const struct A2fcApi* A;
#include "hgr_io.h"
static FILE* f;
static unsigned char at,have,bad;
#ifdef PLUGIN_HOST
extern unsigned char host_page[8192];
#define PAGE host_page
#else
#define PAGE ((unsigned char*)0x2000)
#endif
static unsigned char getb(void) {
 if(at==have) {
  at=0; have=frd(A->copy_buf,1,255,f);
  if(!have) {bad=1;return 0;}
 }
 return A->copy_buf[at++];
}
static unsigned char decode(void) {
 unsigned char tag,ext;
 unsigned int pos=0,n,off;
 if(getb()!=0x66)return 0;
 for(;;) {
  tag=getb(); n=tag>>4;
  if(n==15)n+=getb();
  if(n>8192-pos)return 0;
  while(n--) {PAGE[pos++]=getb();if(bad)return 0;}
  n=tag&15;
  if(n==15) {
   ext=getb();
   if(ext==254)return !bad;
   if(ext==253)continue;
   n+=ext;
  }
  n+=4;off=getb();off|=(unsigned int)getb()<<8;
  if(bad || off>=pos || n>8192-pos)return 0;
  while(n--)PAGE[pos++]=PAGE[off++];
 }
}
void __fastcall__ plugin_entry(const struct A2fcApi* api) {

 A=api;at=have=bad=0;
 f=fopn(A->full,"rb");
 if(!f){scpy(A->note,"Bad data/I/O");return;}
 hv_clear();
 if(!decode() || at!=have)bad=1;
 if(frd(A->copy_buf,1,1,f) || ferror(f))bad=1;
 if(fcls(f))bad=1;
 if(!bad){hv_show();getkey(0);}
 scpy(A->reselect,A->selected->name);
 if(bad)scpy(A->note,"Bad data/I/O");
}
