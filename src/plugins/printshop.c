/* Main-bank HGR only: no AUX or disk writes. */
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
void hv_clear(void);
void hv_show(void);
unsigned char* __fastcall__ hv_row(unsigned char y);
struct Header { unsigned int signature; unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3]; char desc[12]; };
#pragma rodata-name(push, "OVLHDR")
const struct Header __plugin_header = { MEDIA_PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
 {0,0,0}, "Print Shop" };
#pragma rodata-name(pop)
static const struct A2fcApi* A;
#include "hgr_io.h"
static FILE* f;
static unsigned char bad;
static unsigned char readn(void* p, unsigned int n) {
 if (frd(p,1,n,f)!=n) { bad=1; return 0; }
 return 1;
}
static void finish(void) {
 unsigned char b;
 if (frd(&b,1,1,f) || ferror(f)) bad=1;
 if (fcls(f)) bad=1;
 if (!bad) { hv_show(); getkey(0); }
 scpy(A->reselect,A->selected->name);
 if (bad) scpy(A->note,"Bad data/I/O");
}

/* Print Shop clip art: 88x52, MSB left, black ink; 572 bytes plus an
 * optional four-byte trailer. Scale 2x3, centered on a white HGR page. */

unsigned char py;
void __fastcall__ ps_draw(unsigned char*);
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
 unsigned char tail;

 A=api; bad=0;
 if(A->selected->type!=6)return;
 f=fopn(A->full,"rb"); if(!f) {scpy(A->note,"Bad data/I/O");return;}
 hv_clear();
 for(py=18;py<174;py+=3) {
  if(!readn(A->copy_buf,11))goto end;
  ps_draw(A->copy_buf);
 }
 tail=frd(A->copy_buf,1,5,f);
 if(tail && tail!=4)bad=1;
end: finish();
}
