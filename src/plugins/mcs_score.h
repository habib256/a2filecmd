/* Read-only editor-score import. Both files must validate and close before
 * the caller starts the card. Only MAIN song/BSS/copy_buf are written.
 * Reconstructed from the Apple II editor; no editor code is executed. */
#ifndef MS_DOS
static char ms_path[PATH_LEN+NAME_LEN];
#define ms_read(p,n,f) (frd(p,1,n,f)==(n)&&!ferror(f))
#define ms_eof(f) (!frd(A->copy_buf,1,1,f)&&!ferror(f))
#define ms_close(f) (!fcls(f))
#endif
static unsigned char ms_key[38],ms_acc[38],ms_dot[38];
static unsigned char ms_now[4],ms_next[4],ms_signature;
static unsigned int ms_records[2],ms_used[2],ms_duration[2];
static const unsigned char ms_ladder[38]={
 0,1,2,4,6,8,9,11,13,14,16,18,20,21,23,25,26,28,30,32,
 33,35,37,38,40,42,44,45,47,49,50,52,54,56,57,59,61,255};
static const unsigned char ms_durations[10]={2,4,8,16,32,2,4,8,16,32};
static const unsigned char ms_dotted[10]={3,6,12,24,48,3,6,12,24,48};
static const unsigned char ms_bars[4]={16,32,24,24};
static unsigned int ms_word(const unsigned char* p){return (unsigned int)p[0]|((unsigned int)p[1]<<8);}
static unsigned char ms_note(unsigned char k){return k<5||k==18||(k>=21&&k<26);}
static unsigned char ms_pair(unsigned char pitch,unsigned char flags,unsigned char s){
 unsigned int at;
 if(ms_used[s]>STAFF_SIZE-4)return 0;
 at=(s?STAFF_SIZE:0)+ms_used[s];SONG[at]=pitch;SONG[at+1]=flags;
 ms_used[s]+=2;
 if(!(flags&128))ms_duration[s]+=flags&63;
 return 1;
}
static unsigned char ms_staff(FILE* f,unsigned char staff){
 unsigned int i,x,previous=0;unsigned char k,y,orig,d,tie=0,oct=0,permanent=0,chord,z,m;
 int clef=staff?-13:7,idx,pitch;
 memset(ms_key,0,38);memset(ms_acc,0,38);memset(ms_dot,0,38);
 if(!ms_read(ms_now,4,f))return 0;
 for(i=0;i<ms_records[staff];++i){
  if(!ms_read(ms_next,4,f))return 0;
  k=orig=ms_now[0];y=ms_now[1];x=ms_word(ms_now+2);
  if(k>31||x<previous||x>0x3FFF||y>37)return 0;
  previous=x;
  if(k==31){if(y!=10)return 0;memset(ms_acc,0,38);memset(ms_dot,0,38);oct=0;}
  else {
   if((!staff&&y>=19)||(staff&&y<19))return 0;
   if(k>=10&&k<=12){
    ms_acc[y]=k;
    if(x<80){
     idx=(int)y+clef;if(idx<0||idx>=37)return 0;m=ms_ladder[idx]%12;
     for(z=staff?19:0;z<(staff?38:19);++z){idx=(int)z+clef;
      if(idx>=0&&idx<37&&ms_ladder[idx]%12==m)ms_key[z]=k;}
    }
   }else if(k==13)ms_dot[y]=1;
   else if(k==14){oct=1;if(x<80)permanent=1;}
   else if(k==15)clef=staff?-13:7;
   else if(k==16)clef=staff?-1:19;
   else if(k==17||k==26)tie=64;
   else {
    if(k>=21&&k<=24)k-=21;else if(k==25)k=18;
    if(k>=10&&k!=18&&k!=19)return 0;
    pitch=62;
    if(ms_note(orig)){
     idx=(int)y+clef;if(idx<0||idx>=37)return 0;pitch=ms_ladder[idx];
     if(oct||permanent){pitch-=12;if(pitch<0)pitch=0;}
     /* The original exporter adds local and key-signature accidentals;
      * a natural suppresses both. Preserve that behaviour. */
     if(ms_acc[y]!=10){
      if(ms_acc[y]==11)--pitch;else if(ms_acc[y]==12)++pitch;
      if(ms_key[y]==11)--pitch;else if(ms_key[y]==12)++pitch;
     }
     if(pitch<0||pitch>=62)return 0;
    }
    d=k>=18?1:ms_dot[y]?ms_dotted[k]:ms_durations[k];
    if(k==9)d=ms_bars[ms_signature];ms_dot[y]=0;
    chord=ms_note(ms_next[0])&&ms_next[2]==ms_now[2]&&ms_next[3]==ms_now[3];
    /* The published exporter encodes ties from staff 0 for both streams;
     * staff 0's flag is cleared before staff 1. Match its emitted bytes. */
    if(!ms_pair((unsigned char)(pitch*2),d|(staff?0:tie)|(chord?128:0),staff))return 0;
    if(!chord)tie=0;
   }
  }
  memcpy(ms_now,ms_next,4);
 }
 /* Saved end pointers designate one unprocessed four-byte slot. Some
  * editor saves leave stale object bytes there rather than a final bar. */
 if(!ms_eof(f))return 0;
 return 1;
}
static unsigned char ms_score(FILE* f){
 unsigned char s,n,ok;unsigned int end,base,gap,max;
 /* copy_buf contains the entire fresh 256-byte state header. */
 if(A->copy_buf[122]||A->copy_buf[123]||A->copy_buf[124]!=0x41||
    A->copy_buf[125]!=0x74||A->copy_buf[126]>3)goto refused;
 ms_signature=A->copy_buf[126];
 for(s=0;s<2;++s){
  base=s?0x7400:0x4100;end=A->copy_buf[118+s]|((unsigned int)A->copy_buf[120+s]<<8);
  if(end<base+4||end>=base+0xB00||((end-base)&3))goto refused;
  ms_records[s]=(end-base)/4;ms_used[s]=ms_duration[s]=0;
 }
 memset(SONG,0,LIMIT);ok=ms_staff(f,0);
 if(!ms_close(f))ok=0;
 if(!ok)return 0;
#ifdef MS_DOS
 if(!md_next())return 0;
#else
 n=strlen(ms_path);if(n+4>=sizeof ms_path)return 0;
 strcpy(ms_path+n,".OBJ");f=fopn(ms_path,"rb");if(!f)return 0;
#endif
 ok=ms_staff(f,1);if(!ms_close(f))ok=0;if(!ok)return 0;
 max=ms_duration[0]>ms_duration[1]?ms_duration[0]:ms_duration[1];if(!max)return 0;
 /* A silent/shorter staff must not end the whole exported player early.
  * Pad it to the longer staff with the player's ultrasonic rest. */
 for(s=0;s<2;++s){gap=max-ms_duration[s];
  while(gap){n=gap>63?63:(unsigned char)gap;if(!ms_pair(124,n,s))return 0;gap-=n;}
 }
 return valid();
refused:
#ifndef MS_DOS
 ms_close(f);
#endif
 return 0;
}
