/* dosrepl.c -- a ProDOS file written over the DOS 3.3 file of the same name,
 * on a real Disk II. The third verb of the DOS 3.3 write set: DOSWRITE
 * creates a name that is free, DOS33W deletes and renames, this one takes an
 * existing name over.
 *
 * From the ! menu, with the ProDOS file selected in the active panel and the
 * DOS 3.3 disk open in the other -- the same arrangement DOSWRITE uses, and
 * the one whose refusal ("name collision") brought you here.
 *
 * Its own overlay because it does not fit anywhere else: the window is
 * $1B00-$3FFF, and one overlay holding the copy engine, the audit and the
 * three verbs overflows it by two thousand bytes. What it shares instead is
 * written down: dos33_fs.h for the volume (sector I/O read back, the bitmap,
 * audit(), free_victim()) and dos33_copy.h for the copy (the reservation,
 * the data sectors, the track/sector lists, the second reading).
 *
 * The order is the whole point, and it is the one whose interruption cannot
 * lose the file:
 *
 *   1. audit() explains the volume, or nothing is written at all. It also
 *      collects, in `victim`, the sectors the file being replaced owns.
 *   2. The new copy is reserved in sectors of its own. The old file's are
 *      marked in use, so the allocator cannot reach them -- which is why
 *      the disk has to hold both copies at once, and says so when it
 *      cannot.
 *   3. The data and the lists are written, then read back against the
 *      source a second time.
 *   4. One catalog sector, one write: from that instant the name means the
 *      new file. Everything before it left the old one whole and readable.
 *   5. The old sectors go back to the bitmap.
 *
 * A cut between 4 and 5 loses the space of the old file and nothing else,
 * and the message says so rather than calling the work done. A cut before 4
 * leaves the original untouched and the reserved sectors unused -- space
 * again, never data. None of this is atomic and none of it pretends to be:
 * ProDOS gives no such promise on a Disk II, and neither do we.
 */
#define UTIL_STUBS
#define UTIL_INFO
#define UTIL_VOLUME
#define UTIL_WRITE

#include "util.h"
#include <string.h>

void __fastcall__ plugin_entry(const struct A2fcApi*);
unsigned char __fastcall__ dw_protected(unsigned char unit);
void dw_mainbank(void);

struct Header { unsigned int magic; unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3]; char desc[52]; };
#ifndef PLUGIN_HOST
#pragma rodata-name(push,"OVLHDR")
#endif
const struct Header __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},
 "DOS 3.3: replace the file of the same name"};
#ifndef PLUGIN_HOST
#pragma rodata-name(pop)
#endif

static unsigned char vtoc[256], cat[256], ts[256], data[256], seen[70], verify[256];
static unsigned char unit, catsector, slot, name[30];
static unsigned char allocation[70];
static unsigned int needed, sectors, lists, length, address;
static unsigned char kind, prefix;
static FILE* source;
/* audit() looks the entry up by `name`, which is what a replacement knows:
 * the name it must take over, not where that file happens to live. */
static unsigned char want_track, want_sector;
static unsigned char hit_cat, hit_slot, hit_type, name_taken, victim[70];
static unsigned int hit_count;
#define DOS33_FIND
#include "dos33_fs.h"
#include "dos33_copy.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api) {
 unsigned int i,n;unsigned char* e;
 init(api);source=NULL;
 if(pan->fs || !a.full[0] || !a.selected->name[0] || a.selected->type==0x0F ||
    other->fs!=FS_DOS33 || other->img_len) {
  note("ProDOS file here, DOS disk opposite.");return;
 }
 unit=(unsigned char)other->dir_key;
 if(!(unit&0x70) || (unit&15)) {note("No DOS drive there.");return;}
 n=unit_of(a.full,0);
 if(!n || n==unit) {note("Source must be on another drive.");return;}
 dw_mainbank();
 n=dw_protected(unit);
 if(n){note(n==1?"Not a standard Disk II.":"Disk is write-protected.");return;}
 if(getinfo(a.full) || info.storage<1 || info.storage>3 || !(info.access&1)) {
  note("No source info.");return;
 }
 address=info.aux;prefix=0;
 switch(info.type) {
 case 4:kind=0;break;
 case 6:kind=4;prefix=4;break;
 case 0xFC:kind=2;prefix=2;break;
 case 0xFA:kind=1;prefix=2;break;
 default:note("TXT, BIN, BAS, INT only.");return;
 }
 a.memset(name,0xA0,30);
 for(i=0;a.selected->name[i] && i<15;++i)name[i]=a.selected->name[i]|0x80;
 if(!source_length()) {note("Cannot read source.");return;}
 want_track=0;                        /* by name, not by link */
 if(!audit()){note("Refused: disk consistency.");return;}
 if(!hit_cat){note("No such DOS file; use C.");return;}
 if(hit_type&0x80){note("That file is locked.");return;}
 sectors=((unsigned long)length+prefix+255)/256;
 lists=(sectors+121)/122;if(!lists)lists=1;
 needed=sectors+lists;n=0;
 a.memset(allocation,0,sizeof allocation);
 for(i=48;i<560 && n<needed;++i)if(i/16!=17 && free_sector(i)){allocation[i>>3]|=mask(i);++n;}
 if(n!=needed){note("Not enough free sectors.");return;}
 a.sprintf((char*)data,"Replace %s on DOS S%u,D%u?",a.selected->name,
           (unit>>4)&7,(unit>>7)+1);
 if(!RF(confirm)((char*)data))return;
 /* A disk swapped while the question waited on screen is another disk. */
 if(!read_sector(272,ts) || memcmp(ts,vtoc,256) || !audit() || !hit_cat ||
    !read_sector(272+hit_cat,cat))goto refused;
 e=cat+11+hit_slot*35;
 if(memcmp(e+3,name,30) || (e[2]&0x80))goto refused;
 for(i=0;i<needed;++i)vtoc[bitpos(allocated(i))]&=~mask(allocated(i));
 if(!write_sector(272,vtoc) || !transfer())goto failed;
 if(!read_sector(272+hit_cat,ts) || memcmp(ts,cat,256) ||
    !read_sector(272,ts) || memcmp(ts,vtoc,256))goto failed;
 e[0]=allocated(0)/16;e[1]=allocated(0)&15;e[2]=kind;wr16(e+33,needed);
 if(!write_sector(272+hit_cat,cat))goto failed;   /* the switch */
 /* audit() collected the old file's sectors while it walked: only now, the
  * entry no longer pointing at them, may they go back. */
 free_victim();
 if(!write_sector(272,vtoc)) {
  note("Replaced; old sectors kept: run FIXIT.");return;
 }
 note("Replaced; source kept.");
 return;
refused:note("Disk changed; nothing done.");return;
failed:note("Stopped; check disk.");
}
