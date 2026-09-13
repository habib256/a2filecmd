/* Physical 35-track, 16-sector Disk II copying. Encoded address/data fields
 * and sector order are retained; FF gaps are regenerated as 10-bit sync.
 * Unsupported framing/checksums/unstable reads FAIL before that track's write.
 * Main $6500-$84FF is borrowed ONLY inside assembly, with IRQs masked and
 * a complete AUX backup. AUX $4000-$BFFF is destroyed after loader consent.
 * No filesystem calls, overlay loads or source writes during the copy.
 */
#include "util.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header { unsigned int magic; unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3]; char desc[48]; };
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG|OVERLAY_AUX,
 plugin_entry,{0,0,0},"Copy Disk II tracks with verified nibble fields"};
#pragma rodata-name(pop)
void __fastcall__ nb_begin(unsigned char);
void nb_end(void),nb_fetch(void),nb_store(void);
unsigned char nb_read(void),nb_write(void),nb_protected(void);
extern unsigned int nb_address;
extern unsigned char *nb_buffer,nb_track,nb_bank;
unsigned char (*nb_cleanup_fn)(void);
extern char *nb_note,nb_ram_note[48];
static unsigned char cache[512],cached[2],bank;
static unsigned int pos,outpos;
struct Track { unsigned int addr[16],data[16]; unsigned char order[16]; };
static struct Track tracks[2];
static const unsigned char gcr[64]={
 0x96,0x97,0x9A,0x9B,0x9D,0x9E,0x9F,0xA6,
 0xA7,0xAB,0xAC,0xAD,0xAE,0xAF,0xB2,0xB3,
 0xB4,0xB5,0xB6,0xB7,0xB9,0xBA,0xBB,0xBC,
 0xBD,0xBE,0xBF,0xCB,0xCD,0xCE,0xCF,0xD3,
 0xD6,0xD7,0xD9,0xDA,0xDB,0xDC,0xDD,0xDE,
 0xDF,0xE5,0xE6,0xE7,0xE9,0xEA,0xEB,0xEC,
 0xED,0xEE,0xEF,0xF2,0xF3,0xF4,0xF5,0xF6,
 0xF7,0xF9,0xFA,0xFB,0xFC,0xFD,0xFE,0xFF};
/* Returning zero outside a capture cannot be confused with a disk nibble. */
static unsigned char get(unsigned int p) {
 unsigned char page,which;
 if(p>=8192)return 0;
 page=bank+(p>>8);which=bank==0x60;
 if(cached[which]!=page) {
  nb_address=(unsigned int)page<<8;nb_buffer=cache+256*which;nb_fetch();cached[which]=page;
 }
 return cache[256*which+(p&255)];
}
static unsigned char next(void) { unsigned char v=get(pos);++pos;return v; }
static unsigned char four(void) {
 unsigned char x=next(),y=next();
 if((x&0xAA)!=0xAA || (y&0xAA)!=0xAA)return 0;
 return ((x<<1)|1)&y;
}
static unsigned char epilogue(void) {
 return next()==0xDE && next()==0xAA && next()==0xEB;
}
static unsigned char prologue(unsigned char kind) {
 unsigned int start=pos,sync=0;
 unsigned char x,noise=0;
 while(pos-start<1024) {
  x=get(pos);
  if(x==0xFF){++pos;++sync;continue;}
  if(x==0xD5)break;
  /* The physical write splice can frame a few partial nibbles inside
   * GAP3. Accept at most eight, surrounded by >=16 sync bytes on BOTH
   * sides. Never skip a prologue or tolerate noise inside any field/GAP2. */
  if(kind!=0x96 || x<0x80 || noise==8 || (!noise && sync<16))return 0;
  ++noise;++pos;sync=0;
 }
 if(noise && sync<16)return 0;
 return next()==0xD5 && next()==0xAA && next()==kind;
}
/* Seventeen records prove one complete revolution plus its repeated first
 * record. Duplicates, missing sectors and incorrect physical track are errors.
 * Full encoded fields are compared again in equal(), including checksum bytes.
 */
