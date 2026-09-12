/* Purplesoft GRLOAD/GRSAVE pairs, from the original DOS 3.3 programs.
 * FOTO1 is the auxiliary 8K page; FOTO2 the main page. FOTO1[$79] is
 * &GR mode minus one, FOTO1[$7A] is 'S'. No file writes. Only main HGR
 * and, for modes 6..10, AUX HGR are written. OVERLAY_AUX obtains prior
 * consent; any exit after AUXMOVE rebuilds /RAM, including I/O failures.
 */
#include <string.h>
#include "../a2fc_plugin.h"
void __fastcall__ plugin_entry(const struct A2fcApi*);
void pu_prepare(void),pu_aux_move(void),pu_restore(void);
void __fastcall__ pu_show(unsigned char);
struct Header {unsigned int signature;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[22];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={MEDIA_PLUGIN_MAGIC,OVERLAY_BIG|OVERLAY_AUX,plugin_entry,{0,0,0},"Purplesoft pictures"};
#pragma rodata-name(pop)
#ifdef PLUGIN_HOST
extern unsigned char host_page[8192];
#define PAGE host_page
#else
#define PAGE ((unsigned char*)0x2000)
#endif
static const struct A2fcApi* A;
#include "hgr_io.h"
static unsigned char load(FILE* f) {
 unsigned char ok;
 ok=frd(PAGE,1,8192,f)==8192 && !frd(A->copy_buf,1,1,f) && !ferror(f) && feof(f);
 if(fcls(f))ok=0;
 return ok;
}
void __fastcall__ plugin_entry(const struct A2fcApi* a) {
 FILE* f;
 unsigned char len,ok,mode,dirty;
 A=a;dirty=ok=0;
 len=A->strlen(A->full);
 if(len<7 || len>80 || memcmp(A->full+len-6,".FOTO",5))goto done;
 --len;mode=A->full[len]-'1';if(mode>1)goto done;
 scpy(A->other_full,A->full);A->other_full[len]='1';
 f=fopn(A->other_full,"rb");if(!f)goto done;
 pu_prepare();
 ok=load(f);
 if(!ok)goto done;
 mode=PAGE[0x79];ok=0;
 if(PAGE[0x7A]!='S' || mode>9)goto done;
 A->other_full[len]='2';
 f=fopn(A->other_full,"rb");if(!f)goto done;
 if(mode>=5){pu_aux_move();dirty=1;}
 ok=load(f);
 if(ok){pu_show(mode);getkey(0);scpy(A->reselect,A->selected->name);}
 pu_restore();
done:
 if(dirty && A->ram_format())scpy(A->note,"/RAM rebuilt.");
 if(!ok)scpy(A->note,"Bad FOTO pair or I/O.");
}
