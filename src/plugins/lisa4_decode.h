/* Bounded streaming adaptation of CiderPress II Lisa4, faddenSoft 2023,
 * Apache-2.0 (data/licenses/NOTICE.TXT). MAIN state only, no source writes. */
static unsigned char v_symbols[2816],v_line[126],v_tabs[3];
static unsigned int v_bytes,v_count;
static unsigned char v_len,v_at,v_col;
static const char v_mn0[]=
 "???addadcandcmpeorldaorasbcstasubxorasldecinclsr"
 "rolror.ifwhl.gobrabccbcsbeqbflbgebltbmibnebplbtr"
 "bvcbvsobjorgphs.dbpeaperbrl.mdfarfdrfzrinplclrls"
 "bitcpxcpyldxldystxstytrbtsbstzpeirepsepjmpjsrjml"
 "jslmvnmvp=  conepdepzeqlequset.daadrbytcspdbyhby"
 "bbyanxchniclliblnkmsgpsmrlbsbtttldcirvsstrzrodfs"
 "hexusrsav.tfsegcpu";
static const char v_mn1[]=
 ".el.fi.me.we.la.lx.sa.sxdphif1if2endexpgenlstnls"
 "nognoxpagpaunlccndasllsrrolrordecincmvnmvpbrkclc"
 "cldcliclvdexdeyinxinynopphaphpplaplprtirtssecsed"
 "seitaxtaytsxtxatxstyaphxphyplxplycopphbphdphkplb"
 "pldrtlstpswatadtastcdtcstdatdctsatsctxytyxwaixba"
 "xce";
static const char* v_long(unsigned char c){switch(c){
 case 102:return ".entry";
 case 103:return ".ref";
 case 104:return ".group";
 case 105:return ".deref";
 case 106:return "long";
 case 108:return ".assume";
 case 127:return ".table";
 case 225:return ".proc";
 case 226:return ".endp";
 case 227:return ".table";
 case 228:return ".endt";
 default:return 0;}}
