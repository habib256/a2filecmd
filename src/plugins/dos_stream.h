/* Read-only DOS 3.3 logical stream. Caller supplies sector_read(t,s,d).
 * MAIN state only, no FILE emulation or service-table change. Validate the
 * selected catalog identity, T/S offsets, aliases and exact BIN/BASIC EOF.
 * A failed read is sticky and never becomes a normal EOF. */
#ifndef DS_SECTORS
#define DS_SECTORS 560
#endif
#ifndef DS_POSITION
#define DS_POSITION unsigned long
#endif
#ifndef DS_READ_ONLY
static unsigned int ds_slots[DS_SECTORS];
#endif
static unsigned int ds_count, ds_cache;
static unsigned int* ds_map;
#ifndef DS_READ_ONLY
/* Catalog/list work is retired once the logical sector map is complete.
 * Text page positions then reuse exactly that storage. */
static union {struct {unsigned char seen[70],ts[256];} scan;
 unsigned long pages[80];} ds_metadata;
#define ds_seen ds_metadata.scan.seen
#define ds_ts ds_metadata.scan.ts
#define ds_picture_map ((unsigned int*)ds_seen)
#endif
#ifdef DS_DATA_BUFFER
#define ds_data DS_DATA_BUFFER
#else
static unsigned char ds_data[256];
#endif
static unsigned char ds_bad, ds_prefix;
#ifndef DS_READ_ONLY
static unsigned char ds_kind;
static unsigned int ds_aux;
#endif
static DS_POSITION ds_length, ds_pos;
static unsigned int ds_word(const unsigned char* p){return (unsigned int)p[0]|((unsigned int)p[1]<<8);}
#ifndef DS_READ_ONLY
static unsigned char ds_pair(unsigned char t,unsigned char s){return t>0 && t<35 && s<16;}
static unsigned char ds_claim(unsigned char t,unsigned char s){
 unsigned int i;unsigned char bit;
 if(!ds_pair(t,s))return 0;
 i=(unsigned int)t*16+s;bit=1U<<(i&7);
 if(ds_seen[i>>3]&bit)return 0;
 ds_seen[i>>3]|=bit;return 1;
}
static void ds_name(const unsigned char* p,char* out){
 unsigned char n=30,i,c;
 while(n>1 && (p[n-1]&127)==' ')--n;
 if(n>15)n=15;
 for(i=0;i<n;++i){c=p[i]&127;if(c>='a'&&c<='z')c-=32;
  if(!((c>='A'&&c<='Z')||(c>='0'&&c<='9')))c='.';out[i]=c;}
 out[n]=0;if(out[0]<'A'||out[0]>'Z')out[0]='X';
}
static unsigned char ds_open(const struct Entry* selected){
 unsigned char t,s,j,found=0,ct,cs;
#ifndef DS_BINARY_ONLY
 unsigned char k;
#endif
 unsigned int start,last=0,pair,i;
 const unsigned char* e;char name[16];
 ds_map=ds_slots;ds_bad=0;ds_pos=ds_length=0;ds_count=0;ds_cache=65535U;ds_aux=0;
 memset(ds_seen,0,sizeof ds_seen);
 if(!sector_read(17,0,ds_ts))goto bad;
 if(ds_ts[3]<1||ds_ts[3]>3||ds_ts[0x27]!=122||ds_ts[0x34]!=35||
    ds_ts[0x35]!=16||ds_ts[0x36]||ds_ts[0x37]!=1)goto bad;
 ds_claim(17,0);t=ds_ts[1];s=ds_ts[2];
 if(!ds_pair(t,s))goto bad;
 while(t){
  if(!ds_claim(t,s)||!sector_read(t,s,ds_ts))goto bad;
  ct=ds_ts[1];cs=ds_ts[2];if((!ct&&cs)||(ct&&!ds_pair(ct,cs)))goto bad;
  if(ct){i=(unsigned int)ct*16+cs;if(ds_seen[i>>3]&(1U<<(i&7)))goto bad;}
  for(j=0;j<7;++j){
   e=ds_ts+11+(unsigned int)j*35;
   if(!e[0]){ct=0;break;}if(e[0]==255)continue;
   if(((unsigned int)e[0]<<8|e[1])!=selected->mdate)continue;
   ds_name(e+3,name);
   if(strcmp(name,selected->name))goto bad;
   if(++found!=1)goto bad;ds_kind=e[2]&127;
#ifdef DS_CATALOG_ENTRY
   DS_CATALOG_ENTRY(e);
#endif
#ifdef DS_BINARY_ONLY
   if(ds_kind!=4||selected->type!=6)goto bad;
#else
#ifdef DS_OTHER_TYPES
   if(ds_kind && (ds_kind&(unsigned char)(ds_kind-1)))goto bad;
#else
   if(ds_kind!=0&&ds_kind!=4&&ds_kind!=1&&ds_kind!=2)goto bad;
#endif
   k=ds_kind==0?4:ds_kind==4?6:ds_kind==1?0xFA:ds_kind==2?0xFC:0;
   if(k!=selected->type)goto bad;
#endif
  }
  t=ct;s=cs;
 }
 if(found!=1)goto bad;
 t=selected->mdate>>8;s=selected->mdate;start=0;
 while(t){
  if(!ds_claim(t,s)||!sector_read(t,s,ds_ts))goto bad;
  if(ds_word(ds_ts+5)!=start || start>=DS_SECTORS)goto bad;
  ct=ds_ts[1];cs=ds_ts[2];if((!ct&&cs)||(ct&&!ds_pair(ct,cs)))goto bad;
  for(j=0;j<122;++j){
   t=ds_ts[12+(unsigned int)j*2];s=ds_ts[13+(unsigned int)j*2];
   i=start+j;
   if(!t){if(s)goto bad;pair=0;}
   else {if(i>=DS_SECTORS||!ds_claim(t,s))goto bad;pair=((unsigned int)t<<8)|s;last=i+1;}
   if(i<DS_SECTORS)ds_map[i]=pair;
  }
  start+=122;t=ct;s=cs;
 }
 ds_count=last;
#ifdef DS_BINARY_ONLY
 ds_prefix=4;
#else
 ds_prefix=ds_kind==4?4:ds_kind==1||ds_kind==2?2:0;
#endif
 ds_length=(DS_POSITION)ds_count*256U;
 if(ds_prefix){
  if(!ds_count||!ds_map[0]||!sector_read(ds_map[0]>>8,ds_map[0],ds_data))goto bad;
#ifdef DS_BINARY_ONLY
  ds_length=ds_word(ds_data+2);ds_aux=ds_word(ds_data);
#else
  ds_length=ds_word(ds_data+ds_prefix-2);ds_aux=ds_kind==4?ds_word(ds_data):ds_kind==2?0x0801:0;
#endif
#if DS_SECTORS < 256
  if(ds_length>(unsigned int)(ds_count*256U)-ds_prefix)goto bad;
#else
  if((unsigned long)ds_length+ds_prefix>(unsigned long)ds_count*256)goto bad;
#endif
  ds_cache=0;
 }
 return 1;
bad:ds_bad=1;return 0;
}
#endif /* DS_READ_ONLY */
#ifndef DS_NO_SEEK
static unsigned char ds_seek(DS_POSITION at){
 if(ds_bad || at>ds_length){ds_bad=1;return 0;}ds_pos=at;return 1;
}
#endif
static int ds_get(void){
 unsigned int n,p;DS_POSITION at;
 if(ds_bad || ds_pos==ds_length)return -1;
 at=ds_pos+ds_prefix;n=(unsigned int)(at>>8);
 if(n>=ds_count){ds_bad=1;return -1;}
 if(n!=ds_cache){
  p=ds_map[n];
  if(p){if(!sector_read(p>>8,p,ds_data)){ds_bad=1;return -1;}}
  else memset(ds_data,0,256);
  ds_cache=n;
 }
 ++ds_pos;return ds_data[(unsigned char)at];
}
