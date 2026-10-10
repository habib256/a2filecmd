/* Independent decoders derived from original Apple II files. WordPerfect
 * control meanings cross-checked with libwpd's WP42Parser (no copied code).
 * Apple II $DC has six operands, unlike the DOS WP4.2 variable group.
 * Unknown controls remain visible; unknown multibyte groups are refused.
 * A complete first pass, including close, precedes text display. */
static void vw_control(unsigned char c){rt_put('^');rt_put(c==127?'?':c+64);}
#if RT_FORMAT == 17
static const unsigned char wp_len[33]={
 4,2,1,3,3,4,2,4,255,40,255,4,2,255,255,1,
 4,255,255,255,255,2,255,255,255,255,2,255,6,255,2,255,2};
static void rt_decode(void){
 int c,v;unsigned char i,count,note=0,seen=0;
 if(rt_api.selected->type!=0xA0 || rt_api.selected->aux){rt_invalid();return;}
 while(!rt_cancel && (c=rt_get())>=0){
  if(rt_off>65535UL){rt_invalid();return;}
  if(c==0xD2){
   if(note){rt_put(']');note=0;continue;}
   /* Apple II embedded note: five framing bytes, then ordinary text. */
   if(rt_get()!=1 || rt_get()<0 || rt_get()!=255 || rt_get()<0 || rt_get()<0){rt_invalid();return;}
   rt_put('[');note=1;continue;
  }
  if(c>=0xC0){
   if(c>0xE0 || (count=wp_len[c-0xC0])==255){rt_invalid();return;}
   for(i=0;i<count;++i)if((v=rt_get())<0){rt_invalid();return;}
   if(rt_get()!=c){rt_invalid();return;}continue;
  }
  if(c>=128){
   /* Layout/style switches do not change the document's plain text.
    * Preserve unqualified single-byte functions explicitly as [HH]. */
   if((c>=0x80 && c<=0x85)||(c>=0x90 && c<=0x95)||(c>=0x9C && c<=0x9F))continue;
   rt_put('[');rt_put("0123456789ABCDEF"[c>>4]);rt_put("0123456789ABCDEF"[c&15]);rt_put(']');
  }else if(c==13)rt_put(' ');
  else if(c==9)rt_spaces(8-(rt_col&7));
  else if(c==10 || c==11 || c==12)rt_put(13);
  else if(c<32 || c==127)vw_control(c);
  else {rt_put(c);seen=1;}
 }
 if(note || !seen)rt_invalid();
}
#else
static unsigned char mw_line[120];
static void rt_decode(void){
 unsigned int i;unsigned char count,end,width=0;int c;
 if(rt_api.selected->type!=0xF1 || rt_api.selected->aux){rt_invalid();return;}
 for(i=0;i<512;++i){
  c=rt_get();if(c<0){rt_invalid();return;}
  if(i==26)width=c;
  if((i==0 && c!='M')||(i==1 && c!='W')||
     (i==2 && c!=1 && c!=4 && c!=5)||(i==3 && c)||
     (i==4 && c!=2)||(i==5 && c && c!=32)||
     (i==26 && (c<1 || c>120))||(i==27 && c)){
   rt_invalid();return;
  }
 }
 while(!rt_cancel && (c=rt_get())>=0){
  mw_line[0]=c;
  for(count=1;count<width;++count){c=rt_get();if(c<0){rt_invalid();return;}mw_line[count]=c;}
  if(rt_off>65535UL){rt_invalid();return;}
  for(count=0;count<width;++count)if(!mw_line[count] || mw_line[count]>=127){rt_invalid();return;}
  end=width;while(end && mw_line[end-1]==' ')--end;
  for(count=0;count<end;++count){
   c=mw_line[count];
   if(c==13)rt_put(13);
   else if(c==9)rt_spaces(8-(rt_col&7));
   else if(c<32)vw_control(c);
   else rt_put(c);
  }
  if(!end || mw_line[end-1]!=13)rt_put(13);
 }
 if(rt_off==512)rt_invalid();
}
#endif
