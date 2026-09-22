/* dos33_copy.h -- one ProDOS file written onto a DOS 3.3 volume, sector by
 * sector, shared by the overlays that put one there: DOSWRITE (a new name),
 * DOSIMAGE (the same inside an image) and DOS33W (replacing a file that is
 * already on the disk).
 *
 * The caller has audited the volume, reserved what it needs in `allocation`
 * and settled `sectors`, `lists`, `length`, `prefix`, `address` and `kind`.
 * What is here writes the data sectors, then the track/sector lists, then
 * reads the whole thing back against the source a second time: a file is
 * never announced on the strength of the writes alone.
 *
 * `allocated(n)` is the n-th reserved sector in ascending order. A bitmap of
 * seventy bytes saves 450 over a list of 260 sector numbers, and the order
 * is what makes the lists and the data line up.
 *
 * The source is opened, read and closed once per pass and never held across
 * one: a file left open through a failure is a file the cleanup cannot
 * remove. dos33_fs.h must be included first -- read_sector and write_sector
 * come from there.
 */

static unsigned int allocated(unsigned int index) {
 unsigned int s;
 for(s=48;s<560;++s)if(allocation[s>>3]&mask(s)) {if(!index)return s;--index;}
 return 560;
}
#ifdef PLUGIN_HOST
static void reserve(void) {
 unsigned int s;
 for(s=48;s<560;++s)if(allocation[s>>3]&mask(s))vtoc[bitpos(s)]&=~mask(s);
}
#else
/* The same, track by track: bitpos() puts sectors 0-7 of track t at
 * $39+4t and 8-15 at $38+4t, under the masks allocation[2t] and [2t+1]
 * already use. cc65 makes some 90 bytes of the C; this is 30. */
static void reserve(void) {
 asm("ldx #6");                      /* allocation: track 3 */
 asm("ldy #$44");                    /* vtoc: $38 + 4 * 3 */
 asm("rs1: lda %v,x", allocation);
 asm("eor #$FF");
 asm("and %v+1,y", vtoc);
 asm("sta %v+1,y", vtoc);
 asm("lda %v+1,x", allocation);
 asm("eor #$FF");
 asm("and %v,y", vtoc);
 asm("sta %v,y", vtoc);
 asm("iny");
 asm("iny");
 asm("iny");
 asm("iny");
 asm("inx");
 asm("inx");
 asm("cpx #70");
 asm("bne rs1");
}
#endif
static unsigned char source_length(void) {
 unsigned int n;unsigned long total=0;
 source=RF(fopen)(a.full,"rb");if(!source)return 0;
 do {n=RF(fread)(data,1,256,source);total+=n;}while(n==256 && total<=65535UL && !stop());
 n=ferror(source) || total>65535UL || cancelled;
 if(RF(fclose)(source))n=1;source=NULL;
 length=(unsigned int)total;return !n;
}
/* Produce the exact DOS byte stream, with its native BIN/BASIC prefix. */
static unsigned char chunk(unsigned int index,unsigned int* left) {
 unsigned int off=0,n;
 a.memset(data,0,256);
 if(!index && prefix) {
  if(prefix==4){wr16(data,address);off=2;}
  wr16(data+off,length);off+=2;
 }
 n=*left>256-off?256-off:*left;
 if(RF(fread)(data+off,1,n,source)!=n || ferror(source))return 0;
 *left-=n;return 1;
}
static unsigned char end_source(unsigned int left) {
 unsigned char ok=!left && !RF(fread)(data,1,1,source) && !ferror(source);
 if(RF(fclose)(source))ok=0;source=NULL;return ok;
}
static unsigned char verify_source(void);
static unsigned char lists_io(unsigned char writing) {
 unsigned int i,j,cur;
#ifndef DOS_IMAGE
 (void)writing;                    /* only the image build reads back */
#endif
 for(i=0;i<lists;++i) {
  a.memset(data,0,256);
  if(i+1<lists){cur=allocated(i+1);data[1]=cur/16;data[2]=cur&15;}
  wr16(data+5,i*122);
  for(j=0;j<122 && i*122+j<sectors;++j) {
   cur=allocated(lists+i*122+j);data[12+2*j]=cur/16;data[13+2*j]=cur&15;
  }
  #ifdef DOS_IMAGE
  if(!writing) {if(!read_sector(allocated(i),ts) || memcmp(ts,data,256))return 0;}
  else
#endif
  if(!write_sector(allocated(i),data))return 0;
 }
 return 1;
}
static unsigned char transfer(void) {
 unsigned int i,left=length;unsigned char ok;
 source=RF(fopen)(a.full,"rb");if(!source)return 0;
 for(i=0;i<sectors;++i) {
  if(!chunk(i,&left) || !write_sector(allocated(lists+i),data))goto bad;
  a.progress_bar(a.selected->name,i+1,sectors);
 }
 if(!end_source(left))return 0;
 if(!lists_io(1))return 0;
 return verify_source();
bad:
 ok=RF(fclose)(source);source=NULL;(void)ok;return 0;
}
static unsigned char verify_source(void) {
 unsigned int i,left=length;unsigned char ok;
 source=RF(fopen)(a.full,"rb");if(!source)return 0;
 for(i=0;i<sectors;++i) {
  /* the read-back is as long as the writes: the bar starts again at 0 */
  a.progress_bar(a.selected->name,i,sectors);
  if(stop() || !chunk(i,&left) || !read_sector(allocated(lists+i),ts) || memcmp(data,ts,256))goto bad;
 }
 return end_source(left);
bad:
 ok=RF(fclose)(source);source=NULL;(void)ok;return 0;
}
