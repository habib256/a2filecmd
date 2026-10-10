/* Newsroom PN/PG structural decoding. Every byte is read in both passes;
 * no neighbouring file is opened, no fonts or bitmap reconstructed. */
static void nr_string(const char* s){while(*s && !rt_cancel)rt_put(*s++);}
static void nr_number(unsigned int n){char s[8];rt_api.sprintf(s,"%u",n);nr_string(s);}
static unsigned char nr_read(unsigned char* p,unsigned int n){
 int c;while(n--){c=rt_get();if(c<0){rt_invalid();return 0;}*p++=c;}return 1;
}
static void nr_name(const unsigned char* p){unsigned char i;for(i=0;i<8 && p[i];++i)rt_put(p[i]&127);}
#if RT_FORMAT == 7
static void rt_decode(void){
 unsigned char h[7],v[8],i,c;unsigned int n,k;int raw;
 if(!nr_read(h,7))return;
 n=(unsigned int)h[0]|((unsigned int)h[1]<<8);
 if(h[2]>2 || h[3]>1){rt_invalid();return;}
 nr_string("Newsroom panel: ");nr_number(n);nr_string(" text bytes, ");nr_number(h[6]);nr_string(" photos\r");
 nr_string("Text recovered; original fonts and photo placement are not rendered.\r\r");
 /* Original MD2 $60AD: ordering n bytes, n rectangles, n 8-byte names.
  * The text pointer is $4007 + 13*n. */
 for(k=0;k<(unsigned int)h[6]*5;++k)if(rt_get()<0){rt_invalid();return;}
 for(i=0;i<h[6];++i){if(!nr_read(v,8))return;nr_string("Photo: PH.");nr_name(v);rt_put(13);}
 if(h[6])rt_put(13);
 for(k=0;k<n && !rt_cancel;++k){
  raw=rt_get();if(raw<0){rt_invalid();return;}c=raw&127;
  /* $7F/$FF is the text end/cursor sentinel, not a printable glyph. */
  if(c==127)continue;
  if(c!=13 && (c<32 || c>=127)){rt_invalid();return;}rt_put(c);
 }
 if(!rt_cancel && rt_get()>=0)rt_invalid();
}
#else
static void rt_decode(void){
 unsigned char p[99],i,slots,layout;
 if(!nr_read(p,99))return;
 if(rt_get()>=0 || p[0]>3){rt_invalid();return;}
 layout=p[0];slots=7+layout;
 nr_string("Newsroom page: ");nr_name(p+81);rt_put(13);
 nr_string(layout<2?"Letter":"Legal");nr_string(layout&1?", without banner\r":", with banner\r");
 nr_string("Component slots in stored order (size codes from the original layout):\r\r");
 for(i=0;i<slots && !rt_cancel;++i){
  nr_number(i+1);nr_string(": ");
  if(!i && !(layout&1))nr_string("BN.");else nr_string("PN.");
  if(p[1+i*8])nr_name(p+1+i*8);else nr_string("(empty)");
  nr_string("  size code ");nr_number(p[89+i]);rt_put(13);
 }
 nr_string("\rThis is the decoded layout; neighbouring components are not rendered.");
}
#endif
