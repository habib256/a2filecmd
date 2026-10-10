/* Magic Window and LISA v3; bounded streaming adaptations of format rules
 * and LISA tables from CiderPress II, Copyright 2023 faddenSoft, Apache-2.0
 * (data/licenses/NOTICE.TXT). A2FC: MAIN only, no source/AUX writes,
 * complete validation + close before display, strict token bounds. */
#if RT_FORMAT == 11
static void rt_decode(void){
 unsigned int i;
 int c;
 if(rt_api.selected->type!=6){rt_invalid();return;}
 for(i=0;i<256;++i){
  c=rt_get();if(c<0 || (!i && c!=0x8D) || (i==2 && c<32)){rt_invalid();return;}
 }
 while(!rt_cancel && (c=rt_get())>=0){
  if(rt_off>49152UL){rt_invalid();return;}
  c&=127;
  if(c==13)rt_put(13);
  else if(c<32 || c==127){rt_put('^');rt_put(c==127?'?':c+64);}
  else rt_put(c);
 }
}
#else
#include <string.h>
/* Retain SIX packed bytes per symbol (the two value bytes are unused).
 * 512 labels require 3072 bytes, without heap allocation or AUX. */
static unsigned char l_symbols[3072],l_line[126];
static unsigned int l_count,l_remaining;
static unsigned char l_len,l_at,l_col;
static const char l_mn0[]=
 "addadcandcmpeorldaorasbcstasubxor"
 "asldecinclsrrolror"
 ".ifwhlbrabccbcsbeqbflbgebltbmibnebplbtrbvcbvsjsrobjorgphs"
 ".mdfzrinplclrls"
 "bitcpxcpyjmpldxldystxstytrbtsbstz"
 "=  conepzequset"
 ".daadrbytcspdbyhby"
 "anxsbtttlchnblkdciinvrvsmsgstrzro"
 "dfshexusrsav";
static const char l_mn1[]=
 ".el.fi.me.wedphif1if2endexpgenlstnlsnognoxpagpaunlccnd   "
 "asllsrrolrordecincbrkclccldcliclvdexdeyinxinynopphaphpplaplprti"
 "rtssecsedseitaxtaytsxtxatxstyaphxphyplxply";
