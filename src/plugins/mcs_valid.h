/* Canonical two-staff validation, shared by import and playback. */
static unsigned char valid(void) {
 unsigned char s,d,chain,seen;
 unsigned int p,base;
 for(s=0;s<2;++s){
  base=s?STAFF_SIZE:0;chain=seen=0;
  for(p=base;p<base+STAFF_SIZE;p+=2){
   d=SONG[p+1];
   if(!(SONG[p]>>1)&&!d){if(chain||!seen)return 0;break;}
   if(SONG[p]>=128 || !(d&63))return 0;
   chain=d&128;seen=1;
  }
  if(p==base+STAFF_SIZE)return 0;
#ifndef MC_VALID_NO_END
  end[s]=p;
#endif
 }
 return 1;
}