static void v_put(unsigned char c){rt_put(c);if(v_col<255)++v_col;}
static void v_text(const char* p){while(*p)v_put(*p++);}
static void v_tab(unsigned char n){if(v_col>=v_tabs[n])v_put(' ');else while(v_col<v_tabs[n])v_put(' ');}
static unsigned char v_get(void){if(v_at>=v_len){rt_invalid();return 0;}return v_line[v_at++];}
static unsigned int v_word(void){unsigned int lo=v_get();return lo|((unsigned int)v_get()<<8);}
static unsigned int v_header_word(void){int lo=rt_get(),hi=rt_get();if(lo<0||hi<0){rt_invalid();return 0;}return (unsigned int)lo|((unsigned int)hi<<8);}
static void v_symbol(unsigned int index){
 unsigned int off=0,i;unsigned char n,c;
 if(index>=v_count){rt_invalid();return;}
 for(i=0;i<index;++i)off+=v_symbols[off];
 n=v_symbols[off++]-2;
 while(n--){c=v_symbols[off++];v_put(c<128?c|32:c&127);}
}
static void v_mnemonic(unsigned char c){
 const char* p;unsigned int off;unsigned char i;
 if(c && c<102){p=v_mn0;off=(unsigned int)c*3;}
 else if(c>=144 && c<=224){p=v_mn1;off=(unsigned int)(c-144)*3;}
 else{p=v_long(c);if(!p){rt_invalid();return;}v_text(p);return;}
 for(i=0;i<3;++i)v_put(p[off+i]);
}
static void v_hex(unsigned char c){static const char d[]="0123456789ABCDEF";v_put(d[c>>4]);v_put(d[c&15]);}
static void v_numeric(unsigned char n,unsigned char kind){
 unsigned long value=0;unsigned char b[4],i,mask;static char decimal[11];
 for(i=0;i<n;++i)b[i]=v_get();if(rt_bad)return;
 if(!kind){
  for(i=n;i;--i)value=(value<<8)|b[i-1];
  rt_api.sprintf(decimal,"%lu",value);v_text(decimal);
 }else{
  v_put(kind==1?'$':'%');
  for(i=n;i;--i){if(kind==1)v_hex(b[i-1]);else for(mask=128;mask;mask>>=1)v_put(b[i-1]&mask?'1':'0');}
 }
}
static void v_string(unsigned char n,unsigned char quote){
 unsigned char c;
 if(n>v_len-v_at){rt_invalid();return;}
 if(quote)v_put(quote);
 while(n--){c=v_get()&127;v_put(c);if(quote && c==quote)v_put(c);}
 if(quote)v_put(quote);
}
/* 1 means unary prefix: another operand follows. */
static unsigned char v_number(unsigned char c){
 unsigned char n,q;
 if(c<14){static const char op[]="+-*/&|^=<>%<><";v_put(op[c]);if(c==11 || c==12)v_put('=');else if(c==13)v_put('>');}
 else if(c>=16 && c<=25)v_put('0'+c-16);
 else if(c>=26 && c<=31)v_numeric((c&1)?2:1,(c-26)/2);
 else if(c>=52 && c<=54)v_numeric(3,c-52);
 else if(c==51){
  n=v_get();if(n<=2)v_numeric(4,n);
  else if(n==3){n=v_get();if(n>v_len-v_at){rt_invalid();return 0;}while(n--)v_hex(v_get());}
  else if(n==4){n=v_get();v_string(n,0);}else rt_invalid();
 }else if(c==55 || c==56){
  if(v_at<v_len && v_line[v_at]==250)++v_at;
  v_symbol(v_word());v_text(c==55?":A":":L");
 }else if(c==58 || c==59 || c==60 || c==61 || c==62 || c==63){
  static const char prefixes[]="@#/^|\\";v_put(prefixes[c-58]);return 1;
 }else if(c==14 || c==15){v_put(c==14?'~':'-');return 1;}
 else if(c==57)v_put('*');
 else if(c==49 || c==50){v_put(c==49?'<':'>');v_put(c==49?'<':'>');}
 else if(c>=64 && c<=93){v_put(c<80?(c<74?'<':'?'):(c<90?'>':'?'));v_put('0'+(c<74?c-64:c<80?c-74:c<90?c-80:c-84));}
 else if(c==94){v_text("?:");return 1;}
 else if(c==95)v_text("?#");
 else if(c>=96 && c<=127){
  n=c&31;if(!n)n=v_get();
  if(rt_bad || n>v_len-v_at){rt_invalid();return 0;}
  q=n && v_line[v_at]>=128?'"':'\'';v_string(n,q);
 }else if(c==250)v_symbol(v_word());
 else rt_invalid();
 return 0;
}
static void v_comment(unsigned char mode){
 static const char* const tail[]={"","","",",X",",X",",X","",",S",",Y","),Y",",X)",")",",S),Y","]","],Y",""};
 v_text(tail[mode]);
 if(v_at<v_len){v_tab(2);v_put(';');while(v_at<v_len)v_put(v_get()&127);}
}
static void v_operand(unsigned char m){
 unsigned char mode=0,c,operand=1;
 static const char operators[]="+-*/&|^=<>%<><";
 if(m>=144 && m!=252){
  if(v_at<v_len){if(v_get()!=255){rt_invalid();return;}v_comment(0);}return;
 }
 v_tab(1);
 if(m!=252 && (m<18 || (m>=48 && m<67 && m!=65 && m!=66))){
  mode=v_get();if(rt_bad || mode>15){rt_invalid();return;}
 }
 if(mode>=9 && mode<=12)v_put('(');else if(mode==13 || mode==14)v_put('[');
 while(v_at<v_len && !rt_bad && !rt_cancel){
  c=v_get();if(c==255){v_comment(mode);return;}
  if(operand)operand=v_number(c);
  else{
   operand=1;
   if(c<14 || c==49 || c==50){
    v_put(' ');v_put(c<14?operators[c]:c==49?'<':'>');
    if(c==11 || c==12)v_put('=');else if(c==13)v_put('>');else if(c==49 || c==50)v_put(c==49?'<':'>');v_put(' ');
   }else if(c>=32 && c<=47){v_put('+');operand=v_number(c-16);}
   else {v_put(',');--v_at;}
  }
 }
 v_comment(mode);
}
static void v_big(void){
 unsigned char c,m;
 c=v_get();
 if(c>=253){v_put(c==253?'!':c==254?'*':';');while(v_at<v_len)v_put(v_get()&127);return;}
 if(c==252){v_tab(0);v_put('_');v_symbol(v_word());m=c;}
 else{
  if(c==250){v_symbol(v_word());c=v_get();}
  else if(c>=240 && c<=249){v_put('^');v_put('0'+c-240);c=v_get();}
  m=c;v_tab(0);
  if(m==252){v_put('_');v_symbol(v_word());}else v_mnemonic(m);
 }
 if(!rt_bad)v_operand(m);
}
static void rt_decode(void){
 unsigned int end,i,off=0;int c;unsigned char n,j,seen=0;
 if(rt_api.selected->type!=250 || rt_api.selected->aux<0x4000 || rt_api.selected->aux>=0x6000){rt_invalid();return;}
 v_header_word();end=v_header_word();v_count=v_header_word();
 if(rt_bad || end<16 || end-16>sizeof v_symbols || v_count>(end-16)/2){rt_invalid();return;}
 for(i=6;i<16;++i){c=rt_get();if(c<0){rt_invalid();return;}if(i<9)v_tabs[i-6]=c;}
 if(!v_tabs[0] || v_tabs[0]>=128 || v_tabs[1]<2 || v_tabs[1]>=128 || v_tabs[2]<3 || v_tabs[2]>=128){rt_invalid();return;}
 v_bytes=end-16;
 for(i=0;i<v_bytes;++i){c=rt_get();if(c<0){rt_invalid();return;}v_symbols[i]=c;}
 for(i=0;i<v_count;++i){
  if(off>=v_bytes){rt_invalid();return;}n=v_symbols[off];
  if(n<2 || n>v_bytes-off || v_symbols[off+n-1]){rt_invalid();return;}
  for(j=1;j<n-1;++j)if(!v_symbols[off+j]){rt_invalid();return;}
  off+=n;
 }
 if(off!=v_bytes){rt_invalid();return;}
 while(!rt_bad && !rt_cancel && (c=rt_get())>=0){
  if(rt_off>65535UL){rt_invalid();return;}v_col=0;
  if(!c){seen=1;break;}
  if(c<128){
   v_len=c-1;v_at=0;if(!v_len){rt_invalid();return;}
   for(j=0;j<v_len;++j){c=rt_get();if(c<0){rt_invalid();return;}v_line[j]=c;}
   v_big();
  }else if(c>=240){
   if(c==253){}
   else if(c>=254)v_put(c==254?'*':';');
   else if(c<=249){v_put('^');v_put('0'+c-240);}
   else if(c==250 || c==252){
    if(c==252){v_tab(0);v_put('_');}
    v_len=2;v_at=0;
    for(j=0;j<2;++j){c=rt_get();if(c<0){rt_invalid();return;}v_line[j]=c;}
    v_symbol(v_word());
   }else {rt_invalid();return;}
  }else {v_tab(0);v_mnemonic(c);}
  rt_put(13);seen=1;
 }
 if(!rt_cancel && !rt_bad){
  if(!seen){rt_invalid();return;}
  /* Zero tail padding is accepted, nonzero undeclared content is refused. */
  while((c=rt_get())>=0){if(c || rt_off>65535UL){rt_invalid();return;}}
 }
}
