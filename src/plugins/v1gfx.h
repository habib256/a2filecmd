/* No source writes. Validation and close before consent and first AUX write.
 * AUX staging uses $4000-$7FFF. Source reopen/read/close errors discard the
 * staged view. The safe tail rebuilds /RAM after every attempted AUX write.
 * MAIN $2000-$3FFF is replaced only after the C decoder has returned. */
#include <stddef.h>
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
unsigned int vg_addr,vg_count;
unsigned char* vg_buf;
void __fastcall__ vg_write(unsigned char);
void vg_read(void);
static const struct A2fcApi* V;
static FILE* vg_file;
static unsigned char vg_input[128],vg_row[80];
static unsigned int vg_at,vg_have;
static unsigned long vg_off;
static unsigned char vg_bad,vg_draw,vg_used,vg_y,vg_dirty;
static const unsigned char vg_bits[7]={1,2,4,8,16,32,64};
#ifndef PLUGIN_HOST
#define ferror(f) (((unsigned char*)(f))[1]&4)
typedef char vg_api_checked[1-((int)offsetof(struct A2fcApi,wait_key)-34)*((int)offsetof(struct A2fcApi,wait_key)-34)-((int)offsetof(struct A2fcApi,ram_format)-98)*((int)offsetof(struct A2fcApi,ram_format)-98)];
#endif
struct VgHeader {unsigned int signature;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[44];};
#pragma rodata-name(push,"OVLHDR")
const struct VgHeader __plugin_header={MEDIA_PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},VG_DESCRIPTION};
#pragma rodata-name(pop)
static void vg_invalid(void){if(!vg_bad)vg_bad=2;}
static int vg_get(void){
 if(vg_at==vg_have){vg_at=0;vg_have=V->fread(vg_input,1,128,vg_file);if(ferror(vg_file)){vg_bad=1;return -1;}if(!vg_have)return -1;}
 ++vg_off;return vg_input[vg_at++];
}
static unsigned char vg_seek(unsigned int off){
 if(V->fseek(vg_file,(long)off,SEEK_SET)){vg_bad=1;return 0;}
 vg_at=vg_have=0;vg_off=off;return 1;
}
static unsigned int vg_rowaddr(unsigned char y){return ((unsigned int)(y&7)<<10)|((unsigned int)(y&56)<<4)|((unsigned int)(y>>6)*40);}
static void vg_flush(void){
 unsigned char c;
 if(!vg_draw || !vg_dirty)return;
 for(c=0;c<80;++c){vg_addr=(c&1?0x6000:0x4000)+vg_rowaddr(vg_y)+(c>>1);vg_write(vg_row[c]);}
 vg_dirty=0;
}
static void vg_home(unsigned char y){
 unsigned char c,tmp[40];
 if(!vg_draw || y==vg_y)return;
 vg_flush();vg_y=y;
 vg_addr=0x4000+vg_rowaddr(y);vg_buf=tmp;vg_count=40;vg_read();
 for(c=0;c<40;++c)vg_row[c*2]=tmp[c];
 vg_addr=0x6000+vg_rowaddr(y);vg_read();
 for(c=0;c<40;++c)vg_row[c*2+1]=tmp[c];
}
static unsigned char vg_rd(unsigned char y,unsigned char c){vg_home(y);return vg_row[c];}
static void vg_wr(unsigned char y,unsigned char c,unsigned char v){if(!vg_draw)return;vg_home(y);vg_row[c]=v;vg_dirty=1;}
static void vg_decode(void);
static unsigned char vg_pass(unsigned char draw){
 vg_at=vg_have=0;vg_off=0;vg_bad=0;vg_draw=draw;vg_y=255;vg_dirty=0;
 vg_file=V->fopen(V->full,"rb");if(!vg_file){vg_bad=1;return 0;}
 vg_decode();vg_flush();if(V->fclose(vg_file))vg_bad=1;return !vg_bad;
}
unsigned char __fastcall__ vg_run(const struct A2fcApi* a){
 V=a;vg_used=0;
 if(!a->full[0] || a->selected->type!=6){a->strcpy(a->note,"Select a BIN picture.");return 0;}
 if(!strcmp(a->full,"/RAM") || !strncmp(a->full,"/RAM/",5)){
  a->strcpy(a->note,"Copy picture off /RAM before viewing.");return 0;
 }
 if(!vg_pass(0)){a->strcpy(a->note,vg_bad==1?"Read/open/close error.":"Malformed " VG_LABEL " file.");return 0;}
 if(!a->aux_consent())return 0;
 vg_used=1;
 /* Initialise both staged planes without touching AUX text or resident MAIN. */
 for(vg_addr=0x4000;vg_addr<0x8000;++vg_addr)vg_write(VG_CLEAR);
 if(!vg_pass(1)){a->strcpy(a->note,"Picture read/structure error; /RAM erased.");return 1;}
 a->strcpy(a->reselect,a->selected->name);
 a->strcpy(a->note,VG_LABEL " preview; /RAM erased and rebuilt.");
 return 5|VG_DOUBLE;
}