typedef char l_mn0_size[sizeof(l_mn0)-234];
typedef char l_mn1_size[sizeof(l_mn1)-162];
static void l_put(unsigned char c){rt_put(c);if(l_col<255)++l_col;}
static void l_text(const char* s){while(*s)l_put(*s++);}
static void l_tab(unsigned char c){if(l_col>=c)l_put(' ');else while(l_col<c)l_put(' ');}
static unsigned char l_get(void){
 if(l_at>=l_len){rt_invalid();return 0;}
 return l_line[l_at++];
}
static void l_symbol(unsigned int index){
 unsigned int off;
 unsigned char i,j,c;
 if(index>=l_count){rt_invalid();return;}
 off=index*6;
 for(i=0;i<2;++i){
  for(j=0;j<4;++j){
   if(j==0)c=l_symbols[off]>>2;
   else if(j==1)c=((l_symbols[off]<<4)&60)|(l_symbols[off+1]>>4);
   else if(j==2)c=((l_symbols[off+1]<<2)&60)|(l_symbols[off+2]>>6);
   else c=l_symbols[off+2]&63;
   if(c==32)return;
   l_put(c<32?c|64:c);
  }
  off+=3;
 }
}
static void l_ref(unsigned char c){unsigned int n=l_get();l_symbol(n|((unsigned int)(c&1)<<8));}
static void l_mnemonic(unsigned char c){
 unsigned int off;
 const char* p;
 unsigned char i;
 if(c<0x4E){p=l_mn0;off=(unsigned int)c*3;}
 else if(c>=0xB0 && c<0xE6){p=l_mn1;off=(unsigned int)(c-0xB0)*3;}
 else {rt_invalid();return;}
 for(i=0;i<3;++i)l_put(p[off+i]);
}
static void l_comment(unsigned char mode){
 if(mode==4)l_text(",X");else if(mode==8)l_text(",Y");
 else if(mode==16)l_put(')');else if(mode==32)l_text(",X)");
 else if(mode==64)l_text("),Y");
 if(l_at<l_len){l_tab(40);l_put(';');while(l_at<l_len)l_put(l_get()&127);}
}
static void l_decimal(unsigned int n){
 unsigned int div=10000;
 unsigned char leading=0,c;
 while(div){c=n/div;n%=div;div/=10;if(c || leading || !div){l_put('0'+c);leading=1;}}
}
static void l_hex(unsigned char n){
 static const char digits[]="0123456789ABCDEF";
 l_put(digits[n>>4]);l_put(digits[n&15]);
}
static void l_binary(unsigned char n){unsigned char mask;for(mask=128;mask;mask>>=1)l_put(n&mask?'1':'0');}
/* Return 1 to expect another operand (prefix), otherwise an operator. */
static unsigned char l_number(unsigned char c,unsigned char mode){
 unsigned char n,hi,quote;
 unsigned int v;
 if(c<0x1A){l_put('0'|c);}
 else if(c<=0x1F){
  n=l_get();hi=0;if(c&1)hi=l_get();
  if(rt_bad)return 0;
  if(c<0x1C){v=(unsigned int)n|((unsigned int)hi<<8);l_decimal(v);}
  else if(c<0x1E){l_put('$');if(c&1)l_hex(hi);l_hex(n);}
  else {l_put('%');l_binary(n);if(c&1)l_binary(hi);}
 }else if(c>=0x36 && c<=0x39){l_put(c<0x38?'#':'/');l_ref(c);}
 else if(c==0x3C)l_put('*');
 else if(c>=0x40 && c<0x4A){l_put('<');l_put(c-0x10);}
 else if(c>=0x4A && c<0x50){l_put('?');l_put(c-0x1A);}
 else if(c>=0x50 && c<0x5A){l_put('>');l_put(c-0x20);}
 else if(c>=0x5A && c<0x60){
  n=c-0x24;l_put('?');l_put(n==';'?'#':n);return n==':';
 }else if(c>=0x60 && c<0x80){
  n=c&31;if(!n)n=l_get();
  if(rt_bad || n>l_len-l_at){rt_invalid();return 0;}
  quote=n && l_line[l_at]>=128?'"':'\'';l_put(quote);
  while(n--){c=l_get()&127;if(c==quote)l_put(quote);l_put(c);}l_put(quote);
 }else if(c==0xFA || c==0xFB)l_ref(c);
 else if(c==0xFF){l_comment(mode);}
 else rt_invalid();
 return 0;
}
static void l_operand(unsigned char mnemonic){
 static const char op1[]="+-*/&|^=<>%<><";
 unsigned char mode=0,c,operand=1;
 if(mnemonic<0x11 || (mnemonic>=0x29 && mnemonic<0x34)){
  mode=l_get();
  if(mode!=0 && mode!=1 && mode!=2 && mode!=4 && mode!=8 && mode!=16 && mode!=32 && mode!=64 && mode!=128){rt_invalid();return;}
 }
 l_tab(18);if(mode>=16 && mode<128)l_put('(');
 while(l_at<l_len && !rt_bad && !rt_cancel){
  c=l_get();
  if(operand){
   if(c==0x0E)l_put('~');else if(c==0x0F)l_put('-');
   else if(c==0x3A)l_put('#');else if(c==0x3B)l_put('/');else if(c==0x3D)l_put('@');
   else if(c==0xFF){l_comment(mode);return;}
   else operand=l_number(c,mode);
  }else{
   operand=1;
   if(c<14){l_put(' ');l_put(op1[c]);if(c==11 || c==12)l_put('=');else if(c==13)l_put('>');l_put(' ');}
   else if(c>=32 && c<48){l_put('+');operand=l_number(c-16,mode);}
   else if(c==255){l_comment(mode);return;}
   else {l_put(',');--l_at;}
  }
 }
 l_comment(mode);
}
static void l_big(void){
 unsigned char c,m;
 c=l_get();
 if(c>=254){l_put(c==254?'*':';');while(l_at<l_len)l_put(l_get()&127);return;}
 if(c==252 || c==253){l_tab(9);l_put('/');l_ref(c);m=c;}
 else{
  if(c==250 || c==251){l_ref(c);c=l_get();}
  else if(c>=240 && c<=249){l_put('^');l_put(c-192);c=l_get();}
  m=c;l_tab(9);
  if(m==252 || m==253){l_put('/');l_ref(m);}else l_mnemonic(m);
 }
 if(!rt_bad)l_operand(m);
}
static int l_code(void){
 int c;
 if(!l_remaining){rt_invalid();return -1;}
 --l_remaining;c=rt_get();if(c<0)rt_invalid();return c;
}
static unsigned int l_word(void){int lo=rt_get(),hi=rt_get();if(lo<0 || hi<0){rt_invalid();return 0;}return (unsigned int)lo|((unsigned int)hi<<8);}
static void rt_decode(void){
 unsigned int bytes,i,j;
 unsigned char c,k;
 int n;
 if(!strcmp(rt_api.selected->name,"ANIX.EQUATES") || rt_api.selected->type!=0xFA || rt_api.selected->aux<0x1000 || rt_api.selected->aux>=0x4000){rt_invalid();return;}
 l_remaining=l_word();bytes=l_word();
 if(rt_bad || !l_remaining || bytes>4096 || (bytes&7)){rt_invalid();return;}
 l_count=bytes/8;
 for(i=0;i<l_count;++i){
  for(j=0;j<8;++j){n=rt_get();if(n<0){rt_invalid();return;}if(j<6)l_symbols[i*6+j]=n;}
 }
 while(l_remaining && !rt_bad && !rt_cancel){
  n=l_code();if(n<0)break;c=n;l_col=0;
  if(!c){
   /* EOF may be followed by zero padding inside the declared code size. */
   while(l_remaining && !rt_bad){if(l_code()!=0)rt_invalid();}break;
  }
  if(c<128){
   l_len=c-1;l_at=0;
   if(!l_len || l_len>l_remaining){rt_invalid();return;}
   for(k=0;k<l_len;++k){n=l_code();if(n<0)return;l_line[k]=n;}
   l_big();
  }else if(c>=254)l_put(c==254?'*':';');
  else if(c>=250){
   n=l_code();if(n<0)return;l_len=1;l_at=0;l_line[0]=n;
   if(c>=252){l_tab(9);l_put('/');l_ref(c);}else {l_ref(c);l_put(':');}
  }else if(c>=240){l_put('^');l_put('0'+c-240);l_put(':');}
  else {l_tab(9);l_mnemonic(c);}
  rt_put(13);
 }
 if(!rt_cancel && !rt_bad){
  /* Native ProDOS EOF must agree with the two header lengths. */
  if(rt_get()>=0)rt_invalid();
 }
}
#endif
