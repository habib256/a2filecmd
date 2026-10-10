/* PCS authored background and polygon preview, library objects outlined.
 * No game code is executed. AUX staging follows v1gfx.h's consent contract. */
#define VG_DESCRIPTION "PCS static preview (library outlines)"
#define VG_LABEL "PCS outlines"
#define VG_CLEAR 0
#define VG_DOUBLE 0
#include "v1gfx.h"
static unsigned char pc_len[255],pc_x[64],pc_y[64];
static int pc_cross[64];
static unsigned char pc_count;
static unsigned int pc_objstart,pc_bitmap;
static const unsigned char pc_colors[16]={0,0,0x2A,0x55,0x55,0x2A,0x7F,0x7F,0x80,0x80,0xAA,0xD5,0xD5,0xAA,0xFF,0xFF};
static void pc_pixel(unsigned char x,unsigned char y,unsigned char colour){
 unsigned char col=x/7,mask=0x80|vg_bits[x%7],old=vg_rd(y,col*2);
 vg_wr(y,col*2,(old&~mask)|(pc_colors[colour+(col&1)]&mask));
}
static void pc_span(unsigned char lo,unsigned char hi,unsigned char row,unsigned char color){
 unsigned char first=lo/7,last=hi/7,x,col;
 if(first==last){for(x=lo;x<=hi;++x)pc_pixel(x,row,color);return;}
 for(x=lo;x<(first+1)*7;++x)pc_pixel(x,row,color);
 for(col=first+1;col<last;++col)vg_wr(row,col*2,pc_colors[color+(col&1)]);
 for(x=last*7;x<=hi;++x)pc_pixel(x,row,color);
}
static void pc_polygon(unsigned char type,unsigned char color,unsigned char n){
 unsigned char row,i,j,k,hi,lo;int v,a,b;
 /* Preview uses even/odd scan conversion, without physics/scripting. */
 for(row=0;row<192;++row){
  k=0;
  for(i=0,j=n-1;i<n;j=i++){
   if((pc_y[i]<=row && pc_y[j]>row)||(pc_y[j]<=row && pc_y[i]>row)){
    a=(int)pc_x[j]-(int)pc_x[i];b=(int)pc_y[j]-(int)pc_y[i];
    /* Force signed arithmetic on cc65 too: descending edges must divide
     * a negative numerator/denominator with truncation toward zero. */
    v=(int)((long)pc_x[i]+(long)a*((int)row-(int)pc_y[i])/(long)b);pc_cross[k++]=v;
   }
  }
  for(i=1;i<k;++i){v=pc_cross[i];j=i;while(j && pc_cross[j-1]>v){pc_cross[j]=pc_cross[j-1];--j;}pc_cross[j]=v;}
  if(type==3 || color==16 || !color){
   for(i=0;i<k;++i)pc_pixel(pc_cross[i],row,14);
  }else if(type==2){
   lo=0;
   for(i=0;i<k;i+=2){hi=pc_cross[i];if(hi>lo)pc_span(lo,hi-1,row,color);lo=i+1<k?pc_cross[i+1]:153;}
   if(lo<154)pc_span(lo,153,row,color);
  }else for(i=0;i+1<k;i+=2){lo=pc_cross[i];hi=pc_cross[i+1];pc_span(lo,hi,row,color);}
 }
}
static unsigned char pc_objects(unsigned char render){
 unsigned char i,j,n,type,color,length;int raw;
 for(i=0;i<pc_count;++i){
  length=pc_len[i];type=vg_get();color=vg_get();n=vg_get();
  if(vg_bad || type<1 || type>10 || color>16 || (color&1) || n<3 || n>64 || length<3+2*n){vg_invalid();return 0;}
  for(j=0;j<n;++j){raw=vg_get();if(raw<0 || raw>=154){vg_invalid();return 0;}pc_x[j]=raw;}
  for(j=0;j<n;++j){raw=vg_get();if(raw<0 || raw>=192){vg_invalid();return 0;}pc_y[j]=raw;}
  for(j=3+2*n;j<length;++j)if(vg_get()<0){vg_invalid();return 0;}
  if(render && type<=3)pc_polygon(type,color,n);
 }
 return 1;
}
static void vg_decode(void){
 unsigned int i,count,out=0;unsigned char t,trail=0;int raw;
 for(i=0;i<28;++i)if(vg_get()<0){vg_invalid();return;}
 raw=vg_get();if(raw<1){vg_invalid();return;}pc_count=raw;
 for(i=0;i<pc_count;++i){raw=vg_get();if(raw<9){vg_invalid();return;}pc_len[i]=raw;}
 pc_objstart=29+pc_count;
 if(!pc_objects(0))return;
 pc_bitmap=vg_off;
 for(;;){
  raw=vg_get();if(raw<0){vg_invalid();return;}t=raw;
  if(t==1){raw=vg_get();if(raw<0){vg_invalid();return;}if(raw==1)break;count=raw?raw:256;}
  else count=t?t:256;
  if((unsigned long)out+count>8448UL){vg_invalid();return;}
  for(i=0;i<count;++i){
   raw=t==1?0:vg_get();if(raw<0){vg_invalid();return;}
   if(vg_draw && out<8192){vg_addr=0x4000+out;vg_write(raw);}
   ++out;
  }
 }
 if(out<8192){vg_invalid();return;}
 while(vg_get()>=0)if(++trail>2){vg_invalid();return;}
 if(vg_bad || !vg_draw)return;
 if(!vg_seek(pc_objstart))return;
 pc_objects(1);
}
