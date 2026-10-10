/* DPC native 560-dot profile. Full DHGR planes, substitute text font. */
#define VG_DESCRIPTION "Graphics Magician DHGR DPC pictures"
#define VG_LABEL "DHGR DPC"
#define VG_CLEAR 255
#define VG_DOUBLE 2
#include "v1gfx.h"
#include "dgmagi_data.h"
static unsigned int dg_px,dg_tx;
static unsigned char dg_py,dg_ty,dg_colour,dg_pattern,dg_brushno;
static unsigned char dg_pat(unsigned char y,unsigned char c){
 static const unsigned char masks[8]={0x8F,0x9E,0xBC,0xF8,0xF0,0xE1,0xC3,0x87};
 unsigned char n=y&1?dg_odd[dg_pattern]:dg_even[dg_pattern],mask,v;
 mask=masks[c&7];
 v=dg_rows[(n>>4)*4+(c&3)]&mask;
 return v|(dg_rows[(n&15)*4+(c&3)]&~mask);
}
static void dg_dot(unsigned int x,unsigned char y){
 unsigned char c,mask,old;
 if(x>=560 || y>=192)return;
 c=x/7;mask=0x80|vg_bits[x%7];old=vg_rd(y,c);
 vg_wr(y,c,(old&~mask)|(dg_rows[dg_colour*4+(c&3)]&mask));
}
static void dg_line(unsigned int x,unsigned char y){
 unsigned int dx=dg_px>x?dg_px-x:x-dg_px,n;
 unsigned char dy=dg_py>y?dg_py-y:y-dg_py;
 int error=(int)dx-dy; signed char sx=dg_px<x?1:-1,sy=dg_py<y?1:-1;
 dg_dot(dg_px,dg_py);
 for(n=dx+dy;n;--n){
  if(error>=0){dg_px+=sx;error-=dy;}else{dg_py+=sy;error+=dx;}
  dg_dot(dg_px,dg_py);
 }
 dg_px=x;dg_py=y;
}
static unsigned char dg_white(unsigned int x,unsigned char y){
 unsigned char c=x/7,p=x%7,v=vg_rd(y,c),mask;
 mask=p?(vg_bits[p-1]|vg_bits[p]):3;return (v&mask)==mask;
}
static void dg_fill(unsigned int x,unsigned char y){
 unsigned int l,r,xx;unsigned char c,p,v;
 while(dg_white(x,y)){if(!y)break;--y;}
 if(!dg_white(x,y)){if(y==191)return;++y;}
 do{
  l=x;r=x;
  while(l && (vg_rd(y,(l-1)/7)&vg_bits[(l-1)%7]))--l;
  while(r<559 && (vg_rd(y,(r+1)/7)&vg_bits[(r+1)%7]))++r;
  for(xx=l;xx<=r;++xx){c=xx/7;p=0x80|vg_bits[xx%7];v=vg_rd(y,c);vg_wr(y,c,(v&~p)|(dg_pat(y,c)&p));}
  x=(l+r)/2;
  if(++y==192)break;
 }while(dg_white(x,y));
}
static void dg_stamp(unsigned int x,unsigned char y,const unsigned char* bits,unsigned char height,unsigned char xor){
 unsigned char row,bit,c,mask,v;unsigned int xx;
 for(row=0;row<height && (unsigned int)y+row<192;++row){
  for(bit=0;bit<7;++bit)if(bits[row]&vg_bits[bit]){
   for(xx=x+bit*2;xx<=x+bit*2+1 && xx<560;++xx){
    c=xx/7;mask=vg_bits[xx%7];v=vg_rd(y+row,c);
    vg_wr(y+row,c,xor?v^mask:(v&~mask&127)|((mask|128)&dg_pat(y+row,c)));
   }
  }
 }
}
static void vg_decode(void){
 int raw,a,b;unsigned char t,arg,seen=0,ended=0,pen=0;
 unsigned int x;
 dg_px=dg_tx=0;dg_py=dg_ty=0;dg_colour=0;dg_pattern=0;dg_brushno=5;
 while((raw=vg_get())>=0){
  if(vg_off>65535UL){vg_invalid();return;}
  if(ended){if(raw){vg_invalid();return;}continue;}
  if(!raw){ended=1;continue;}
  t=raw>>4;arg=raw&15;
  if(t==2){dg_colour=arg;continue;}
  if(t==4){if(arg>7){vg_invalid();return;}dg_brushno=arg;continue;}
  if(t==3 || t==5 || t==6){
   a=vg_get();if(arg || a<0){vg_invalid();return;}
   if(t==6){dg_pattern=a;continue;}
   if(a<32 || a>127){vg_invalid();return;}
   if(vg_draw)dg_stamp(dg_tx,dg_ty,dg_font+(unsigned int)(a-32)*8,8,t==3);
   dg_tx+=16;continue;
  }
  if(t!=1 && t!=7 && t!=8 && t!=10 && t!=12 && t!=14){vg_invalid();return;}
  a=vg_get();b=vg_get();x=((unsigned int)arg<<8)|a;
  if(a<0 || b<0 || x>=560 || b>=192){vg_invalid();return;}
  if(t==1){dg_tx=x;dg_ty=b;continue;}
  if(t==8){dg_px=x;dg_py=b;pen=1;continue;}
  if(t==7){vg_invalid();return;} /* transient colour-line mode unqualified */
  if(t==10){if(!pen){vg_invalid();return;}if(vg_draw)dg_line(x,b);else{dg_px=x;dg_py=b;}}
  else if(t==14){if(vg_draw)dg_fill(x,b);}
  else if(vg_draw){
   const unsigned char* q=dg_brush+(unsigned int)dg_brushno*32;
   dg_stamp(x,b,q,8,0);dg_stamp(x+14,b,q+8,8,0);
   dg_stamp(x,b+8,q+16,8,0);dg_stamp(x+14,b+8,q+24,8,0);
  }
  seen=1;
 }
 if(!ended || !seen)vg_invalid();
}