static unsigned char parse(unsigned char which) {
 struct Track* t=tracks+which;
 unsigned char n,s,v,tr,c,x,j,sum,first;
 unsigned int i,seen,addr,data;
 bank=which?0x60:0x40;cached[0]=cached[1]=0;pos=0;seen=0;first=0;
 while(pos<1024 && !(get(pos)==0xD5 && get(pos+1)==0xAA && get(pos+2)==0x96))++pos;
 if(pos==1024)return 0;
 for(n=0;n<17;++n) {
  if(!prologue(0x96))return 0;
  addr=pos-3;
  /* Check all four-and-four bytes, including those decoding to zero. */
  for(i=pos;i<pos+8;++i)if((get(i)&0xAA)!=0xAA)return 0;
  v=four();tr=four();s=four();c=four();
  if(tr!=nb_track || s>=16 || (v^tr^s)!=c || !epilogue())return 0;
  if(!n)first=s;
  if(n==16) { if(s!=first || seen!=65535U)return 0; }
  else {
   if(seen&(1U<<s))return 0;
   seen|=1U<<s;t->addr[s]=addr;t->order[n]=s;
  }
  if(!prologue(0xAD))return 0;
  data=pos-3;sum=0;
  for(i=0;i<343;++i) {
   x=next();for(j=0;j<64 && gcr[j]!=x;++j);
   if(j==64)return 0;
   sum^=j;
  }
  if(sum || !epilogue())return 0;
  if(n==16) {
   for(i=0;i<14;++i)if(get(addr+i)!=get(t->addr[s]+i))return 0;
   for(i=0;i<349;++i)if(get(data+i)!=get(t->data[s]+i))return 0;
  } else t->data[s]=data;
 }
 return 1;
}
static unsigned char equal(void) {
 unsigned char s,j,k,x;
 unsigned int i;
 for(k=0;k<16 && tracks[1].order[k]!=tracks[0].order[0];++k);
 if(k==16)return 0;
 for(j=0;j<16;++j)if(tracks[0].order[j]!=tracks[1].order[(j+k)&15])return 0;
 for(s=0;s<16;++s)for(i=0;i<363;++i) {
  bank=0x40;x=get(i<14?tracks[0].addr[s]+i:tracks[0].data[s]+i-14);
  bank=0x60;if(x!=get(i<14?tracks[1].addr[s]+i:tracks[1].data[s]+i-14))return 0;
 }
 return 1;
}
static void emit(unsigned char v) {
 buf[outpos&255]=v;++outpos;
 if(!(outpos&255)) {
  nb_address=0x8000+outpos-256;nb_buffer=buf;nb_store();
 }
}
static void gap(unsigned int n) { while(n--)emit(0x7F); }
static void build(void) {
 unsigned char n,s;unsigned int i;
 bank=0x40;cached[0]=cached[1]=0;outpos=0;
 /* 782 leading sync bytes (writer starts at offset $32), 16 records,
  * six sync bytes before data and eight between sectors. Last EB ends
  * 56 bytes before Q7 stops: it must finish shifting out. At 1 MHz the
  * interval from the first address to Q7-off is 196736 cycles, below a
  * 300 RPM revolution, including the tail. Long leading sync absorbs
  * the overwrite splice. See docs/NIBCOPY.md for the timing budget. */
 gap(832);
 for(n=0;n<16;++n) {
  s=tracks[0].order[n];
  for(i=0;i<14;++i)emit(get(tracks[0].addr[s]+i));
  gap(6);
  for(i=0;i<349;++i)emit(get(tracks[0].data[s]+i));
  gap(8);
 }
 gap(8192-outpos);
}
static unsigned char capture(unsigned char which) {
 nb_bank=which?0x60:0x40;
 return !nb_read() && parse(which);
}
/* Disk II ROM signature only, never SmartPort or /RAM. */
static unsigned char controller(unsigned char slot) {
#ifdef PLUGIN_HOST
 return slot==6;
#else
 const unsigned char* r=(const unsigned char*)(0xC000+((unsigned int)slot<<8));
 return r[1]==0x20 && r[3]==0 && r[5]==3 && r[0xFF]==0;
#endif
}
static unsigned char key(const char* text) {
 unsigned char k;
 a.message(text);
 do{k=a.cgetc();}while(k!=KEY_RETURN && k!=KEY_ESC);
 return k==KEY_RETURN;
}
unsigned char __fastcall__ nb_run(const struct A2fcApi* api) {
 unsigned char slot,source,target,single,done,dirty,r,k;
 const char* status;
 init(api);nb_cleanup_fn=api->ram_format;done=dirty=0;nb_track=0;status="Cancelled";
 a.message("\1NIBCOPY: Disk II slot 1-7 (ESC cancels)");
 do{k=a.cgetc();if(k==KEY_ESC)return 0;}while(k<'1'||k>'7');
 slot=k-'0';if(!controller(slot)){note("Not a supported Disk II controller.");return 0;}
 a.message("\1Source drive: 1 or 2 (ESC cancels)");
 do{k=a.cgetc();if(k==KEY_ESC)return 0;}while(k!='1'&&k!='2');
 source=(slot<<4)|(k=='2'?0x80:0);
 a.message("\1Target drive: 1 or 2 (same = disk exchanges, ESC cancels)");
 do{k=a.cgetc();if(k==KEY_ESC)return 0;}while(k!='1'&&k!='2');
 target=(slot<<4)|(k=='2'?0x80:0);single=source==target;
 a.clrscr();
 a.cprintf("NIBCOPY S%u,D%u -> S%u,D%u\r\n",slot,(source>>7)+1,slot,(target>>7)+1);
 a.cputs("35 tracks, standard 16-sector fields. No copy protections.\r\n"
          "Use normal 1 MHz speed; disable accelerators.\r\n"
          "WRITE-PROTECT SOURCE (cover notch). Keep it protected.\r\n"
          "Remove BOOT/tools; use a disposable target.\r\n"
          "ALL target files, including locked files, will be destroyed.\r\n"
          "No recovery after a failed write or power cut.\r\n");
 if(!key("\1Insert WRITE-PROTECTED SOURCE. RETURN ready, ESC cancels"))goto end;
 nb_begin(source);
 if(!nb_protected()){status="Source must be write-protected";goto motor;}
 nb_end();
 for(nb_track=0;nb_track<35;++nb_track) {
  a.progress_bar("NIBCOPY (ESC cancels between tracks)",nb_track,35);
  if(stop())goto end;
  if(single && nb_track && !key("\1Insert WRITE-PROTECTED SOURCE. RETURN ready, ESC cancels"))goto end;
  nb_begin(source);
  if(!nb_protected()){status="Source must be write-protected";goto motor;}
  dirty=1;
  if(!capture(0)||!capture(1)||!equal()){status="Source read/format/instability error";goto motor;}
  nb_end();build();
  /* Reconfirm the exact drive before its first write and EACH single-drive
   * exchange. Hardware protection is checked again inside the write loop. */
  if(single || !done) {
   a.sprintf(a.other_full,"Erase TARGET S%u,D%u ALL files? Insert target; Y confirms",slot,(target>>7)+1);
   if(!a.confirm(a.other_full))goto end;
  }
  if(stop())goto end;
  nb_begin(target);
  if(nb_protected()){status="Target protected; nothing written on this track";goto motor;}
  r=nb_write();
  if(r || !capture(1) || !equal()){status="WRITE/VERIFY FAILED; target incomplete";goto motor;}
  nb_end();++done;
 }
 status="Copy verified";
 goto end;
motor:nb_end();
end:
 nb_note=a.note;
 a.sprintf(nb_ram_note,"/RAM not rebuilt; %u/35 tracks verified.",done);
 a.sprintf(a.note,"%s; %u/35 tracks verified.",status,done);
 return dirty;
}
