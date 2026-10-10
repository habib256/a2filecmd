/* Print Shop borders: F5 has three row-major 24x14 patterns after 12
 * bytes; Companion BIN has 3 column-major 24x14 patterns, with
 * optional FOUR-BYTE PREFIX, not a trailer. Derived from original BOEDIT
 * SETBORD/GETMASK source. MAIN/text only, complete read+close before display. */
#include "ps_source.h"
#pragma rodata-name(push,"OVLHDR")
const struct PsHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,
 {0,0,0},"Preview Print Shop border patterns (24x14)"};
#pragma rodata-name(pop)
static unsigned char border[264];
static void show(unsigned char prefix){
 unsigned char x,y,k,ink;
 unsigned int off;
 ps_api.clrscr();ps_api.gotoxy(0,0);
 ps_api.cprintf("Print Shop border: 3 patterns 24x14%s",prefix?" + options":"");
 for(k=0;k<3;++k){
  ps_api.gotoxy(k*26,2);ps_api.cprintf("Pattern %u",k+1);
  for(y=0;y<14;++y){
   ps_api.gotoxy(k*26,y+4);
   for(x=0;x<24;++x){
    if(ps_new){off=12+(unsigned int)k*42+(unsigned int)y*3+x/8;ink=border[off]&(128>>(x&7));}
    else {off=prefix+(unsigned int)k*48+x+(y<7?24:0);ink=border[off]&(1<<(y%7));}
    ps_api.cputc(ink?'*':' ');
   }
  }
 }
 if(prefix){ps_api.gotoxy(0,20);ps_api.cprintf("Options: %02X %02X %02X %02X (no assembled frame)",border[0],border[1],border[2],border[3]);}
 ps_api.message("ESC or any key back");ps_api.wait_key();
}
void __fastcall__ plugin_entry(const struct A2fcApi* api){
 unsigned int n=0;int c;
 if(!ps_select(api))return;
 if(!ps_open())goto fail;
 while((c=ps_get())>=0){if(n<264)border[n]=c;if(++n>264)break;}
 if(!ps_close())goto fail;
 if(ps_new){
  if(ps_aux!=0x2000 || n!=264)goto malformed;
  show(0);api->strcpy(api->reselect,api->selected->name);return;
 }
 if(n!=144 && n!=148)goto malformed;
 if((ps_aux&0xCFFF)!=0x4800)goto malformed;
 show(n==148?4:0);api->strcpy(api->reselect,api->selected->name);return;
malformed:api->strcpy(api->note,"Malformed/unsupported Print Shop border.");return;
fail:if(ps_bad)api->strcpy(api->note,"Print Shop read/open/close error.");
}
