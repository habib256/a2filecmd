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
 {0,0,0}, "MGTK fonts" };
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

/* MGTK format: flag/last/height, widths, then row/column/character planes.
 * Reference: a2stuff/a2d bin/dump_font.pl. 16 cells per row, two HGR
 * bytes per glyph; all 128 glyphs fit without touching auxiliary RAM. */
unsigned char fh, fn, fr, fc;
void __fastcall__ font_draw(unsigned char*);
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
 unsigned char h[3], cols,g;

 A=api; bad=0;
 if(A->selected->type!=7) return;
 f=fopn(A->full,"rb"); if(!f) { scpy(A->note,"Bad data/I/O"); return; }
 if(!readn(h,3)) goto end;
 cols=h[0]==0?1:2; fn=h[1]+1; fh=h[2];
 if((h[0]!=0 && h[0]!=128) || !fn || fn>128 || !fh || fh>22) { bad=1; goto end; }
 if(!readn(A->copy_buf,fn)) goto end;
 for(g=0;g<fn;++g) if(A->copy_buf[g]>cols*7) { bad=1; goto end; }
 hv_clear();
 for(fr=0;fr<fh;++fr) for(fc=0;fc<cols;++fc) {
  if(!readn(A->copy_buf+128,fn)) goto end;
  font_draw(A->copy_buf);
 }
end: finish();
}
