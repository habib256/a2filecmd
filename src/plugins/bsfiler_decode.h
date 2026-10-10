/* AFILER 1.0: 20-byte header, LE record starts, field definitions,
 * sequential values and opaque report/settings area. Original DOS BIN
 * payloads may be extracted as ProDOS BIN without changing their bytes.
 * Never read bounds from stale panel sizes. Fixed tables cap all indices.
 * Apple floating values shown to three fractional digits (truncated);
 * formulas are identified, not evaluated. Dates support year-only values. */
static unsigned char bf_form[1024];
static unsigned int bf_index[256],bf_label[40];
static unsigned int bf_word(const unsigned char* p){return (unsigned int)p[0]|((unsigned int)p[1]<<8);}
static unsigned int bf_u16(void){int a=rt_get(),b=rt_get();if(a<0 || b<0){rt_invalid();return 0;}return a|((unsigned int)b<<8);}
static void bf_text(const char* s){while(*s && !rt_cancel)rt_put(*s++);}
static void bf_number(const unsigned char* p){
 unsigned long m,whole,rem;unsigned char bits,i,digits[3];int exp;
 char s[16];
 if(!p[0]){bf_text("0");return;}
 exp=(int)p[0]-129;
 if(exp>30 || exp<-23){
  bf_text("[FP $");for(i=0;i<5;++i){rt_put("0123456789ABCDEF"[p[i]>>4]);rt_put("0123456789ABCDEF"[p[i]&15]);}rt_put(']');return;
 }
 /* Keep 24 significant bits so remainder*10 cannot overflow 32 bits. */
 m=0x800000UL|((unsigned long)(p[1]&127)<<16)|((unsigned long)p[2]<<8)|p[3];
 if(p[1]&128)rt_put('-');
 if(exp>=23){whole=m<<(exp-23);rem=0;bits=23;}
 else {bits=23-exp;if(bits>23){m>>=bits-23;bits=23;}whole=m>>bits;rem=m&((1UL<<bits)-1);}
 rt_api.sprintf(s,"%lu",whole);bf_text(s);
 if(rem){
  for(i=0;i<3;++i){rem*=10;digits[i]=rem>>bits;rem&=(1UL<<bits)-1;}
  rt_put('.');for(i=0;i<3;++i)rt_put('0'+digits[i]);
 }
}
static void rt_decode(void){
 unsigned int fields,count,formlen,datalen,settings,i,j,at,start,end,base;
 unsigned char h[20],v[5],t,c;int raw;
 char title[32];
 if(rt_api.selected->type!=6){rt_invalid();return;}
 for(i=0;i<20;++i){raw=rt_get();if(raw<0){rt_invalid();return;}h[i]=raw;}
 for(i=0;i<10;++i)if(h[i]!=(unsigned char)("AFILER 1.0"[i]|128)){rt_invalid();return;}
 fields=bf_word(h+10);count=bf_word(h+12);formlen=bf_word(h+14);datalen=bf_word(h+16);settings=bf_word(h+18);
 if(!fields || fields>40 || (count&1) || count>512 || !formlen || formlen>1024 ||
    20UL+count+formlen+datalen+settings>65535UL){rt_invalid();return;}
 count>>=1;
 for(i=0;i<count;++i){bf_index[i]=bf_u16();if(rt_bad)return;
  if((!i && bf_index[i]) || bf_index[i]>=datalen || (i && bf_index[i]<=bf_index[i-1])){rt_invalid();return;}}
 if(!count && datalen){rt_invalid();return;}
 for(i=0;i<formlen;++i){raw=rt_get();if(raw<0){rt_invalid();return;}bf_form[i]=raw;}
 at=0;
 for(i=0;i<fields;++i){
  if(at+6>=formlen){rt_invalid();return;}
  t=bf_form[at];if(t>7 || t==4){rt_invalid();return;}bf_label[i]=at;at+=6;
  do{if(at>=formlen){rt_invalid();return;}c=bf_form[at++];if((c&127)<32 || (c&127)==127){rt_invalid();return;}}while(c<128);
  if(t==6){if(at+42>formlen){rt_invalid();return;}at+=42;}
 }
 if(at!=formlen){rt_invalid();return;}
 base=20+count*2+formlen;
 for(i=0;i<count && !rt_cancel;++i){
  start=base+bf_index[i];end=base+(i+1<count?bf_index[i+1]:datalen);
  if(rt_off!=start){rt_invalid();return;}
  rt_api.sprintf(title,"Record %u/%u",i+1,count);bf_text(title);rt_put(13);
  for(j=0;j<fields && !rt_cancel;++j){
   at=bf_label[j];t=bf_form[at];at+=6;
   do{c=bf_form[at++];rt_put(c&127);}while(c<128);
   bf_text(": ");
   if(t==6)bf_text("[formula]");
   else if(t==0 || t==1 || t==7){
    do{
     if(rt_off>=end || (raw=rt_get())<0){rt_invalid();return;}
     c=raw;
     if(c==128)break;
     if(((c&127)<32 && (c&127)!=13) || (c&127)==127){rt_invalid();return;}
     rt_put(c&127);
    }while(c<128);
   }else{
    t=t==5?3:5;
    for(at=0;at<t;++at){if(rt_off>=end || (raw=rt_get())<0){rt_invalid();return;}v[at]=raw;}
    if(t==5)bf_number(v);
    else {
     c=((v[1]&1)<<3)|(v[2]>>5);
     if(v[0]>99 || (v[1]>>1)>99 || c>12 || (!c && (v[2]&31))){rt_invalid();return;}
     rt_api.sprintf(title,"%u",(unsigned int)v[0]*100+(v[1]>>1));bf_text(title);
     if(c){rt_api.sprintf(title,"-%02u-%02u",(unsigned int)c,(unsigned int)(v[2]&31));bf_text(title);}
    }
   }
   rt_put(13);
  }
  if(!rt_cancel && rt_off!=end){rt_invalid();return;}
 }
 if(rt_cancel)return;
 for(i=0;i<settings;++i)if(rt_get()<0){rt_invalid();return;}
 if(rt_get()>=0)rt_invalid();
 if(!count){bf_text("Empty database");rt_put(13);for(j=0;j<fields;++j){at=bf_label[j]+6;do{c=bf_form[at++];rt_put(c&127);}while(c<128);rt_put(13);}}
}
