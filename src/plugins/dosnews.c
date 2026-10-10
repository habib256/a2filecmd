/* Direct read-only DOS Newsroom photos/banners. PLUGIN_MAGIC, OVERLAY_BIG.
 * C preflight validates all source bytes, then returns before HGR writes.
 * Renderer/reader state and helpers stay below $2000; MAIN only. */
#include <string.h>
#include <stddef.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct Header {unsigned int magic;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[40];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG,plugin_entry,
 {0,0,0},"Direct DOS Newsroom photos/banners"};
#pragma rodata-name(pop)
static const struct A2fcApi* A;
#ifndef PLUGIN_HOST
#define ferror(f) (((unsigned char*)(f))[1]&4)
#endif
#define DS_MLI A->mli
#define DS_SEEK A->fseek
#define frd A->fread
#define fopn A->fopen
#define fcls A->fclose
#define DS_SECTORS 257
#define DS_DATA_BUFFER (A->copy_buf)
#include "dos_source.h"
#ifndef PLUGIN_HOST
extern unsigned int dh_map[33],dh_length;
extern unsigned char dh_unit,dn_width,dn_height,dn_offset;
extern unsigned long dh_base;
extern FILE* dh_file;
extern unsigned char* dh_buffer;
const unsigned char dh_api_offsets[]={offsetof(struct A2fcApi,wait_key),offsetof(struct A2fcApi,mli),
 offsetof(struct A2fcApi,fread),offsetof(struct A2fcApi,fclose),offsetof(struct A2fcApi,fseek),offsetof(struct A2fcApi,note)};
#else
extern void host_news(const unsigned char*,unsigned int,unsigned char,unsigned char);
static unsigned char host_bitmap[7104];
#endif
unsigned char __fastcall__ dv_entry(const struct A2fcApi* a){
 unsigned char frame[6],width,height;unsigned int i,bytes,start,count;unsigned long offset;int c;
 const struct Entry* e=a->selected;
 A=a;dv_file=NULL;
 if(!e->name[0] || e->type!=6 || !dv_open(a->panels+*a->active) || !ds_open(e) || ds_kind!=4 || ds_aux!=0x4000)goto bad;
 for(i=0;i<6;++i){c=ds_get();if(c<0)goto bad;frame[i]=c;}
 if(frame[3]<frame[2] || frame[5]<frame[4])goto bad;
 height=frame[3]-frame[2];if(height>=192)goto bad;++height;
 width=(unsigned char)(frame[5]-frame[4]);width=width/7+1;bytes=(unsigned int)width*height;
 if(ds_word(frame)!=bytes || ds_length<(unsigned long)bytes+8)goto bad;
 offset=ds_length-bytes;
 if(!ds_seek(offset-1)||ds_get()!=255)goto bad;
 for(i=0;i<bytes;++i){c=ds_get();if(c<0)goto bad;
#ifdef PLUGIN_HOST
 host_bitmap[i]=c&127;
#endif
 }
 if(ds_bad || ds_pos!=ds_length)goto bad;
#ifdef PLUGIN_HOST
 if(!dv_close())goto bad;
 host_news(host_bitmap,bytes,width,height);return 0;
#else
 offset+=4;start=(unsigned int)(offset>>8);
 count=((unsigned int)(offset&255)+bytes+255)/256;
 if(count>33 || (unsigned long)start+count>ds_count)goto bad;
 for(i=0;i<count;++i)dh_map[i]=ds_map[start+i];
 dh_length=bytes;dh_unit=dv_unit;dh_base=dv_base;dh_file=dv_file;dh_buffer=A->copy_buf;
 dn_width=width;dn_height=height;dn_offset=(unsigned char)offset;
 return 1;
#endif
bad:
 dv_close();a->strcpy(a->note,"Malformed DOS Newsroom photo/banner or source I/O error.");return 0;
}
#ifdef PLUGIN_HOST
void __fastcall__ plugin_entry(const struct A2fcApi* a){dv_entry(a);}
#endif
