/* Qualified B00 profile: fixed 1K header, 512-byte row/column labels,
 * six-byte decimal cells padded to 512, row/column formula blocks and
 * two opaque 512-byte settings blocks. No evaluation or disk/AUX writes.
 * Shared preflight completes physical reads and close before rendering. */
static unsigned char pp_rows[512],pp_cols[512],pp_head[34];
static unsigned int pp_ro[32],pp_co[16];
static unsigned char pp_nr,pp_nc;
static unsigned int pp_word(const unsigned char* p){return (unsigned int)p[0]|((unsigned int)p[1]<<8);}
static unsigned char pp_read(unsigned char* p,unsigned int n){
 int c;while(n--){c=rt_get();if(c<0){rt_invalid();return 0;}*p++=c;}return 1;
}
static unsigned char pp_ascii(const unsigned char* p,unsigned int n){
 while(n--)if(*p<32 || *p++>=127){rt_invalid();return 0;}return 1;
}
static void pp_text(const unsigned char* p,unsigned int n){while(n-- && !rt_cancel)rt_put(*p++);}
static unsigned char pp_zero(const unsigned char* p,unsigned int n){
 while(n--)if(*p++){rt_invalid();return 0;}return 1;
}
static void pp_title(char kind,unsigned int index){
 char b[12];unsigned char i;rt_api.sprintf(b,"%c%u ",kind,index);for(i=0;b[i];++i)rt_put(b[i]);
}
static unsigned char pp_labels(void){
 unsigned int at=0,n,j,end;unsigned char i,l;
 for(i=0;i<pp_nr;++i){
  if(at>507){rt_invalid();return 0;}l=pp_rows[at+4];
  if(l>507-at || !pp_ascii(pp_rows+at+5,l)){rt_invalid();return 0;}
  pp_ro[i]=at;at+=5+l;
 }
 if(!pp_zero(pp_rows+at,512-at))return 0;
 at=0;
 for(i=0;i<pp_nc;++i){
  if(at>502){rt_invalid();return 0;}n=pp_word(pp_cols+at+6);
  if(n<8 || n>506-at || pp_cols[at+8]!=1){rt_invalid();return 0;}
  end=at+6+n;l=pp_cols[at+9];j=at+10+l;
  if(j>end || !pp_ascii(pp_cols+at+10,l)){rt_invalid();return 0;}
  /* Primary label followed by one of the three observed heading forms.
   * Group metadata is bounded but not interpreted as column coordinates. */
  if(end-j==4 && (pp_cols[j]==1 || pp_cols[j]==3) && pp_cols[j+2]==1 && !pp_cols[j+3]){
   if(pp_cols[j]==1 && pp_cols[j+1]){rt_invalid();return 0;}
  }else if(end-j>=10 && pp_cols[j]==2){
   l=pp_cols[j+7];
   if(end-j!=10U+l || pp_cols[end-2]!=1 || pp_cols[end-1] || !pp_ascii(pp_cols+j+8,l)){rt_invalid();return 0;}
  }else{rt_invalid();return 0;}
  pp_co[i]=at;at=end;
 }
 return pp_zero(pp_cols+at,512-at);
}
static void pp_colname(unsigned char i){
 unsigned int at=pp_co[i];pp_text(pp_cols+at+10,pp_cols[at+9]);
}
/* Five packed BCD bytes, decimal point exponent in low four bits.
 * $20 is zero, bit $10 sign and $40 a stored formula result. Blank has
 * $A0 in byte zero. Fixed decimal text preserves all ten stored digits. */
