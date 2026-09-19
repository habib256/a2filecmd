/* dos33w.c -- delete and rename a file on a real DOS 3.3 disk.
 *
 * From the ! menu, with the active panel opened on a real DOS 3.3 disk and
 * the cursor on the file. The volume layer -- sector I/O read back, the
 * VTOC bitmap and audit() -- is src/plugins/dos33_fs.h, shared with
 * DOSWRITE; this file is the two verbs and everything they must refuse.
 *
 * The file is found by the track and sector of its first track/sector
 * list, which the panel keeps in `mdate`, never by name: the panel shows a
 * DOS name made into a ProDOS one, so two DOS files can share one panel
 * name and neither can be found back by it. Two entries cannot share the
 * link -- audit() would have refused the volume for a cross-link.
 *
 * Nothing is written before audit() has explained the whole volume, before
 * the question on screen has been answered, and before that same audit has
 * been run again on the sectors as they are at that moment: the drive door
 * is open while the question waits.
 *
 * Deleting writes the catalog sector FIRST and the bitmap after. A cut
 * between the two leaves the file's sectors marked in use with no entry
 * pointing at them -- space lost until FIXIT says so, and nothing else.
 * The other order would, for as long as it lasted, leave a visible entry
 * pointing at sectors the next file written is free to take: that is how
 * two files come to share a sector, and it is not a risk to run for the
 * sake of the natural order. Neither order is atomic and this one does not
 * pretend to be; it is the one whose interruption cannot lose data.
 *
 * Renaming is one catalog sector, read back like every other write. The
 * new name comes from the core's prompt, so it is a ProDOS-shaped name
 * (letters, digits and periods, fifteen at most) written in high-bit ASCII
 * padded with $A0. DOS 3.3 itself allows more, including the comma that
 * breaks its own CATALOG listing and the leading space that makes a file
 * unopenable from BASIC; we do not write those.
 *
 * A locked file is refused, as DOS's own DELETE and RENAME refuse it:
 * unlocking is a decision, not a step.
 */
#define UTIL_STUBS
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
 "DOS 3.3: delete or rename the selected file"};
#ifndef PLUGIN_HOST
#pragma rodata-name(pop)
#endif

static unsigned char vtoc[256], cat[256], ts[256], seen[70], verify[256];
static unsigned char unit, catsector, slot, name[30];
/* What audit() is asked to find, and what it found (dos33_fs.h). */
static unsigned char want_track, want_sector;
static unsigned char hit_cat, hit_slot, hit_type, name_taken, victim[70];
static unsigned int hit_count;

#define DOS33_FIND
#include "dos33_fs.h"

/* The panel's name is not the disk's: say which file in the words the user
 * can check, the panel line and the drive. */
static char question[64];

/* The catalog entry as it is on the disk right now, or 0: re-read, its link
 * still the one the panel showed, still unlocked. Every write goes through
 * this, after the question and after a second audit. */
static unsigned char* entry_now(void) {
 unsigned char* e;
 if(!audit() || !hit_cat)return 0;
 if(!read_sector(272+hit_cat,cat))return 0;
 e=cat+11+hit_slot*35;
 if(e[0]!=want_track || e[1]!=want_sector || (e[2]&0x80))return 0;
 return e;
}

static unsigned char do_delete(void) {
 unsigned char* e=entry_now();
 if(!e)return 0;
 /* DOS marks a deleted entry $FF and keeps the original track in the last
  * byte of the name, which is where UNDELETE reads it back from. That byte
  * is the thirtieth character of the name: DOS overwrites it too. */
 e[32]=e[0];e[0]=0xFF;
 if(!write_sector(272+hit_cat,cat))return 0;
 /* The entry is gone from the catalog: only now may its sectors go back to
  * the bitmap, and only its own, walked from the chain audit() validated. */
 free_victim();
 /* 2: the file is deleted and its sectors are still marked in use. Saying
  * "nothing deleted" here would be false, and saying "deleted" would hide
  * the lost space; FIXIT is what finds sectors no entry claims. */
 return write_sector(272,vtoc)?1:2;
}

static unsigned char do_rename(void) {
 unsigned char* e=entry_now();
 if(!e || name_taken)return 0;
 RF(memcpy)(e+3,name,30);
 return write_sector(272+hit_cat,cat);
}

/* The typed name into `name`, DOS style: high bit set, $A0 to the end. 0
 * when nothing usable was typed. */
static unsigned char take_name(void) {
 unsigned char i;
 a.memset(name,0xA0,30);
 for(i=0;a.input[i] && i<30;++i)name[i]=a.input[i]|0x80;
 return i!=0;
}

static const char s_consistency[] = "Refused: DOS 3.3 disk consistency.";

/* The drive named by `unit` must be a Disk II we may write to. 0 when it
 * is, and the note says why when it is not. */
static unsigned char drive_ready(void) {
 unsigned char n;
 if(!(unit&0x70) || (unit&15)) {note("Cannot identify the DOS 3.3 drive.");return 0;}
 dw_mainbank();
 n=dw_protected(unit);
 if(n){note(n==1?"Not a standard Disk II.":"DOS 3.3 disk is write-protected.");return 0;}
 return 1;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api) {
 unsigned char n;char key;
 init(api);
 if(pan->fs!=FS_DOS33 || pan->img_len || !pan->count || !a.selected->name[0] ||
    a.selected->type==0x0F) {
  note("Open a real DOS 3.3 disk and select a file.");return;
 }
 unit=(unsigned char)pan->dir_key;
 if(!drive_ready())return;
 /* The panel marks a locked file with access 1 (dos33_type keeps bit 7 of
  * the catalog byte); the entry is checked again on the disk itself. */
 if(!(a.selected->access&0x80)) {note("Locked on the DOS disk; unlock it there first.");return;}
 want_track=(unsigned char)(a.selected->mdate>>8);
 want_sector=(unsigned char)a.selected->mdate;
 a.memset(name,0xA0,30);
 if(!audit()){note(s_consistency);return;}
 if(!hit_cat){note("That file is no longer in the catalog.");return;}

 a.bar_begin();
 a.keys_bar(0,"D Delete,R Rename,ESC Back");
 RF(message)("\1Delete or rename on the DOS 3.3 disk?");
 key=a.wait_key();
 RF(message)("");
 if(key>='a' && key<='z')key-=32;

 if(key=='D') {
  a.sprintf(question,"Delete %s on DOS 3.3 S%u,D%u?",a.selected->name,
            (unit>>4)&7,(unit>>7)+1);
  if(!RF(confirm)(question))return;
  n=do_delete();
  if(!n){note("Nothing deleted; the disk is unchanged.");return;}
  note(n==1?"Deleted from the DOS 3.3 disk."
          :"Deleted, but its sectors stay in use: run FIXIT.");
  return;
 }
 if(key=='R') {
  if(!a.prompt("New name",a.selected->name,0) || !take_name())return;
  if(!audit() || !hit_cat){note(s_consistency);return;}
  if(name_taken){note("That name is already on the DOS 3.3 disk.");return;}
  a.sprintf(question,"Rename %s to %s?",a.selected->name,a.input);
  if(!RF(confirm)(question))return;
  if(!do_rename()){note("Not renamed; the disk is unchanged.");return;}
  note("Renamed on the DOS 3.3 disk.");
 }
}
