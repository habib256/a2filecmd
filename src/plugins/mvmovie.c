/* Movie Maker MVM films: read-only 40x48 colour preview, frame by frame.
 * MAIN text/lores page only, no AUX/RAM reconstruction. Never executes the
 * MVM command that embeds machine code. Fully reads, validates and closes
 * the film before displaying a frame. */
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct MvHeader {unsigned int signature;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[44];};
#pragma rodata-name(push,"OVLHDR")
const struct MvHeader __plugin_header={MEDIA_PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},"Movie Maker frames (40x48 colour preview)"};
#pragma rodata-name(pop)
#ifndef PLUGIN_HOST
#define ferror(f) (((unsigned char*)(f))[1]&4)
#endif
static const struct A2fcApi* M;
static FILE* mv_file;
static unsigned char mv_input[128],mv_shapes[256],mv_sprites[192],mv_pixels[1920],mv_rowdata[40];
static unsigned int mv_at,mv_have,mv_size[2],mv_start[2],mv_base[2];
static unsigned long mv_off;
static unsigned char mv_bad,mv_draw,mv_cancel,mv_nsprites,mv_cached,mv_y;
static void mv_invalid(void){if(!mv_bad)mv_bad=2;}
static int mv_get(void){
 if(mv_at==mv_have){mv_at=0;mv_have=M->fread(mv_input,1,128,mv_file);if(ferror(mv_file)){mv_bad=1;return -1;}if(!mv_have)return -1;}
 ++mv_off;return mv_input[mv_at++];
}
static unsigned char mv_seek(unsigned int at){
 if(M->fseek(mv_file,(long)at,SEEK_SET)){mv_bad=1;return 0;}mv_at=mv_have=0;mv_off=at;return 1;
}
static unsigned int mv_word(void){int lo=mv_get(),hi=mv_get();if(lo<0 || hi<0){mv_invalid();return 0;}return lo|((unsigned int)hi<<8);}
static unsigned int mv_hgr(unsigned char y){return ((unsigned int)(y&7)<<10)|((unsigned int)(y&56)<<4)|((unsigned int)(y>>6)*40);}
static unsigned char mv_row(unsigned char plane,unsigned char y){
 unsigned int at=mv_hgr(y),lo,hi;unsigned char i;
 if(mv_cached==plane && mv_y==y)return 1;
 mv_cached=plane;mv_y=y;for(i=0;i<40;++i)mv_rowdata[i]=0;
 lo=at>mv_start[plane]?at:mv_start[plane];hi=at+40;
 if(hi>mv_start[plane]+mv_size[plane])hi=mv_start[plane]+mv_size[plane];
 if(hi<=lo)return 1;
 if(M->fseek(mv_file,(long)mv_base[plane]+lo-mv_start[plane],SEEK_SET) ||
    M->fread(mv_rowdata+lo-at,1,hi-lo,mv_file)!=hi-lo || ferror(mv_file)){mv_bad=1;return 0;}
 return 1;
}
static unsigned char mv_color(unsigned char x){
 unsigned int bit=(unsigned int)x*2;unsigned char a=mv_rowdata[bit/7],b,p;
 p=(a>>(bit%7))&1;++bit;b=mv_rowdata[bit/7];p|=((b>>(bit%7))&1)<<1;
 if(!p)return 0;if(p==3)return 15;
 if(a&128)return p==2?9:6;return p==2?12:3;
}
static void mv_display(void){
 unsigned int base;unsigned char y,x,a,b;
#ifdef PLUGIN_HOST
 extern void mv_host_display(const unsigned char*);mv_host_display(mv_pixels);
#else
 for(y=0;y<24;++y){base=0x0400+((unsigned int)(y&7)<<7)+(unsigned int)(y>>3)*40;
  for(x=0;x<40;++x){a=mv_pixels[(unsigned int)y*80+x];b=mv_pixels[(unsigned int)y*80+40+x];*((unsigned char*)(base+x))=a|(b<<4);}}
 *((unsigned char*)0xC000)=0;*((unsigned char*)0xC00C)=0;*((unsigned char*)0xC054)=0;
 *((unsigned char*)0xC056)=0;*((unsigned char*)0xC052)=0;*((unsigned char*)0xC050)=0;
#endif
}
static void mv_scene(void){
 unsigned int at=mv_off,i,p,source_y,source_x;unsigned char x,y,id,sx,sy,w,h,xx,yy;int dx,dy;
 if(!mv_draw)return;
 mv_cached=255;
 for(y=0;y<48;++y){
  if(!mv_row(1,y*4))return;
  for(x=0;x<40;++x)mv_pixels[(unsigned int)y*40+x]=mv_color((unsigned int)x*7/2);
 }
 for(i=0;i<mv_nsprites;++i){
  p=i*3;id=mv_sprites[p];sx=mv_shapes[(id-1)*4];sy=mv_shapes[(id-1)*4+1];w=mv_shapes[(id-1)*4+2];h=mv_shapes[(id-1)*4+3];
  dx=mv_sprites[p+1];if(dx>=140)dx-=256;dy=mv_sprites[p+2];
  for(y=0;y<48;++y){
   if((int)y*4<dy || (int)y*4>=dy+h)continue;source_y=sy+(int)y*4-dy;if(source_y>=192)continue;yy=source_y;
   if(!mv_row(0,yy))return;
   for(x=0;x<40;++x){
    xx=(unsigned int)x*7/2;
    if((int)xx<dx || (int)xx>=dx+w)continue;
    source_x=sx+xx-dx;if(source_x>=140)continue;xx=source_x;
    /* A reduced preview treats the shape rectangle as opaque. */
    mv_pixels[(unsigned int)y*40+x]=mv_color(xx);
   }
  }
 }
 if(!mv_seek(at))return;mv_display();
 if(M->wait_key()==KEY_ESC)mv_cancel=1;
}
static void mv_decode(void){
 unsigned int length,left,i,nframes=0;unsigned char tag,phase=0,op,n,id,trail=0;int raw;
 mv_nsprites=0;
 for(;;){
  raw=mv_get();if(raw<0){mv_invalid();return;}tag=raw;length=mv_word();if(mv_bad)return;
  if(mv_off+length>65535UL){mv_invalid();return;}
  if(!phase){if(tag!=1 || length!=256){mv_invalid();return;}for(i=0;i<256;++i){raw=mv_get();if(raw<0){mv_invalid();return;}mv_shapes[i]=raw;}phase=1;continue;}
  if(phase==1 || phase==2){
   if(tag!=phase+1 || length<2 || length>8194){mv_invalid();return;}
   i=phase-1;mv_start[i]=mv_word();mv_size[i]=length-2;mv_base[i]=mv_off;
   if(mv_start[i]>8192 || mv_size[i]>8192-mv_start[i]){mv_invalid();return;}
   for(left=length-2;left;--left)if(mv_get()<0){mv_invalid();return;}++phase;continue;
  }
  if(phase==3){if(tag!=6 || length){mv_invalid();return;}phase=4;continue;}
  if(phase==4){
   if(tag!=5 || !length){mv_invalid();return;}left=length;
   while(left && !mv_cancel){
    raw=mv_get();--left;if(raw<0){mv_invalid();return;}op=raw;
    if(op<16){
     n=op&15;if((unsigned int)n*3>left || mv_nsprites+n>64){mv_invalid();return;}
     for(i=0;i<n;++i){
      raw=mv_get();id=raw;if(raw<1 || raw>64 ||
         mv_shapes[(id-1)*4]>=140 || mv_shapes[(id-1)*4+1]>=192 || mv_shapes[(id-1)*4+2]>140){mv_invalid();return;}
      mv_sprites[mv_nsprites*3]=id;
      raw=mv_get();if(raw<0){mv_invalid();return;}mv_sprites[mv_nsprites*3+1]=raw;
      raw=mv_get();if(raw<0){mv_invalid();return;}mv_sprites[mv_nsprites*3+2]=raw;++mv_nsprites;left-=3;
     }
    }else if(op==0x30){++nframes;mv_scene();mv_nsprites=0;if(mv_bad)return;}
    else if(op==0xC0){if(left || mv_nsprites || !nframes){mv_invalid();return;}}
    else {mv_invalid();return;}
   }
   if(mv_cancel)return;if(op!=0xC0){mv_invalid();return;}phase=5;continue;
  }
  if(phase==5){if(tag || length){mv_invalid();return;}phase=6;continue;}
  if(tag!=7 || length){mv_invalid();return;}break;
 }
 while(mv_get()>=0)if(++trail>4){mv_invalid();return;}
}
static unsigned char mv_pass(unsigned char draw){
 mv_at=mv_have=0;mv_off=0;mv_bad=mv_cancel=0;mv_draw=draw;
 mv_file=M->fopen(M->full,"rb");if(!mv_file){mv_bad=1;return 0;}
 mv_decode();if(M->fclose(mv_file))mv_bad=1;return !mv_bad;
}
void __fastcall__ plugin_entry(const struct A2fcApi* a){
 M=a;
 if(!a->full[0] || a->selected->type!=6){a->strcpy(a->note,"Select a BIN MVM film.");return;}
 if(!mv_pass(0)){a->strcpy(a->note,mv_bad==1?"Read/open/close error.":"Unsupported/malformed MVM film.");return;}
 a->clrscr();
 if(!mv_pass(1))a->strcpy(a->note,mv_bad==1?"Read/open/close error.":"Malformed MVM film.");
 else a->strcpy(a->note,"MVM: 40x48 opaque frames; Space next, ESC back.");
#ifndef PLUGIN_HOST
 *((unsigned char*)0xC051)=0;*((unsigned char*)0xC00D)=0;
#endif
 a->strcpy(a->reselect,a->selected->name);
}
