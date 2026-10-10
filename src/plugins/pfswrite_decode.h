/* Qualified ProDOS profile: 1024-byte settings, LE text size at 8,
 * CR count at 6, initial FF/CR and final $0E. Settings remain opaque.
 * High-bit printable characters and embedded controls are exposed, rather
 * than guessing printer commands, styles or database merge semantics. */
static void rt_decode(void){
 unsigned int i,length=0,lines=0,count=0;
 int c;
 unsigned char lo=0;
 if(rt_api.selected->type!=0x16 || rt_api.selected->aux!=2){rt_invalid();return;}
 for(i=0;i<1024;++i){
  c=rt_get();if(c<0){rt_invalid();return;}
  if(i==6 || i==8)lo=c;
  if(i==7)lines=(unsigned int)lo|((unsigned int)c<<8);
  if(i==9)length=(unsigned int)lo|((unsigned int)c<<8);
 }
 if(length<3 || length>64511U){rt_invalid();return;}
 for(i=0;i<length && !rt_cancel;++i){
  c=rt_get();if(c<0){rt_invalid();return;}
  if(i==0){if(c!=12){rt_invalid();return;}continue;}
  if(i==1 && c!=13){rt_invalid();return;}
  if(i==length-1){if(c!=14){rt_invalid();return;}continue;}
  if(!c || c==14 || c==127 || c==255){rt_invalid();return;}
  if(c==13){++count;rt_put(13);}
  else if(c>=32 && (c&127)>=32)rt_put(c&127);
  else {rt_put('^');rt_put((c&31)+64);}
 }
 if(!rt_cancel && (count!=lines || rt_get()>=0))rt_invalid();
}