static unsigned char pp_number(unsigned char* p){
 unsigned char i,n,digit[10],last=10,flags=p[5];int exponent;
 if(p[0]==0xA0){
  if(!pp_zero(p+1,4) || (flags&~0x40)){rt_invalid();return 0;}
  pp_text((const unsigned char*)"[blank]",7);return 1;
 }
 for(i=0;i<5;++i){
  if((p[i]>>4)>9 || (p[i]&15)>9){rt_invalid();return 0;}
  digit[i*2]='0'+(p[i]>>4);digit[i*2+1]='0'+(p[i]&15);
 }
 if(flags&128){rt_invalid();return 0;}
 exponent=flags&63;
 if(exponent==32){if(!pp_zero(p,5)){rt_invalid();return 0;}rt_put('0');return 1;}
 if(digit[0]=='0'){rt_invalid();return 0;}
 if(flags&32 || (flags&15)>10){rt_invalid();return 0;}
 exponent=flags&15;
 while(last>1 && digit[last-1]=='0')--last;
 if(flags&16)rt_put('-');
 if(exponent<=0){rt_put('0');rt_put('.');for(n=0;n<(unsigned char)-exponent;++n)rt_put('0');}
 for(i=0;i<last;++i){if(exponent>0 && i==exponent)rt_put('.');rt_put(digit[i]);}
 if(exponent>last)for(i=last;i<exponent;++i)rt_put('0');
 return 1;
}
static unsigned char pp_formulas(unsigned char count,char kind){
 unsigned int at=0;unsigned char i,n;
 if(!pp_read(pp_rows,512))return 0;
 for(i=0;i<count;++i){
  if(at>=512 || !(n=pp_rows[at]) || n>512-at || !pp_ascii(pp_rows+at+1,n-1)){rt_invalid();return 0;}
  if(n>1){pp_title(kind,i+1);pp_text((const unsigned char*)"formula: ",9);pp_text(pp_rows+at+1,n-1);rt_put(13);}
  at+=n;if(rt_cancel)return 1;
 }
 return pp_zero(pp_rows+at,512-at);
}
static void rt_decode(void){
 unsigned int i,j,cells,padded;unsigned char r,c,value[6];int v;
 if(rt_api.selected->type!=0x16 || rt_api.selected->aux!=4){rt_invalid();return;}
 if(!pp_read(pp_head,34))return;
 for(i=0;i<10;++i)if(pp_head[24+i]!="Plan  \003B00"[i]){rt_invalid();return;}
 i=pp_word(pp_head);j=pp_word(pp_head+2);
 if(!i || i>32 || !j || j>16){rt_invalid();return;}
 pp_nr=i;pp_nc=j;
 for(i=34;i<1024;++i)if(rt_get()<0){rt_invalid();return;}
 if(!pp_read(pp_rows,512) || !pp_read(pp_cols,512) || !pp_labels())return;
 pp_text((const unsigned char*)"Stored values; no recalculation",31);rt_put(13);
 cells=(unsigned int)pp_nr*pp_nc*6;padded=(cells+511)&~511U;
 for(r=0;r<pp_nr && !rt_cancel;++r){
  pp_title('R',r+1);i=pp_ro[r];pp_text(pp_rows+i+5,pp_rows[i+4]);rt_put(13);
  for(c=0;c<pp_nc && !rt_cancel;++c){
   if(!pp_read(value,6))return;
   rt_put(' ');pp_title('C',c+1);pp_colname(c);pp_text((const unsigned char*)" = ",3);
   if(!pp_number(value))return;
   if(value[5]&64)pp_text((const unsigned char*)" [formula]",10);
   rt_put(13);
  }
 }
 if(rt_cancel)return;
 for(i=cells;i<padded;++i){v=rt_get();if(v!=0){rt_invalid();return;}}
 if(!pp_formulas(pp_nr,'R') || rt_cancel || !pp_formulas(pp_nc,'C') || rt_cancel)return;
 /* Per-cell formula area is empty in this profile. Do not silently hide it. */
 for(i=0;i<512;++i){v=rt_get();if(v!=0){rt_invalid();return;}}
 /* Printer/display settings are opaque; still require all physical bytes. */
 for(i=0;i<512;++i)if(rt_get()<0){rt_invalid();return;}
 if(rt_get()>=0)rt_invalid();
}
