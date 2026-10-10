/* Read-only MAIN-only Print Shop source. No disk/AUX writes. DOS allocation
 * identity and sector aliases are validated by the shared logical stream. */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
struct PsHeader {unsigned int signature;unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[52];};
#ifndef PLUGIN_HOST
#define ferror(f) (((unsigned char*)(f))[1]&4)
#endif
static struct A2fcApi ps_api;
static FILE* ps_file;
static unsigned char ps_dos,ps_bad,ps_new;
static unsigned int ps_aux,ps_pos,ps_len;
static unsigned long ps_off;
#define A (&ps_api)
/* Largest supported font is 16 KiB plus the DOS BIN header: 65 sectors. */
#define DS_SECTORS 65
#define DS_DATA_BUFFER ps_api.copy_buf
#define DS_MLI ps_api.mli
#define DS_SEEK ps_api.fseek
#define frd ps_api.fread
#define fopn ps_api.fopen
#define fcls ps_api.fclose
#include "dos_source.h"
static unsigned char ps_open(void){
 ps_bad=0;ps_pos=ps_len=0;ps_off=0;
 if(ps_dos){
  if(!dv_open(&ps_api.panels[*ps_api.active]) || !ds_open(ps_api.selected) || ds_kind!=4){dv_close();ps_bad=1;return 0;}
  ps_aux=ds_aux;return 1;
 }
 ps_aux=ps_api.selected->aux;ps_file=ps_api.fopen(ps_api.full,"rb");
 if(!ps_file){ps_bad=1;return 0;}return 1;
}
static int ps_get(void){
 int c;
 if(ps_dos){c=ds_get();if(ds_bad)ps_bad=1;if(c>=0)++ps_off;return c;}
 if(ps_pos==ps_len){
  ps_pos=0;ps_len=ps_api.fread(ps_api.copy_buf,1,512,ps_file);
  if(ferror(ps_file)){ps_bad=1;return -1;}if(!ps_len)return -1;
 }
 ++ps_off;return ps_api.copy_buf[ps_pos++];
}
static unsigned char ps_seek(unsigned int pos){
 ps_off=pos;ps_pos=ps_len=0;
 if(ps_dos){if(!ds_seek(pos)){ps_bad=1;return 0;}}
 else if(ps_api.fseek(ps_file,(long)pos,SEEK_SET)){ps_bad=1;return 0;}
 return 1;
}
static unsigned char ps_close(void){
 if(ps_dos){if(!dv_close())ps_bad=1;}
 else if(ps_api.fclose(ps_file))ps_bad=1;
 return !ps_bad;
}
static unsigned char ps_select(const struct A2fcApi* api){
 ps_api=*api;ps_bad=0;
 ps_dos=api->panels!=NULL && api->active!=NULL && api->panels[*api->active].fs==FS_DOS33;
 ps_new=api->selected->type==0xF5;
 if((!ps_dos && !api->full[0]) || !api->selected->name[0] ||
    (api->selected->type!=6 && (!ps_new || ps_dos))){
  api->strcpy(api->note,"Select a Print Shop BIN/F5 file.");return 0;}
 return 1;
}
