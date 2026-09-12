/* A2 FILE CMD -- a two-panel ProDOS file manager in the spirit of Total
 * Commander, running natively on a 128 KB Apple IIe.
 *
 * A standalone SYS program, bootable on its own or launched from a selector
 * such as Bitsy Bye, with its own launcher (loader.c) and its video
 * switches (memory_swap.c). It never modifies a file on its
 * own: only the explicit commands (copy, move, rename, delete, directory
 * creation, type, lock) write to the disk, after confirmation whenever
 * they destroy something. It also writes A2FILE/A2FILE.CFG on exit: the
 * two directories, the sort order, the active panel.
 *
 * Open (Return) chooses by type: a directory opens, a DHGR image (.RLE,
 * DHRR stream) is shown full screen, a TXT is read page by page, a SYS is
 * launched after confirmation, everything else is viewed in hexadecimal.
 * Space tags several files: copy, move and delete then apply to all the
 * tagged files.
 *
 * Memory: code at $4000, working buffers in $1000-$1AFF (LOWBSS),
 * viewers and prompts in the language card ($D400-$DFFF, segment LC,
 * copied by crt0 as for the game), and an overlay window at $1B00-$1FFF
 * where the overlays (A2FILE/IMAGE.PLG, TEXT, HEX, DELETE, HELP: linked
 * with the program but written separately) are read on demand, see
 * overlay(). The two entry tables occupy the MAIN graphics page
 * $2000-$3FFF, free as long as no image is displayed: an image overwrites
 * it (MAIN and AUX), and both panels are reread on return. At most two
 * open files (copy): ProDOS buffers $0800 and $0C00, A2FC does not use
 * MAPBSS. A directory that overflows the table is read in windows, in
 * disk order.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <conio.h>
#include <unistd.h>
#include <fcntl.h>
#include <device.h>
#include <errno.h>
#include <apple2.h>
#include "memory_swap.h"
#include "music.h"
#include "a2fc_plugin.h"

/* cc65 reads these when a file is created (fopen "wb"): the copy keeps the
 * type and auxtype of the original, an image stays an image. */
extern unsigned char _filetype;
extern unsigned int _auxtype;

unsigned char __fastcall__ mli_gfi(void* params);   /* a2fc_mli.s */
unsigned char ram_format(void);
extern unsigned int chain_addr;                    /* chain.s */
void __fastcall__ chain_load(const char* path);
void __fastcall__ chain_command(const char* name);
unsigned char vsdrive_install(void);                /* vsdrive.s : VDrive, two volumes over the serial line */
extern const unsigned int a2fc_link_id;            /* overlay.s : the address of main, the identity of the overlays' link */
unsigned char __fastcall__ mli_sfi(void* params);
unsigned char __fastcall__ mli_call(unsigned char cmd, void* params);
void __fastcall__ aux_copy(unsigned int main_addr, unsigned int aux_addr, unsigned char to_aux);
void aux_hgr_to_aux(void);   /* $2000-$3FFF, main to auxiliary, AUXMOVE in one go */
/* The mouse (mouse.s): an AppleMouse II card, in any slot.
 * Not in the 6502 version (A2FC_NOMOUSE, make ARCH=6502): the space. */
#ifndef A2FC_NOMOUSE
unsigned char mouse_init(void);
unsigned char mouse_read(void);
void mouse_show(void);
void mouse_hide(void);
extern unsigned char mouse_x, mouse_y;
#endif
static unsigned char exists(const char* path);
static FILE* new_output(const char* path);
static unsigned char push_name(char* path, const char* name);
int main(void);
static void too_long(void);
static unsigned char target_check(void);
static void progress_bar(const char* name, unsigned long copied, unsigned long size);
static void refresh_both(void);
static unsigned char abort_key(void);
static void dir_fail(void);

#ifndef A2FC_VERSION
#define A2FC_VERSION "0.6.8"
#endif
#define WINDOW (MAX_ENTRIES - 1)   /* disk entries per window: ".." on top of them */

/* The fingerprint of what a panel shows (a2fc_mli.s, in LOWEXE): count,
 * window, path or its absence, and every byte of the entry table.
 * It tells whether a reread changed the screen, far more cheaply than
 * redrawing it. The assembler reads the panel through the offsets noted
 * next to the fields of struct Panel: moving them means updating it. */
unsigned int __fastcall__ panel_hash(const struct Panel* pan);

enum { SORT_NAME, SORT_SIZE, SORT_TYPE, SORT_MODES };
enum { ASK, OVERWRITE_ALL, SKIP_ALL };

#define ENTRIES ((struct Entry*)0x2000)   /* the HGR MAIN page, see the header */
#define HELP_BUF ((char*)0x2000)          /* the same page for the help */
/* The editor is a big overlay: its code runs from $1B00 to $27FF, the
 * text occupies $2C00-$3FFF of the graphics page. */
#define EDIT_BUF ((char*)0x2C00)
#define EDIT_MAX 0x13F0
/* All the BSS of this file lives in low RAM ($1000-$1FFF, segment LOWBSS
 * of a2fc.cfg): main() zeroes it, crt0 only does so for BSS.
 * Segment bounds exported by the linker. */
extern char _LOWBSS_RUN__[];
extern char _LOWBSS_SIZE__[];
#pragma bss-name (push, "LOWBSS")
static struct Panel panels[2];
static unsigned char active, sort_mode, over_policy;
static unsigned char batch_snapshot;
static unsigned int progress_done, progress_total, progress_skipped;
static unsigned char progress_abort;   /* ESC during an operation: we stop at the current file */
static unsigned char bar_last;         /* the bar as it is drawn: we only redraw it if it changes */
static const char* bar_name;
/* Diagnostics readable by the POM2 test bench (see a2fc.lbl). */
unsigned int a2fc_draws, a2fc_ops, a2fc_errors;
unsigned char a2fc_view;       /* 0 panels, 1 image, 2 text, 3 hex, 4 help, 5 editor */
unsigned char a2fc_slot;       /* the Mockingboard, 0 without; 0xFF not searched for yet */
unsigned char a2fc_mouse;      /* the slot of the mouse, 0 without */
#ifndef A2FC_NOMOUSE
static unsigned char pointer;  /* the mouse has moved once: the pointer is shown */
#endif

static char full[PATH_LEN + NAME_LEN];
static char other_full[PATH_LEN + NAME_LEN];
static char cfg_path[PATH_LEN];
static char input[NAME_LEN];
static char question[64];
static unsigned char copy_buf[512];
static unsigned char gfi[18];
static unsigned char gfi_path[PATH_LEN + 1];
static unsigned char picked[MAX_ENTRIES];
static char album[2][NAME_LEN];    /* image viewer: the left and right neighbours */
static unsigned int seen[2];       /* and the fingerprint of both panels on entry */
static char overlay_loaded[12];     /* the overlay in place in the $1B00 window, "" if none */
static char reselect[NAME_LEN];    /* on return from a big overlay: the name to reselect */
static struct Entry selected;      /* the entry under the cursor, copied before a big overlay overwrites the table */
static char note[80];              /* ... and the message to write on line 22 */
static long text_starts[80];   /* known page starts */
/* MOVE manifest state survives all overlays in the idle text-viewer buffer. */
struct MoveBatch {
    char list[PATH_LEN], source[PATH_LEN], target[PATH_LEN], reason[80];
    unsigned char count, index, owned, ready;
};
#define MB ((struct MoveBatch*)text_starts)
typedef char batch_state_fits[sizeof text_starts - sizeof(struct MoveBatch)];
/* The recursive walks (copying and deleting a directory) stack the
 * entries of each level: a level occupies pool[base..base+n[, the next
 * level starts at base+n. A tree in which one path accumulates more than
 * POOL_SIZE entries is refused before any write. The pool occupies the
 * entry table of the inactive panel (4060 bytes), useless during the
 * operation since both panels are reread afterwards. */
#define POOL_SIZE 213
struct Mini { char name[16]; unsigned char type; unsigned int aux; };
static struct Mini* pool;

/* ---------------------------------------------------------------------- */
/* MLI: GET_FILE_INFO and SET_FILE_INFO                                    */
/* ---------------------------------------------------------------------- */

/* Fills gfi[] for `path` (full ProDOS name). Returns 0 on error. */
static unsigned char file_info(const char* path)
{
    unsigned char len = strlen(path);
    gfi_path[0] = len;
    memcpy(gfi_path + 1, path, len);
    gfi[0] = 0x0A;
    gfi[1] = (unsigned char)((unsigned)gfi_path & 0xFF);
    gfi[2] = (unsigned char)((unsigned)gfi_path >> 8);
    return mli_gfi(gfi) == 0;
}

/* Reserve a new directory entry before any truncating open. A failed
 * lookup never grants permission to overwrite an existing file. */
static FILE* new_output(const char* path)
{
    FILE* f;
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL);
    if (fd < 0) return NULL;
    if (close(fd)) { remove(path); return NULL; }
    f = fopen(path, "wb");
    if (!f) remove(path);            /* only the entry just created */
    return f;
}

/* Rewrites access, type and auxtype from gfi[]: SET_FILE_INFO shares the
 * layout of GET_FILE_INFO for its first seven parameters. */
static unsigned char set_info(void)
{
    gfi[0] = 0x07;
    return mli_sfi(gfi) == 0;
}

/* On a volume directory, aux_type = blocks of the volume and blocks_used
 * = blocks in use. */
static unsigned char volume_blocks(const char* volume, unsigned int* total, unsigned int* free)
{
    if (!file_info(volume)) return 0;
    *total = gfi[5] | ((unsigned int)gfi[6] << 8);
    *free = *total - (gfi[8] | ((unsigned int)gfi[9] << 8));
    return 1;
}

static void volume_space(struct Panel* pan)
{
    const char* slash;
    unsigned char len;
    char volume[NAME_LEN];
    pan->free_blocks = pan->total_blocks = 0;
    if (!pan->path[0] || pan->fs) return;
    slash = strchr(pan->path + 1, '/');
    len = slash ? (unsigned char)(slash - pan->path) : (unsigned char)strlen(pan->path);
    if (len >= NAME_LEN) return;
    memcpy(volume, pan->path, len);
    volume[len] = 0;
    volume_blocks(volume, &pan->total_blocks, &pan->free_blocks);
}

/* ---------------------------------------------------------------------- */
/* Direct reading of a directory                                          */
/* ---------------------------------------------------------------------- */

/* ProDOS lets a directory be read like a file: 512-byte blocks, four
 * bytes of chaining then 39-byte entries, the first one of the first
 * block being the header (entry length, entries per block). Reading it
 * this way avoids cc65's opendir/readdir and their malloc: less code, and
 * no heap left to reserve. The current block lives in copy_buf, which is
 * never in use at the same time. */
static int dir_fd = -1;
static unsigned char dir_index, dir_per_block, dir_entry_len, dir_error;
static unsigned int dir_block_key;
static struct DirEntry dir_entry;

/* ---------------------------------------------------------------------- */
/* A disk image read as a directory (IMGFS)                               */
/* ---------------------------------------------------------------------- */

/* A ProDOS disk image opened for reading: its blocks are read by fseek
 * within the file (a .DSK is in DOS 3.3 order, permuted like po2dsk.py
 * does; a .2MG carries its order and the offset of its data in its
 * header). The directory is then read block by block following the
 * ProDOS chaining, exactly like a real directory. */
static FILE* img_f;
static unsigned char img_dsk;        /* 1: DOS 3.3 order */
static long img_base;                /* offset of the data (.2MG) */
static const unsigned char IMG_SECT[16] = { 0x0, 0xE, 0xD, 0xC, 0xB, 0xA, 0x9, 0x8, 0x7, 0x6, 0x5, 0x4, 0x3, 0x2, 0x1, 0xF };
static unsigned char dir_img;        /* dir_next reads from an image */

/* The source of a DOS 3.3 sector: 0 = open image (img_f), otherwise the
 * ProDOS unit of a real disk, read by READ_BLOCK. */
static unsigned char dos_unit;
/* A logical DOS 3.3 sector (T, S) to a ProDOS half-block, on the same
 * disk: the inverse of the SECTORS table of po2dsk.py. Value = block within
 * the track (T x 8 + value >> 1) and half (value & 1). */
static const unsigned char DOS_TS[16] = { 0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15 };

/* Recognises a disk image by its suffix. Returns 1 (FS_IMG) if it is one,
 * FS_PRODOS (0) otherwise. The sector order is deduced from the suffix by
 * img_open. */
static unsigned char image_order(const char* name)
{
    unsigned char n = strlen(name);
    return (n > 4 && (!strcmp(name + n - 4, ".DSK") || !strcmp(name + n - 4, ".2MG")))
        || (n > 3 && (!strcmp(name + n - 3, ".PO") || !strcmp(name + n - 3, ".DO"))) ? FS_IMG : FS_PRODOS;
}

/* Opens the image `path`: the sector order comes from the suffix (.PO ProDOS,
 * .DSK/.DO DOS 3.3, .2MG from its header). Returns 0 on failure; img_f open. */
static unsigned char img_open(const char* path)
{
    unsigned char n = strlen(path);
    img_f = fopen(path, "rb");
    if (!img_f) return 0;
    img_dsk = (n > 4 && !strcmp(path + n - 4, ".DSK")) || (n > 3 && !strcmp(path + n - 3, ".DO"));
    img_base = 0;
    if (n > 4 && !strcmp(path + n - 4, ".2MG")) {
        if (fread(copy_buf, 1, 64, img_f) != 64 || memcmp(copy_buf, "2IMG", 4) || copy_buf[0x0C] > 1) { fclose(img_f); return 0; }
        img_dsk = copy_buf[0x0C] == 0;
        img_base = *(unsigned long*)(copy_buf + 0x18);
    }
    return 1;
}

/* Reads the logical DOS 3.3 sector (track, sector), 256 bytes, into copy_buf.
 * Source: the open image (fseek in DOS order) or a real disk
 * (READ_BLOCK on the corresponding ProDOS half-block). Returns 1 if complete. */
static unsigned char dos_read_sector(unsigned char track, unsigned char sector)
{
    unsigned char code, parms[6];
    if (track >= 35 || sector >= 16) return 0;
    if (!dos_unit) {
        if (fseek(img_f, img_base + (((long)track * 16 + sector) << 8), SEEK_SET)) return 0;
        return fread(copy_buf, 1, 256, img_f) == 256;
    }
    code = DOS_TS[sector];
    parms[0] = 3; parms[1] = dos_unit;
    parms[2] = (unsigned char)((unsigned)copy_buf & 0xFF);
    parms[3] = (unsigned char)((unsigned)copy_buf >> 8);
    parms[4] = (unsigned char)((unsigned)track * 8 + (code >> 1));
    parms[5] = (unsigned char)(((unsigned)track * 8 + (code >> 1)) >> 8);
    if (mli_call(0x80, parms)) return 0;
    if (code & 1) memmove(copy_buf, copy_buf + 256, 256);   /* the upper half of the block */
    return 1;
}

/* A real DOS 3.3 volume? The VTOC (track 17 sector 0): DOS version 1-3,
 * plausible catalog track and sector, 35 tracks, 256 bytes per sector,
 * 122 pairs per list. Leaves the VTOC in copy_buf. */
static unsigned char dos_vtoc_ok(void)
{
    return dos_read_sector(17, 0) && copy_buf[3] >= 1 && copy_buf[3] <= 3
        && copy_buf[1] && copy_buf[1] < 35 && copy_buf[2] < 16
        && copy_buf[0x34] == 35 && copy_buf[0x27] == 0x7A;
}

/* Reads ProDOS block `block` of the image into `buf`. Returns 1 if complete. */
static unsigned char img_read_block(unsigned int block, unsigned char* buf)
{
    unsigned char half;
    if (!img_dsk) {
        if (fseek(img_f, img_base + ((long)block << 9), SEEK_SET)) return 0;
        return fread(buf, 1, 512, img_f) == 512;
    }
    for (half = 0; half < 2; ++half) {
        if (fseek(img_f, img_base + ((((long)(block >> 3) << 4) + IMG_SECT[((block & 7) << 1) + half]) << 8), SEEK_SET)) return 0;
        if (fread(buf + half * 256, 1, 256, img_f) != 256) return 0;
    }
    return 1;
}

/* Opens the directory with key block `key` in the already open image.
 * Returns 0 if it is not a ProDOS directory. */
static unsigned char dir_open_image(unsigned int key)
{
    dir_error = 0;
    dir_img = 1;
    dir_block_key = key;
    if (!img_read_block(key, copy_buf) || (copy_buf[4] >> 4) < 0x0E) return 0;
    dir_entry_len = copy_buf[4 + 0x1F];
    dir_per_block = copy_buf[4 + 0x20];
    if (dir_entry_len != 0x27 || dir_per_block != 0x0D) return 0;
    dir_index = 1;
    return 1;
}

static unsigned char dir_open(const char* path)
{
    dir_error = 0;
    dir_img = 0;
    dir_fd = open(path, O_RDONLY);
    if (dir_fd < 0) return 0;
    if (read(dir_fd, copy_buf, 512) != 512 || (copy_buf[4] >> 4) < 0x0E) { close(dir_fd); dir_fd = -1; return 0; }
    dir_entry_len = copy_buf[4 + 0x1F];
    dir_per_block = copy_buf[4 + 0x20];
    if (dir_entry_len != 0x27 || dir_per_block != 0x0D) { close(dir_fd); dir_fd = -1; return 0; }
    dir_index = 1;                   /* entry 0 is the header */
    return 1;
}

static void dir_close(void)
{
    if (dir_img) { if (img_f && fclose(img_f)) dir_error = 1; img_f = 0; dir_img = 0; return; }
    if (dir_fd >= 0 && close(dir_fd)) dir_error = 1;
    dir_fd = -1;
}

/* Loads the next directory block into copy_buf. For an image, we follow
 * the forward chaining pointer (bytes 2-3 of the current block); for a
 * real directory, ProDOS assembles the blocks, a plain read is enough. */
static unsigned char dir_block_next(void)
{
    unsigned int next = copy_buf[2] | ((unsigned int)copy_buf[3] << 8);
    if (!next) return 0;
    if (dir_img) {
        if (img_read_block(next, copy_buf) &&
            (copy_buf[0] | ((unsigned int)copy_buf[1] << 8)) == dir_block_key) {
            dir_block_key = next;
            return 1;
        }
    } else if (read(dir_fd, copy_buf, 512) == 512) return 1;
    dir_error = 1;
    return 0;
}

/* The next entry into dir_entry, or 0 at the end. */
static unsigned char dir_next(void)
{
    const unsigned char* e;
    unsigned char len, i, c;
    for (;;) {
        if (dir_index >= dir_per_block) {
            if (!dir_block_next()) return 0;
            dir_index = 0;
        }
        e = copy_buf + 4 + dir_index * dir_entry_len;
        ++dir_index;
        if (!(e[0] & 0xF0)) continue;   /* deleted entry */
        len = e[0] & 0x0F;
        for (i = 0; i < len; ++i) {
            c = e[i + 1] | 0x20;
            if ((c < 'a' || c > 'z') && (!i || !((c >= '0' && c <= '9') || c == '.'))) {
                dir_error = 1; return 0;
            }
            dir_entry.name[i] = e[i + 1];
        }
        if (!len) { dir_error = 1; return 0; }
        dir_entry.name[len] = 0;
        dir_entry.type = e[0x10];
        dir_entry.key = e[0x11] | ((unsigned int)e[0x12] << 8);
        dir_entry.blocks = e[0x13] | ((unsigned int)e[0x14] << 8);
        dir_entry.size = (unsigned long)e[0x15] | ((unsigned long)e[0x16] << 8) | ((unsigned long)e[0x17] << 16);
        dir_entry.access = e[0x1E];
        dir_entry.aux = e[0x1F] | ((unsigned int)e[0x20] << 8);
        dir_entry.mdate = e[0x21] | ((unsigned int)e[0x22] << 8);
        return 1;
    }
}

/* ---------------------------------------------------------------------- */
/* Display                                                                */
/* ---------------------------------------------------------------------- */

static void clear_row(unsigned char row)
{
    cclearxy(0, row, 80);
}

#pragma code-name (push, "LC")
static void message(const char* text)
{
    revers(0);
    clear_row(22);
    if (*text == 1) { revers(1); ++text; } /* explicit question marker, also available to plugins */
    cputsxy(0, 22, text);
    revers(0);
}
#pragma code-name (pop)

#pragma code-name(push, "LC")
static void too_long(void)
{
    extern const char msg_toolong[]; message(msg_toolong);
}
#pragma code-name(pop)

#ifndef A2FC_6502
#pragma code-name(push, "LC")
#endif
static void dir_fail(void)
{
    extern const char msg_dirfail[]; message(msg_dirfail);
}
#ifndef A2FC_6502
#pragma code-name(pop)
#endif
extern unsigned char tree_stack_ok(void);

/* The key bar, Norton Commander style: each key in an inverse block of
 * three columns, its label in plain text right after, one space between
 * the buttons. `spec` chains "KEY Label" items separated by commas; a
 * one-letter key is centred in its block. Line 23 is never written
 * beyond column 78: conio would wrap to the next line on the 80th and
 * scroll the screen. */
extern const char MAIN_KEYS[];   /* defined in the language card, further down (LC) */
extern const char VIEW_KEYS[];   /* in the language card, defined further down */

void keys_bar(unsigned char x, const char* spec); /* display.s; same plugin ABI */

/* Clears line 23 (79 columns, see keys_bar) before rewriting it. */
static void bar_begin(void)
{
    cclearxy(0, 23, 79);
    gotoxy(0, 23);
}

static void help_bar(void)
{
    bar_begin();
    keys_bar(0, MAIN_KEYS);
}

#include "display_types.h"

static unsigned char is_up(const struct Entry* e)
{
    return e->name[0] == '.' && e->name[1] == '.' && !e->name[2];
}

static unsigned char is_dir(const struct Entry* e)
{
    return e->type == 0x0F;
}

static unsigned char is_locked(const struct Entry* e)
{
    return !(e->access & 0x80);
}

static unsigned char tagged(const struct Panel* pan, unsigned char index)
{
    return (pan->tags[index >> 3] >> (index & 7)) & 1;
}

static void set_tag(struct Panel* pan, unsigned char index, unsigned char on)
{
    if (on) pan->tags[index >> 3] |= 1 << (index & 7);
    else pan->tags[index >> 3] &= ~(1 << (index & 7));
}

static unsigned char tag_count(const struct Panel* pan)
{
    unsigned char i, n = 0;
    for (i = 0; i < pan->count; ++i) n += tagged(pan, i);
    return n;
}

/* The tags of both panels, set aside in picked[] while an image, the help
 * or the editor overwrites the entry tables (save = 1), then given back
 * once the panels have been reread (save = 0). */
static void keep_tags(unsigned char save)
{
    if (save) {
        memcpy(picked, panels[0].tags, sizeof panels[0].tags);
        memcpy(picked + sizeof panels[0].tags, panels[1].tags, sizeof panels[1].tags);
    } else {
        memcpy(panels[0].tags, picked, sizeof panels[0].tags);
        memcpy(panels[1].tags, picked + sizeof panels[0].tags, sizeof panels[1].tags);
    }
}

/* One entry line, exactly 38 characters (a shorter line would leave the
 * end of the previous line on screen), in inverse when the cursor is on
 * it; a star after the name marks a file selected with Space, an L a
 * locked file. */
static void draw_entry(unsigned char p, unsigned char index)
{
    struct Panel* pan = &panels[p];
    unsigned char x = p ? 40 : 0;
    unsigned char row = 2 + (index - pan->top);
    const struct Entry* e = &pan->e[index];
    if (index >= pan->count) { cclearxy(x, row, 38); return; }
    if (p == active && index == pan->cursor) revers(1);
    gotoxy(x, row);
    if (is_up(e)) cprintf("%-15s  <UP>                 ", e->name);
    else if (!pan->path[0]) {
        /* Exactly 38 columns, like the other lines: with 7 trailing spaces
         * this line was 42 long, and in inverse (selection) its 4 extra
         * cells spilled over the separator and the neighbouring panel on
         * the left, or wrapped to the next line, columns 0-1, on the
         * right -- the "white squares" in DOS 3.3 mode. */
        if (!e->access) cprintf("%-15s S%u,D%u  DOS 3.3 disk   ", e->name, (e->mdate >> 4) & 7, (e->mdate >> 7) + 1);
        else {                                   /* "/VOL/" : a directory, as Ammonoid shows it */
            sprintf(question, "%s/", e->name);
            cprintf("%-16sS%u,D%u %5u/%5u free", question, e->mdate & 7, (e->mdate >> 3) + 1, e->aux, e->blocks);
        }
    }
    else if (is_dir(e)) { sprintf(question, "%s/", e->name); cprintf("%-17s<DIR>          %5u ", question, e->blocks); }
    else cprintf("%-15s%c%c%s $%04X %8lu   ", e->name, tagged(pan, index) ? '*' : ' ',
                 is_locked(e) ? 'L' : ' ', type_name(e->type), e->aux, e->size);
    revers(0);
}

static void draw_panel(unsigned char p)
{
    struct Panel* pan = &panels[p];
    unsigned char x = p ? 40 : 0, i;
    extern const char a2fc_header[];
    static const unsigned char sort_column[SORT_MODES] = { 4, 35, 21 };
    ++a2fc_draws;
    cclearxy(x, 0, 38);
    if (p == active) revers(1);
    gotoxy(x, 0);
    i = strlen(pan->path);
    cprintf("%-38.38s", !pan->path[0] ? "[Volumes]" : i > 38 ? pan->path + i - 38 : pan->path);
    revers(0);
    gotoxy(x, 1);
    if (!pan->path[0]) cprintf("%-38s", "Volume          Slot   Free/Total");
    else if (pan->first || pan->more) cprintf("%-4u+ disk order    Type  Aux     Size", pan->first);
    else {
        cprintf("%-38s", a2fc_header);
        cputcxy(x + sort_column[sort_mode], 1, '*');
    }
    for (i = 0; i < ROWS; ++i) draw_entry(p, pan->top + i);
}

/* The separator line carries the program name and the free space of the
 * active panel's volume. */
static void draw_status(void)
{
    struct Panel* pan = &panels[active];
    chlinexy(0, 20, 80);
    cputsxy(2, 20, " A2 FILE CMD " A2FC_VERSION " ");
    if (pan->total_blocks) {
        gotoxy(30, 20);
        cprintf(" %u of %u blocks free ", pan->free_blocks, pan->total_blocks);
    }
#ifndef A2FC_NOMOUSE
    if (a2fc_mouse) cputsxy(70, 20, " Mouse ");
#endif
}

static void draw_frame(void)
{
    unsigned char row;
    clrscr();
    for (row = 0; row < 20; ++row) cputcxy(39, row, '|');
    draw_status();
    help_bar();
}

static void draw_info(void)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e;
    unsigned char n;
    clear_row(21);
    if (!pan->count) return;
    e = &pan->e[pan->cursor];
    gotoxy(0, 21);
    if (is_up(e)) { extern const char msg_parent[]; cputs(msg_parent); }
    else if (!pan->path[0]) cprintf("Volume %s  slot %u drive %u  %u blocks, %u free", e->name, e->mdate & 7, (e->mdate >> 3) + 1, e->blocks, e->aux);
    else if (is_dir(e)) cprintf("%s  directory  %u blocks", e->name, e->blocks);
    else {
        /* Directory reads have finished before drawing. One shared prefix
         * (at most 66 chars), then annotation/date (84 total before clipping),
         * in the existing 512-byte MAIN buffer; never borrow AUX. */
        n = sprintf((char*)copy_buf, "%s  type $%02X  aux $%04X  %u blocks  %lu bytes",
                    e->name, e->type, e->aux, e->blocks, e->size);
        if (pan->fs) strcpy((char*)copy_buf + n, "  (in image)");
        else sprintf((char*)copy_buf + n, "  %02u/%02u/%02u%s",
                     e->mdate & 31, (e->mdate >> 5) & 15, (e->mdate >> 9) % 100,
                     is_locked(e) ? "  locked" : "");
        copy_buf[79] = 0;
        cputs((char*)copy_buf);
    }
    n = tag_count(pan);
    if (n) { gotoxy(70, 21); cprintf("%u tagged", n); }
}

static void draw_all(void)
{
    draw_frame();
    draw_panel(0);
    draw_panel(1);
    draw_info();
}

static void show_active(void)
{
    draw_panel(active);
    draw_status();
    draw_info();
}

/* ---------------------------------------------------------------------- */
/* Reading directories                                                    */
/* ---------------------------------------------------------------------- */

static int compare(const void* a, const void* b)
{
    const struct Entry* x = a;
    const struct Entry* y = b;
    if (is_dir(x) != is_dir(y)) return is_dir(x) ? -1 : 1;
    if (!is_dir(x)) {
        if (sort_mode == SORT_SIZE && x->size != y->size) return x->size < y->size ? 1 : -1;
        if (sort_mode == SORT_TYPE && x->type != y->type) return x->type < y->type ? -1 : 1;
    }
    return strcmp(x->name, y->name);
}

/* Insertion sort, ".." stays first: less code than qsort, and the
 * directories on disk arrive almost sorted. */
static void sort_entries(struct Panel* pan)
{
    unsigned char i, j;
    struct Entry tmp;
    for (i = 2; i < pan->count; ++i) {
        tmp = pan->e[i];
        for (j = i; j > 1 && compare(&pan->e[j - 1], &tmp) > 0; --j) pan->e[j] = pan->e[j - 1];
        pan->e[j] = tmp;
    }
}

static struct Entry* add_entry(struct Panel* pan, const char* name, unsigned char type)
{
    struct Entry* e = &pan->e[pan->count++];
    strncpy(e->name, name, NAME_LEN - 1);
    e->name[NAME_LEN - 1] = 0;
    e->type = type;
    e->access = 0xC3;
    e->aux = e->blocks = e->mdate = 0;
    e->size = 0;
    return e;
}

/* DEVNUM ($BF30): the last device ProDOS touched. Enumerating the volumes
 * leaves it on the last drive queried (/RAM on a IIe), and Bitsy Bye would
 * open there on return: we put it back the way it was. */
#define DEVNUM (*(volatile unsigned char*)0xBF30)

/* The volume list as ProDOS gives it: ON_LINE on unit 0 returns, sixteen
 * bytes per DEVLST unit, the unit (DSSS) and the name -- or a zero length
 * and an error code for a drive without a volume. This is the list of
 * Bitsy Bye and CAT; cc65 (getfirstdevice, getdevicedir) redid one
 * ON_LINE per slot and drive it knows of, and a machine with more units
 * than that (ProDOS 2.4 mirrors up to fourteen per SmartPort card) lost
 * some. mdate keeps the DSSS >> 4 number: the drive in bit 3, the slot in
 * bits 0-2. */
static void read_volumes(struct Panel* pan)
{
    unsigned char saved = DEVNUM, i, b, len;
    unsigned char* online = copy_buf;
    unsigned char parms[4];
    char name[NAME_LEN];
    struct Entry* e;
    parms[0] = 2; parms[1] = 0;
    parms[2] = (unsigned char)((unsigned)online & 0xFF);
    parms[3] = (unsigned char)((unsigned)online >> 8);
    if (!mli_call(0xC5, parms))
        for (i = 0; i < 16 && pan->count < MAX_ENTRIES; ++i) {
            b = online[i * 16];
            if (!b) break;
            len = b & 15;
            if (!len) continue;                  /* no volume: the error follows */
            name[0] = '/';
            memcpy(name + 1, online + i * 16 + 1, len);
            name[len + 1] = 0;
            e = add_entry(pan, name, 0x0F);
            e->mdate = b >> 4;
            volume_blocks(name, &e->blocks, &e->aux);
        }
    /* DOS 3.3 disks have no ProDOS volume: we probe each unit (DEVLST) for
     * a DOS 3.3 VTOC and offer it as a directory. A ProDOS disk or an empty
     * drive fails the check and is not added; the ProDOS unit is kept in
     * mdate, access = 0 marks it. */
    {
        unsigned char nd = *(unsigned char*)0xBF31 + 1, i, unit;
        for (i = 0; i < nd && pan->count < MAX_ENTRIES; ++i) {
            unit = ((unsigned char*)0xBF32)[i] & 0xF0;
            dos_unit = unit;
            if (dos_vtoc_ok()) {
                e = add_entry(pan, "DOS 3.3", 0x0F);
                e->mdate = unit;
                e->access = 0;
                e->blocks = 560;
                e->aux = 0;
            }
        }
        dos_unit = 0;
    }
    DEVNUM = saved;
}

/* Fills the panel and forgets its tags. The window starts at entry
 * pan->first of the disk; ".." only appears in the first one, and sorting
 * only applies if the whole directory fits. Returns 0 if the directory
 * cannot be read: the panel then falls back to the volume list, never to
 * an empty screen. */
/* read_image_panel, dos33_type and read_dos33_panel keep their locals on
 * the C stack (low RAM is full); none of them is recursive. */
#pragma static-locals (push, off)

/* The closest ProDOS type to a DOS 3.3 type (catalog byte, bit 7 =
 * locked): T text, I Integer, A Applesoft, B binary, everything else BIN. */
static unsigned char dos33_type(unsigned char t)
{
    switch (t & 0x7F) {
    case 0x00: return 0x04;   /* T -> TXT */
    case 0x01: return 0xFA;   /* I -> INT */
    case 0x02: return 0xFC;   /* A -> BAS */
    case 0x04: return 0x06;   /* B -> BIN */
    }
    return 0x06;
}

/* Fills the panel from the DOS 3.3 catalog of the already established
 * source (dos_unit: an open image or a real disk). The catalog is flat: no
 * subdirectories, no "..". Each entry keeps in mdate the track and sector
 * of its first T/S list, for extraction. The DOS name is reduced to a
 * valid ProDOS name (letters, digits, periods, 15 at most). Returns 0 if
 * this is not a DOS 3.3 volume. */
static unsigned char read_dos33_panel(struct Panel* pan)
{
    struct Entry* e;
    unsigned char ct, cs, i, k, len;
    unsigned int remaining = 560;
    const unsigned char* d;
    char name[NAME_LEN];
    char c;
    if (!dos_vtoc_ok()) return 0;
    ct = copy_buf[1]; cs = copy_buf[2];
    pan->count = 0;
    pan->more = 0;
    memset(pan->tags, 0, sizeof pan->tags);
    while (ct && pan->count < MAX_ENTRIES) {
        if (!remaining-- || !dos_read_sector(ct, cs)) return 0;
        ct = copy_buf[1]; cs = copy_buf[2];
        for (i = 0; i < 7 && pan->count < MAX_ENTRIES; ++i) {
            d = copy_buf + 0x0B + i * 0x23;
            if (!d[0]) { ct = 0; break; }        /* never used: end of the catalog */
            if (d[0] == 0xFF) continue;          /* deleted */
            /* `len > 1`, not `len`: the trim always leaves one character,
             * so the loop below writes name[0] and its terminator. A name
             * of thirty blanks used to leave len at 0, and the fallback
             * two lines down then overwrote the ONLY terminator with 'X',
             * handing add_entry whatever followed on the stack. */
            len = 30;
            while (len > 1 && (d[2 + len] & 0x7F) == ' ') --len;
            for (k = 0; k < len && k < 15; ++k) {
                c = d[3 + k] & 0x7F;
                if (c >= 'a' && c <= 'z') c -= 32;
                if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))) c = '.';
                name[k] = c;
            }
            name[k] = 0;
            if (name[0] < 'A' || name[0] > 'Z') name[0] = 'X';   /* ProDOS: a letter first */
            e = add_entry(pan, name, dos33_type(d[2]));
            e->blocks = d[0x21] | ((unsigned int)d[0x22] << 8);   /* sectors, T/S lists included */
            e->size = (unsigned long)e->blocks << 8;
            e->access = (d[2] & 0x80) ? 0x01 : 0xC3;
            e->aux = 0;
            e->mdate = ((unsigned int)d[0] << 8) | d[1];          /* track/sector of the 1st T/S list */
        }
    }
    return 1;
}


/* Fills the panel from an image or a real disk opened as a directory
 * (pan->fs != 0). The source is a file image when pan->img_len > 0 (path
 * in pan->path[0..img_len], then the internal path), otherwise a real DOS
 * 3.3 disk whose ProDOS unit is in pan->dir_key. A ProDOS volume is
 * navigated by key block (dir_key), with ".." and the subdirectories; a
 * DOS 3.3 is a flat catalog. Returns 0 if the source is not readable; the
 * panel then falls back to the volume list. */





/* M: tags the files missing from the other panel or of a different size,
 * the basis of a synchronization by C. */

static unsigned char read_image_panel(struct Panel* pan)
{
    struct Entry* e;
    unsigned int parent = 2;
    unsigned char i;
    dos_unit = 0;
    if (pan->img_len) {             /* a file image */
        unsigned char tail = pan->path[pan->img_len];
        pan->path[pan->img_len] = 0;
        i = img_open(pan->path);
        pan->path[pan->img_len] = tail;
        if (!i) goto fail;
    } else {                        /* a real DOS 3.3 disk, by its ProDOS unit */
        dos_unit = (unsigned char)pan->dir_key;
        img_f = 0;
    }
    if (pan->fs == FS_DOS33) {       /* flat catalog, read by the overlay */
        i = read_dos33_panel(pan);
        if (img_f) { if (fclose(img_f)) i = 0; img_f = 0; }
        if (!i) goto fail;
        return 1;
    }
    /* ProDOS; if reading fails and the image is in DOS order, try DOS 3.3
     * (a DOS 3.3 floppy read by mistake as ProDOS). */
    pan->count = 0;
    pan->more = 0;
    memset(pan->tags, 0, sizeof pan->tags);
    if (!dir_open_image(pan->dir_key)) {
        if (img_dsk && pan->dir_key == 2 && read_dos33_panel(pan)) {
            pan->fs = FS_DOS33;
            dir_close();
            if (dir_error) goto fail;
            return 1;
        }
        dir_close();
        goto fail;
    }
    if (pan->dir_key != 2)          /* parent pointer of a subdirectory (0x23 in the header) */
        parent = copy_buf[4 + 0x23] | ((unsigned int)copy_buf[4 + 0x24] << 8);
    if (pan->dir_key != 2) { e = add_entry(pan, "..", 0x0F); e->mdate = parent; }
    while (dir_next()) {
        if (pan->count >= MAX_ENTRIES) { pan->more = 1; break; }
        e = add_entry(pan, dir_entry.name, dir_entry.type);
        e->access = dir_entry.access;
        e->aux = dir_entry.aux;
        e->blocks = dir_entry.blocks;
        e->size = dir_entry.size;
        e->mdate = dir_entry.key;   /* the key block, to navigate and extract */
    }
    dir_close();
    if (dir_error) goto fail;
    if (pan->count > 2) sort_entries(pan);
    return 1;
fail:
    pan->fs = FS_PRODOS;
    pan->path[0] = 0;
    read_volumes(pan);
    return 0;
}
#pragma static-locals (pop)

static unsigned char read_panel(unsigned char p)
{
    struct Panel* pan = &panels[p];
    struct Entry* e;
    unsigned int skip = pan->first;
    unsigned char ok = 1;
    if (pan->fs) {
        ok = read_image_panel(pan);
        goto placed;
    }
    pan->count = 0;
    pan->more = 0;
    memset(pan->tags, 0, sizeof pan->tags);
    if (!pan->path[0]) {
        pan->first = 0;
        read_volumes(pan);
    } else {
        if (!dir_open(pan->path)) {
            ok = 0;
            pan->path[0] = 0;
            pan->first = 0;
            read_volumes(pan);
        } else {
            if (!pan->first) add_entry(pan, "..", 0x0F);
            while (dir_next()) {
                if (skip) { --skip; continue; }
                if (pan->count >= (pan->first ? WINDOW : MAX_ENTRIES)) { pan->more = 1; break; }
                e = add_entry(pan, dir_entry.name, dir_entry.type);
                e->access = dir_entry.access;
                e->aux = dir_entry.aux;
                e->blocks = dir_entry.blocks;
                e->size = dir_entry.size;
                e->mdate = dir_entry.mdate;
            }
            dir_close();
            if (dir_error) {pan->count=pan->more=0;ok=0;goto placed;}
            if (pan->first && !pan->count) { pan->first = 0; return read_panel(p); }
            if (!pan->first && !pan->more && pan->count > 2) sort_entries(pan);
        }
    }
    volume_space(pan);
placed:
    if (pan->cursor >= pan->count) pan->cursor = pan->count ? pan->count - 1 : 0;
    if (pan->top > pan->cursor) pan->top = pan->cursor;
    if (pan->cursor >= pan->top + ROWS) pan->top = pan->cursor - ROWS + 1;
    return ok;
}

static void set_cursor(struct Panel* pan, unsigned char index)
{
    pan->cursor = index;
    if (pan->cursor < pan->top) pan->top = pan->cursor;
    if (pan->cursor >= pan->top + ROWS) pan->top = pan->cursor - ROWS + 1;
}

/* Puts the active panel's cursor on `index` and redraws only what moves:
 * the two lines when the window does not scroll, the whole panel
 * otherwise, then the information line. */
static void land(unsigned char index)
{
    struct Panel* pan = &panels[active];
    unsigned char previous = pan->cursor, old_top = pan->top;
    set_cursor(pan, index);
    if (pan->top != old_top) draw_panel(active);
    else { draw_entry(active, previous); draw_entry(active, pan->cursor); }
    draw_info();
}

static void select_name(struct Panel* pan, const char* name)
{
    unsigned char i;
    pan->cursor = 0;
    pan->top = 0;
    for (i = 0; i < pan->count; ++i)
        if (!strcmp(pan->e[i].name, name)) { set_cursor(pan, i); break; }
}

/* Full path of the entry: "/VOL/DIR/NAME", or "/VOL" from the volume
 * list. Returns 0 if the result would exceed the 64 ProDOS characters. */
static unsigned char build_full(char* out, const struct Panel* pan, const struct Entry* e)
{
    if (!pan->path[0]) { strcpy(out, e->name); return 1; }
    if (strlen(pan->path) + 1 + strlen(e->name) >= PATH_LEN) return 0;
    sprintf(out, "%s/%s", pan->path, e->name);
    return 1;
}

static void open_path(struct Panel* pan)
{
    pan->cursor = pan->top = 0;
    pan->first = 0;
    if (!read_panel(pan - panels)) message("Cannot read this directory.");
}

#pragma code-name (push, "NAV")
#pragma rodata-name (push, "NAVRO")
/* Locate the child by name in the parent's current directory contents.
 * Directory reads only; no saved index can select an unrelated entry. */
static void nav_select(struct Panel* pan, const char* name)
{
    for (;;) {
        select_name(pan, name);
        if (pan->count && !strcmp(pan->e[pan->cursor].name, name)) return;
        if (!pan->more || pan->fs || pan->first > 65535U-WINDOW) break;
        pan->first += WINDOW;
        if (!read_panel(pan-panels)) return;
    }
    open_path(pan); /* the child disappeared: a clean first window */
}

static void go_up(struct Panel* pan)
{
    char last[NAME_LEN];
    char* slash;
    if (pan->fs) {
        if (!pan->img_len) {   /* a real DOS 3.3 disk: back to the volume list */
            pan->fs = FS_PRODOS;
            pan->path[0] = 0;
            pan->dir_key = 2;
            open_path(pan);
            nav_select(pan, "DOS 3.3");
            return;
        }
        if (pan->dir_key == 2) {
            /* root of the image: leave it, go back to the directory that
             * contains it, cursor on the image file. */
            pan->path[pan->img_len] = 0;
            slash = strrchr(pan->path, '/');
            strcpy(input, slash ? slash + 1 : pan->path);
            if (slash && slash != pan->path) *slash = 0;
            else pan->path[0] = 0;
            pan->fs = FS_PRODOS;
            open_path(pan);
            nav_select(pan, input);
        } else {
            /* go up one level in the image: ".." holds the parent's block */
            slash = strrchr(pan->path + pan->img_len, '/');
            pan->dir_key = pan->count ? pan->e[0].mdate : 2;
            if (slash) { strcpy(last, slash+1); *slash = 0; }
            pan->cursor = pan->top = 0;
            if (read_panel(pan - panels) && slash) nav_select(pan, last);
        }
        return;
    }
    slash = strrchr(pan->path, '/');
    if (!slash) return;
    strcpy(last, slash == pan->path ? slash : slash + 1);   /* the volume list names "/VOL" */
    if (slash == pan->path) pan->path[0] = 0;   /* "/VOL" -> volumes */
    else *slash = 0;
    open_path(pan);
    nav_select(pan, last);
}

static void enter_dir(struct Panel* pan, const struct Entry* e)
{
    if (is_up(e)) { go_up(pan); return; }
    if (pan->fs) {
        /* a subdirectory in the image: its key block is in mdate */
        if (strlen(pan->path) + 1 + strlen(e->name) >= PATH_LEN) { too_long(); return; }
        pan->dir_key = e->mdate;
        strcat(pan->path, "/");
        strcat(pan->path, e->name);
        pan->cursor = pan->top = 0;
        read_panel(pan - panels);
        return;
    }
    if (!build_full(full, pan, e)) { too_long(); return; }
    strcpy(pan->path, full);
    open_path(pan);
}

#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Input -- in the language card                                          */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "LC")
#pragma rodata-name (push, "LC")

static void question_begin(void)
{
    clear_row(22);
    gotoxy(0, 22);
    revers(1);
}

static unsigned char confirm(const char* text)
{
    char key;
    question_begin();
    cputs(text);
    cputs(" (Y/N) ");
    revers(0);
    do {
        key = cgetc();
        if (key == KEY_ESC) break;
        key |= 0x20;
    } while (key != 'y' && key != 'n');
    clear_row(22);
    return key == 'y';
}

/* An input into `input`: a ProDOS name (a letter, then letters, digits
 * or periods, 15 at most) or, with hex != 0, that many hexadecimal
 * digits. Returns 0 if the user cancels (Escape) or enters nothing. */
static unsigned char prompt(const char* label, const char* initial, unsigned char hex)
{
    unsigned char len = 0, max = hex ? hex : 15;
    char key;
    if (initial) { strcpy(input, initial); len = strlen(input); }
    else input[0] = 0;
    for (;;) {
        question_begin();
        cputs(label);
        cputs(": ");
        if (hex) cputc('$');
        cputs(input);
        cputc('_');
        revers(0);
        key = cgetc();
        if (key == KEY_ESC) { clear_row(22); return 0; }
        if (key == KEY_RETURN) { clear_row(22); return hex ? len == max : len != 0; }
        if (key == KEY_LEFT || key == KEY_DELETE) { if (len) input[--len] = 0; continue; }
        if (key >= 'a' && key <= 'z') key -= 32;
        if (len >= max) continue;
        if (hex ? ((key >= '0' && key <= '9') || (key >= 'A' && key <= 'F'))
                : ((key >= 'A' && key <= 'Z') || (len && ((key >= '0' && key <= '9') || key == '.')))) {
            input[len++] = key;
            input[len] = 0;
        }
    }
}

unsigned int __fastcall__ hex_value(const char* s); /* display.s, LC */

#include "errors.h"

const char msg_dirfail[] = "Directory unreadable or too large/deep.";
const char msg_toolong[] = "Path too long for ProDOS.";
const char msg_vdrive[] = "VDrive: serial card in slot %u, volumes in slot %u, drives 1 and 2.";
const char msg_notimg[] = "Not a ProDOS disk image (or DOS 3.3).";
const char msg_roimg[] = "Read-only disk image; C extracts to the other panel.";
const char msg_noentry[] = "This overlay has no entry point.";
const char msg_parent[] = "Parent directory";
const char msg_samedir[] = "Both panels show the same directory.";
const char msg_otherro[] = "The other panel is a read-only disk image.";
const char msg_intoself[] = "Cannot copy a directory into itself.";
const char VIEW_KEYS[] = "SPC Next,B Prev,ESC Back";
/* Shared text; draw_panel adds the sort marker over a space. */
const char a2fc_header[] = "Name             Type  Aux     Size";
const char MAIN_KEYS[] = "TAB Panel,RET Open,SPC Tag,C Copy,V Move,R Ren,D Del,K Mkdir,! More,? Help";
/* ---------------------------------------------------------------------- */
/* Viewers -- in the language card                                        */
/* ---------------------------------------------------------------------- */

/* Without opening the file: a FOT ($08), or a BIN the size of an HGR or DHGR
 * page, or an .RLE stream. Opening it then settles the matter on the header.
 * In main RAM: the language card is full. */
#pragma code-name (push, "CODE")
#pragma rodata-name (push, "RODATA")
/* The size of an HGR page (8,192 or 8,184 bytes) or a DHGR page (16,384), read
 * as two words: cc65 compares a long through a routine, and each comparison
 * used to cost some thirty bytes. */
static unsigned char page_size(const unsigned long* size)
{
    const uint16_t* w = (const uint16_t*)size;
    /* 8,184 and 16,376 as well as 8,192 and 16,384: a saver that stops at
     * the last byte the screen actually shows drops the eight bytes of the
     * final screen hole. 816/Paint writes its uncompressed double hi-res
     * that way, and A2FC used to answer "not an image" to it. */
    return !w[1] && (w[0] == 8192 || w[0] == 8184 || w[0] == 16384 || w[0] == 16376);
}

/* One classification for Return, I and the raw-image album. Explicit
 * packed formats take precedence over coincidental raw-page file sizes.
 * 0 unknown, 1 raw/RLE, 2 Extasie, 3 packed FOT, 4 816/Paint, 5 lo-res. */
static unsigned char image_kind(const struct Entry* e)
{
    unsigned char n = strlen(e->name);
    if (is_dir(e)) return 0;
    if (e->type == 0xF2) return 2;
    if (e->type != 0x06 && e->type != 0x08) return 0;
    if (e->type == 0x08 && ((e->aux & 0xFFFE) == 0x4000 || e->aux == 0x8066)) return 3;
    if (e->type == 0x06 && (e->aux == 0xE001 || e->aux == 0xE002)) return 4;
    if (e->aux == 0x0400 && e->size && e->size <= 2048) return 5;
    return page_size(&e->size) || (n > 4 && !strcmp(e->name + n - 4, ".RLE"));
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* Buffered reading: cc65's fgetc goes through ProDOS for every byte. */
static FILE* vf;
static unsigned int vlen, vpos;
static long vbase;

static int view_getc(void)
{
    if (vpos >= vlen) {
        vbase += vlen;
        vpos = 0;
        vlen = fread(copy_buf, 1, sizeof copy_buf, vf);
        if (!vlen) return -1;
    }
    return copy_buf[vpos++];
}

static void view_seek(long offset)
{
    fseek(vf, offset, SEEK_SET);
    vbase = offset;
    vlen = vpos = 0;
}

#define TEXT_ROWS 22
#define TEXT_PAGES 80           /* text_starts[]: the known page starts */

/* A page of 22 rows; ProDOS line ends are CRs. The page starts are
 * remembered on the way through: the previous page is an fseek. */
/* The TEXT overlay: the text viewer, in A2FILE/TEXT.PLG. */
#pragma code-name (push, "TEXT")
#pragma rodata-name (push, "TEXTRO")
static const char tx_status[] = "%-38.38s page %u%s";
static const char tx_end[] = " (end)";
/* No " Back" after ESC, unlike the other bars: keys_bar lays this one down
 * from column 52, and the label made it 32 columns wide, ending at 83. The
 * four columns past 79 wrapped -- conio carried them round to the top left
 * of the screen, where "Back" sat over the first line of every text file.
 * At 28 columns it ends at 79, exactly like BASLIST's and AWP's. */
static const char tx_keys[] = "SPC Next,B Prev,R First,ESC";

static void view_text(const char* path)
{
    long* starts = text_starts;
    unsigned char page = 0, known = 1, row, col, done = 0;
    int c;
    char key;
    vf = fopen(path, "rb");
    if (!vf) { report_error("Open"); return; }
    a2fc_view = 2;
    starts[0] = 0;
    for (;;) {
        view_seek(starts[page]);
        clrscr();
        row = 0; col = 0; done = 0;
        while (row < TEXT_ROWS) {
            c = view_getc();
            if (c < 0) { done = 1; break; }
            c &= 0x7F;
            if (c == 13 || c == 10) { ++row; col = 0; if (row < TEXT_ROWS) gotoxy(0, row); continue; }
            if (c < 32) c = '.';
            if (col == 80) { ++row; col = 0; if (row >= TEXT_ROWS) { --row; --vpos; break; } gotoxy(0, row); }   /* the character will open the next page */
            cputc((char)c);
            ++col;
        }
        if (!done && page + 1 < TEXT_PAGES && known == page + 1) {
            starts[page + 1] = vbase + vpos;
            known = page + 2;
        }
        bar_begin();
        cprintf(tx_status, path, page + 1, done ? tx_end : (const char*)"");
        keys_bar(52, tx_keys);
        key = cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if (key == 'r' || key == 'R') page = 0;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN) && !done && page + 1 < known) ++page;
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && page) --page;
    }
    fclose(vf);
    a2fc_view = 0;
    draw_all();
}

/* S: the next sort order. Hosted by the TEXT overlay, which has room and is
 * on the floppy edition (the low RAM and the resident being full). */
static void resort(void)
{
    unsigned char p;
    char keep[NAME_LEN];
    sort_mode = (sort_mode + 1) % SORT_MODES;
    for (p = 0; p < 2; ++p) {
        strcpy(keep, panels[p].count ? panels[p].e[panels[p].cursor].name : "");
        read_panel(p);
        select_name(&panels[p], keep);
        draw_panel(p);
    }
    draw_info();
}

void __fastcall__ text_entry(const struct A2fcApi* a)
{
    if (a->arg == 'S') { resort(); return; }
    if (full[0]) view_text(full);
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* The BASLIST overlay: listing an Applesoft program, in BASLIST.PLG.     */
/* `T` on a BAS ($FC) loads it instead of the text viewer: instead of the */
/* hex of the tokens, the detokenised listing. It reads the file back     */
/* through view_getc (resident) and pages the way the text viewer does,   */
/* remembering the start of each page in text_starts. No buffer: it stays */
/* a small overlay.                                                       */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "BASLIST")
#pragma rodata-name (push, "BASLISTRO")
static const char bl_status[] = "%-38.38s page %u%s";
static const char bl_end[] = " (end)";
static const char bl_keys[] = "SPC Next,B Prev,R First,ESC";
static const char bl_number[] = "%u ";

#pragma static-locals (push, off)

/* The 107 Applesoft keywords ($80-$EA), separated by zeros. A NAMED array
 * (const char[]), not "..." literals: cc65 gathers literals into RODATA
 * (main window full), a named array follows the overlay's segment --
 * BASLISTRO, which makes BASLIST a big overlay (1.4 KB): the language card,
 * full, could no longer host it. */
static const char BAS_TOK[] =
    "END\0FOR\0NEXT\0DATA\0INPUT\0DEL\0DIM\0READ\0GR\0TEXT\0PR#\0IN#\0CALL\0"
    "PLOT\0HLIN\0VLIN\0HGR2\0HGR\0HCOLOR=\0HPLOT\0DRAW\0XDRAW\0HTAB\0HOME\0"
    "ROT=\0SCALE=\0SHLOAD\0TRACE\0NOTRACE\0NORMAL\0INVERSE\0FLASH\0COLOR=\0"
    "POP\0VTAB\0HIMEM:\0LOMEM:\0ONERR\0RESUME\0RECALL\0STORE\0SPEED=\0LET\0"
    "GOTO\0RUN\0IF\0RESTORE\0&\0GOSUB\0RETURN\0REM\0STOP\0ON\0WAIT\0LOAD\0"
    "SAVE\0DEF\0POKE\0PRINT\0CONT\0LIST\0CLEAR\0GET\0NEW\0TAB(\0TO\0FN\0SPC(\0"
    "THEN\0AT\0NOT\0STEP\0+\0-\0*\0/\0^\0AND\0OR\0>\0=\0<\0SGN\0INT\0ABS\0USR\0"
    "FRE\0SCRN(\0PDL\0POS\0SQR\0RND\0LOG\0EXP\0COS\0SIN\0TAN\0ATN\0PEEK\0LEN\0"
    "STR$\0VAL\0ASC\0CHR$\0LEFT$\0RIGHT$\0MID$";

static const char* bas_token(unsigned char n)
{
    const char* s = BAS_TOK;
    while (n--) { while (*s) ++s; ++s; }
    return s;
}

#define bl_row input[0]      /* 2 bytes of the resident input[] buffer: LOWBSS is full */
#define bl_col input[1]

/* One character on screen, cut at 80 columns, 22 rows; beyond that we stop
 * writing but keep consuming the file. CR moves to the next line. */
static void bl_putc(char c)
{
    if (bl_row >= TEXT_ROWS) return;
    if (c == 13) { ++bl_row; bl_col = 0; if (bl_row < TEXT_ROWS) gotoxy(0, bl_row); return; }
    if (bl_col == 80) { ++bl_row; bl_col = 0; if (bl_row >= TEXT_ROWS) return; gotoxy(0, bl_row); }
    cputc(c);
    ++bl_col;
}

static void bl_puts(const char* s) { while (*s) bl_putc(*s++); }

void __fastcall__ baslist_entry(const struct A2fcApi* a)
{
    unsigned char page = 0, known = 1, done;
    unsigned int num;
    int lo, hi, t;
    char key, buf[7];
    (void)a;
    vf = fopen(full, "rb");
    if (!vf) { report_error("Open"); return; }
    a2fc_view = 2;
    text_starts[0] = 0;
    for (;;) {
        view_seek(text_starts[page]);
        clrscr();
        bl_row = 0; bl_col = 0; done = 0;
        while (bl_row < TEXT_ROWS) {
            lo = view_getc(); hi = view_getc();      /* the next-line pointer */
            if (lo < 0 || (lo == 0 && hi == 0)) { done = 1; break; }
            num = (unsigned int)view_getc();
            num |= (unsigned int)view_getc() << 8;    /* the line number */
            sprintf(buf, bl_number, num);
            bl_puts(buf);
            for (;;) {
                t = view_getc();
                if (t <= 0) break;                    /* $00 ends the line (or EOF) */
                if (t >= 0x80 && t <= 0xEA) { bl_putc(' '); bl_puts(bas_token((unsigned char)(t - 0x80))); bl_putc(' '); }
                else bl_putc((char)(t & 0x7F));
            }
            bl_putc(13);
        }
        if (!done && page + 1 < TEXT_PAGES && known == page + 1) {
            text_starts[page + 1] = vbase + vpos;     /* the start of the next page */
            known = page + 2;
        }
        bar_begin();
        cprintf(bl_status, full, page + 1, done ? bl_end : (const char*)"");
        keys_bar(52, bl_keys);
        key = cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if (key == 'r' || key == 'R') page = 0;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN) && !done && page + 1 < known) ++page;
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && page) --page;
    }
    fclose(vf);
    a2fc_view = 0;
    draw_all();
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* The AWP overlay: an AppleWorks document (word processor, type $1A)     */
/* read page by page, in A2FILE/AWP.PLG. Return or T on an AWP, or the    */
/* ! menu. The format: 300 header bytes (SFMinVers at +183: from 30 on,   */
/* two more bytes), then records with a two-byte header: $D0 as second    */
/* byte = a lone carriage return, > $D0 = a page-layout command (skipped) */
/* $FF $FF = the end, otherwise the first byte counts the bytes of a line */
/* of text: cursor position and flags ($FF = a ruler, skipped), then the  */
/* characters, where the codes below $20 are formatting attributes        */
/* (ignored) and tabs.                                                    */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "AWP")
#pragma rodata-name (push, "AWPRO")
static const char aw_status[] = "%-38.38s page %u%s";
static const char aw_end[] = " (end)";
static const char aw_keys[] = "SPC Next,B Prev,R First,ESC";

#pragma static-locals (push, off)

#define aw_row input[0]
#define aw_col input[1]

static const char aw_bad[] = "Not an AppleWorks word-processor file.";

static void aw_putc(char c)
{
    if (aw_row >= TEXT_ROWS) return;
    if (c == 13) { ++aw_row; aw_col = 0; if (aw_row < TEXT_ROWS) gotoxy(0, aw_row); return; }
    if (aw_col == 80) { ++aw_row; aw_col = 0; if (aw_row >= TEXT_ROWS) return; gotoxy(0, aw_row); }
    cputc(c);
    ++aw_col;
}

void __fastcall__ awp_entry(const struct A2fcApi* a)
{
    unsigned char page = 0, known = 1, done, len;
    int c, kind;
    char key;
    (void)a;
    if (!selected.name[0] || selected.type != 0x1A || !full[0]) { message(aw_bad); return; }
    vf = fopen(full, "rb");
    if (!vf) { report_error("Open"); return; }
    view_seek(183);
    c = view_getc();                              /* SFMinVers */
    a2fc_view = 2;
    text_starts[0] = c >= 30 ? 302 : 300;
    for (;;) {
        view_seek(text_starts[page]);
        clrscr();
        aw_row = 0; aw_col = 0; done = 0;
        while (aw_row < TEXT_ROWS) {
            c = view_getc(); kind = view_getc();
            if (c < 0 || kind < 0 || kind == 0xFF) { done = 1; break; }
            if (kind == 0xD0) { aw_putc(13); continue; }       /* a lone carriage return */
            if (kind > 0xD0) continue;                          /* a page-layout command */
            len = (unsigned char)c;
            if (len < 2) { done = 1; break; }
            c = view_getc(); view_getc();                       /* position, then count and CR flag */
            len -= 2;
            if (c == 0xFF) { while (len--) view_getc(); continue; }   /* a ruler */
            while (len--) {
                c = view_getc();
                if (c < 0) { done = 1; break; }
                if (c >= 0x20 && c < 0x7F) aw_putc((char)c);
                else if (c == 0x16 || c == 0x17) do aw_putc(' '); while (aw_col & 7);   /* tab */
                else if (c == 0x0B) aw_putc(' ');                                      /* non-breaking space */
            }
            aw_putc(13);
        }
        if (!done && page + 1 < TEXT_PAGES && known == page + 1) {
            text_starts[page + 1] = vbase + vpos;
            known = page + 2;
        }
        bar_begin();
        cprintf(aw_status, full, page + 1, done ? aw_end : (const char*)"");
        keys_bar(52, aw_keys);
        key = cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if (key == 'r' || key == 'R') page = 0;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN) && !done && page + 1 < known) ++page;
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && page) --page;
    }
    fclose(vf);
    a2fc_view = 0;
    draw_all();
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* The COMPARE overlay: the selected file and the one of the same name in */
/* the other panel, byte by byte, in A2FILE/COMPARE.PLG. Run from the !   */
/* menu (M only compares sizes). Two halves of the resident copy buffer,  */
/* no reserve: a small overlay.                                           */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "COMPARE")
#pragma rodata-name (push, "COMPARERO")
#pragma static-locals (push, off)

static const char cmp_pick[]   = "Select a file to compare.";
static const char cmp_nooth[]  = "No such file in the other panel.";
static const char cmp_ident[]  = "Identical: %lu bytes.";
static const char cmp_diff[]   = "Differ at byte %lu.";
static const char cmp_short[]  = "Same for %lu bytes, then longer.";

/* M: tags the files missing from the other panel, or of a different size
 * or modification date (Cat Doctor's "compare directories"). Hosted by the
 * COMPARE overlay, on the floppy edition too (the resident being full). */
static void mark_differences(void)
{
    struct Panel* pan = &panels[active];
    struct Panel* other = &panels[!active];
    unsigned char i, j, n = 0;
    if (!target_check()) return;
    for (i = 0; i < pan->count; ++i) {
        const struct Entry* e = &pan->e[i];
        unsigned char differs = 1;
        if (is_dir(e)) continue;
        for (j = 0; j < other->count; ++j)
            if (!strcmp(other->e[j].name, e->name)) { differs = other->e[j].size != e->size || other->e[j].mdate != e->mdate; break; }
        set_tag(pan, i, differs);
        n += differs;
    }
    show_active();
    clear_row(22);
    gotoxy(0, 22);
    cprintf("%u missing from the other panel or of another size/date.", n);
}

void __fastcall__ compare_entry(const struct A2fcApi* a)
{
    struct Panel* oth = &panels[!active];
    FILE* fa;
    FILE* fb;
    unsigned int na, nb, i, m;
    unsigned long pos = 0;
    if (a->arg == 'M') { mark_differences(); return; }
    if (!selected.name[0] || is_dir(&selected) || !full[0]) { message(cmp_pick); return; }
    if (!oth->path[0] || oth->fs) { message(cmp_nooth); return; }
    sprintf(other_full, "%s/%s", oth->path, selected.name);
    fa = fopen(full, "rb");
    if (!fa) { report_error("Open"); return; }
    fb = fopen(other_full, "rb");
    if (!fb) { fclose(fa); message(cmp_nooth); return; }
    for (;;) {
        na = fread(copy_buf, 1, 256, fa);
        nb = fread(copy_buf + 256, 1, 256, fb);
        m = na < nb ? na : nb;
        for (i = 0; i < m; ++i)
            if (copy_buf[i] != copy_buf[256 + i]) {
                fclose(fa); fclose(fb);
                sprintf(question, cmp_diff, pos + i);
                message(question);
                return;
            }
        pos += m;
        if (na != nb) { fclose(fa); fclose(fb); sprintf(question, cmp_short, pos); message(question); return; }
        if (na < 256) break;
    }
    fclose(fa); fclose(fb);
    sprintf(question, cmp_ident, pos);
    message(question);
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* The SEARCH overlay: a text searched for in the panel's files, those    */
/* that contain it get tagged, in A2FILE/SEARCH.PLG. Run from the ! menu. */
/* The search is case-insensitive; the text is a ProDOS name (resident    */
/* prompt: letters, digits, periods), which covers keywords and names. A  */
/* sliding window handles the block edges.                                */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "SEARCH")
#pragma rodata-name (push, "SEARCHRO")
#pragma static-locals (push, off)

static const char srch_label[] = "Search for";
static const char srch_none[]  = "No file in this panel.";
static const char srch_res[]   = "%u file(s) contain \"%s\", now tagged.";
static const char srch_cancel[] = "%u file(s) tagged; search cancelled.";

/* SEARCH can spend several seconds opening and scanning a large panel.  The
 * keyboard strobe is safe to poll between files; consume ESC so it cannot
 * leak into the next menu action. */
static unsigned char search_cancel(void)
{
    if (*(volatile unsigned char*)0xC000 != 155) return 0;
    (void)*(volatile unsigned char*)0xC010;
    return 1;
}

/* fread (already resident) rather than fgetc (which would link into the main
 * window, which is full): one block in copy_buf, a sliding window of plen
 * bytes over it, case-insensitive. */
static unsigned char file_has(const char* path, const char* pat, unsigned char plen)
{
    FILE* f = fopen(path, "rb");
    unsigned char win[16], wlen = 0, i, c;
    unsigned int n, j;
    if (!f) return 0;
    for (;;) {
        n = fread(copy_buf, 1, 512, f);
        for (j = 0; j < n; ++j) {
            c = copy_buf[j] & 0x7F;
            if (c >= 'a' && c <= 'z') c -= 32;
            if (wlen < plen) win[wlen++] = c;
            else { for (i = 1; i < plen; ++i) win[i - 1] = win[i]; win[plen - 1] = c; }
            if (wlen == plen) {
                for (i = 0; i < plen && win[i] == (unsigned char)pat[i]; ++i) ;
                if (i == plen) { fclose(f); return 1; }
            }
        }
        if (n < 512) break;
    }
    fclose(f);
    return 0;
}

void __fastcall__ search_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    unsigned char plen, i, found = 0, cancelled = 0;
    (void)a;
    if (!pan->count) { message(srch_none); return; }
    if (!prompt(srch_label, 0, 0)) return;          /* input: the text, in upper case */
    plen = strlen(input);
    if (!plen || plen > 15) return;
    for (i = 0; i < pan->count; ++i) {
        if (search_cancel()) { cancelled = 1; break; }
        if (is_dir(&pan->e[i]) || !build_full(full, pan, &pan->e[i])) continue;
        if (file_has(full, input, plen)) { set_tag(pan, i, 1); ++found; }
    }
    draw_panel(active);
    if (cancelled) sprintf(question, srch_cancel, found);
    else sprintf(question, srch_res, found, input);
    message(question);
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* The BINARY2 overlay: extract a Binary II archive (.BNY), in            */
/* A2FILE/BINARY2.PLG. Run from the ! menu. Each file: a 128-byte header  */
/* (magic 0A 47 4C), the data (EOF bytes) padded to a multiple of 128. No */
/* compression: a plain copy. tools/mkbny.py writes and reads back the    */
/* same format.                                                           */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "BINARY2")
#pragma rodata-name (push, "BINARY2RO")
#pragma static-locals (push, off)

static const char b2_pick[]  = "Select a Binary II archive.";
static const char b2_notdir[] = "Other panel must be a ProDOS folder.";
static const char b2_bad[]   = "Not a Binary II archive.";
static const char b2_path[]  = "%s/%s";
static const char b2_done[]  = "%u file(s) extracted.";

/* A ProDOS name out of the one in the archive: letters, digits and
 * periods, a letter first, 15 at most. */
static void b2_name(const unsigned char* src, unsigned char len, char* out)
{
    unsigned char i, n = 0, start = 0;
    char c;
    for (i = 0; i < len; ++i) if (src[i] == '/' || src[i] == ':') start = i + 1;
    for (i = start; i < len && n < 15; ++i) {
        c = src[i];
        if (c >= 'a' && c <= 'z') c -= 32;
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.')) c = '.';
        if (!n && !(c >= 'A' && c <= 'Z')) { out[n++] = 'X'; if (n == 15) break; }
        out[n++] = c;
    }
    if (!n) out[n++] = 'X';
    out[n] = 0;
}

/* Small overlay, message() is enough; big (ARCH=6502, where it overflows
 * the window: A2FC_BIG_BINARY2 with the header flag), overlay_run reloads
 * the panels on return and would erase the message: so it goes into note,
 * which it displays afterwards. */
#ifdef A2FC_BIG_BINARY2
#define b2_say(m) strcpy(note, m)
#else
#define b2_say(m) message(m)
#endif

void __fastcall__ binary2_entry(const struct A2fcApi* a)
{
    struct Panel* oth = &panels[!active];
    FILE* in;
    FILE* out;
    unsigned long eof, pad;
    unsigned int n, k;
    unsigned char more = 1, done = 0;
    char name[17];
    (void)a;
    if (!selected.name[0] || is_dir(&selected) || !full[0]) { b2_say(b2_pick); return; }
    if (!oth->path[0] || oth->fs) { b2_say(b2_notdir); return; }
    in = fopen(full, "rb");
    if (!in) { report_error("Open"); return; }
    while (more) {
        if (fread(copy_buf, 1, 128, in) != 128) break;
        if (copy_buf[0] != 0x0A || copy_buf[1] != 0x47 || copy_buf[2] != 0x4C) {
            if (!done) { b2_say(b2_bad); fclose(in); return; }
            break;
        }
        /* EOF on 3 bytes ($14-$16), the name at $17/$18, "more follows" at $7F.
         * All of the header is read BEFORE the copy loop, which overwrites
         * copy_buf. The padding to a multiple of 128 is computed here. */
        eof = (unsigned long)copy_buf[0x14] | ((unsigned long)copy_buf[0x15] << 8)
              | ((unsigned long)copy_buf[0x16] << 16);   /* EOF on 3 bytes, $14-$16 */
        pad = (128 - (eof & 127)) & 127;
        more = copy_buf[0x7F] != 0;                       /* "more follows" at $7F */
        if (copy_buf[0x17] > 64 || strlen(oth->path) + 17 >= PATH_LEN) {
            fclose(in); b2_say(b2_bad); return;
        }
        b2_name(copy_buf + 0x18, copy_buf[0x17], name);   /* name: length at $17, text at $18 */
        _filetype = copy_buf[4];
        _auxtype = copy_buf[5] | (copy_buf[6] << 8);
        sprintf(other_full, b2_path, oth->path, name);
        out = new_output(other_full);
        if (!out) { b2_say("Create failed; existing files kept."); fclose(in); return; }
        while (eof) {
            n = eof > 512 ? 512 : (unsigned int)eof;
            k = fread(copy_buf, 1, n, in);
            if (!k || fwrite(copy_buf, 1, k, out) != k) break;
            eof -= k;
        }
        if (fclose(out)) eof = 1;
        if (eof) { remove(other_full); b2_say("Extract failed: read/write error."); fclose(in); return; }
        ++done;
        if (pad) fseek(in, (long)pad, SEEK_CUR);
    }
    fclose(in);
#ifndef A2FC_BIG_BINARY2
    refresh_both();                    /* the other panel shows what just arrived (big: overlay_run does it) */
#endif
    sprintf(question, b2_done, done);
    b2_say(question);
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

#define HEX_ROWS 20
#define HEX_PAGE (HEX_ROWS * 16)

/* The HEX overlay: the hex viewer, in A2FILE/HEX.PLG. */
#pragma code-name (push, "HEX")
#pragma rodata-name (push, "HEXRO")
static const char hx_offset[] = "%05lX ";
static const char hx_keys[] = "G Go,R Top,E End,ESC";
static const char hx_go[] = "File offset";
static const char hx_bad[] = "Past EOF. Press a key.";
static const char hx_byte[] = "%02X ";
static const char hx_status[] = "%-22.22s %lu bytes page %u/%u";

static void view_hex(const char* path, unsigned long size)
{
    unsigned int page = 0, pages = (unsigned int)((size + HEX_PAGE - 1) / HEX_PAGE), n, i, j;
    char key;
    unsigned long off;
    vf = fopen(path, "rb");
    if (!vf) { report_error("Open"); return; }
    a2fc_view = 3;
    if (!pages) pages = 1;
    for (;;) {
        fseek(vf, (long)page * HEX_PAGE, SEEK_SET);
        n = fread(copy_buf, 1, HEX_PAGE, vf);
        clrscr();
        for (i = 0; i < n; i += 16) {
            gotoxy(0, i / 16);
            cprintf(hx_offset, (unsigned long)page * HEX_PAGE + i);
            for (j = 0; j < 16; ++j) {
                if (i + j < n) cprintf(hx_byte, copy_buf[i + j]);
                else cputs("   ");
            }
            cputc(' ');
            for (j = 0; j < 16 && i + j < n; ++j) {
                unsigned char c = copy_buf[i + j] & 0x7F;
                cputc(c < 32 || c == 127 ? '.' : (char)c);
            }
        }
        bar_begin();
        cprintf(hx_status, path, size, page + 1, pages);
        keys_bar(52, hx_keys);
        key = cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN) && page + 1 < pages) ++page;
        if (key == 'r' || key == 'R') page = 0;
        if (key == 'e' || key == 'E') page = pages - 1;
        if ((key == 'g' || key == 'G') && prompt(hx_go, 0, 7)) {
            /* A file offset is independent of the 16-bit CPU address bus.
             * Seven hex digits cover the complete 32-MB XL image. */
            {
                unsigned char cut = input[3];
                input[3] = 0;
                off = (unsigned long)hex_value(input) << 16;
                input[3] = cut;
                off |= hex_value(input + 3);
            }
            if (off < size || !off) page = (unsigned int)(off / HEX_PAGE);
            else { message(hx_bad); cgetc(); }
        }
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && page) --page;
    }
    fclose(vf);
    a2fc_view = 0;
    draw_all();
}

void __fastcall__ hex_entry(const struct A2fcApi* a)
{
    (void)a;
    if (full[0]) view_hex(full, panels[active].e[panels[active].cursor].size);
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Preferences: A2FILE/A2FILE.CFG -- in the language card                 */
/* ---------------------------------------------------------------------- */

#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Image                                                                  */
/* ---------------------------------------------------------------------- */

/* The image formats recognised, from the first eight bytes and the size:
 * a raw HGR page (8,192 or 8,184 bytes), a raw DHGR page (16,384: AUX then
 * MAIN, the file order of A2FC and of the game), an HGRR v1 stream (RLE,
 * 8,192 decompressed) or a DHRR v1 stream (RLE, 16,384). */
enum { IMG_NONE, IMG_HGR, IMG_DHGR, IMG_HGRR, IMG_DHRR };
static const char* const IMG_NAMES[] = { "not an image", "HGR raw", "DHGR raw", "HGR RLE", "DHGR RLE" };
static const unsigned long IMG_BYTES[] = { 0, 8192, 16384, 8192, 16384 };
static unsigned char img_kind;
static unsigned char aux_dirty;    /* an image wrote to AUX: /RAM must be rebuilt */
static const char* ram_note;
static const char RAM_NOTE[] = "  /RAM was rebuilt empty.";

#define HGR_MAIN ((unsigned char*)0x2000)
#define OVERLAY ((unsigned char*)0x1B00)   /* the overlay window, see a2fc.cfg */

/* Plain HGR, page 1, without double mode: 80COL and DHIRES off.
 * TXTCLR ($C050) LAST: turning graphics on before HIRES is armed shows the
 * text page read back in low resolution -- a checkerboard of colours for the
 * duration of two writes, just enough for one frame on a slow monitor.
 *
 * An RGB card (Le Chat Mauve, Video-7) holds a two-bit latch clocked by the
 * $C05E -> $C05F edge, its data being 80COL: raising AN3 for plain HGR
 * therefore clocks it, whether we want it or not. By turning 80COL off
 * BEFORE that edge, we pushed a zero into it on every image -- two HGRs in
 * a row and the latch fell to BW560, a mode the program never asked for. So
 * we clock it with ones, twice, which leaves it on COL140, its power-on
 * state; 80COL then drops again, plain HGR being read in 40 columns. Without
 * an RGB card these writes change nothing: they are the same soft switches
 * as before. */
static void show_hgr(void)
{
    *(unsigned char*)0xC000 = 0;                              /* 80STORE off */
    *(unsigned char*)0xC00D = 0;                              /* 80COL on: the latch data */
    *(unsigned char*)0xC05E = 0; *(unsigned char*)0xC05F = 0; /* one edge, data 1 */
    *(unsigned char*)0xC05E = 0; *(unsigned char*)0xC05F = 0; /* two: COL140, AN3 high */
    *(unsigned char*)0xC00C = 0;                              /* 80COL off */
    *(unsigned char*)0xC057 = 0; *(unsigned char*)0xC054 = 0; *(unsigned char*)0xC052 = 0;
    *(unsigned char*)0xC050 = 0;
}

/* The path of a file stored next to the program: "/VOL/A2FILE/name", in
 * other_full, derived from the configuration's. Empty if the program does
 * not know where it came from. */
static void a2file_file(const char* name)
{
    char* slash;
    strcpy(other_full, cfg_path);
    slash = strrchr(other_full, '/');
    if (slash) strcpy(slash + 1, name);
    else other_full[0] = 0;
}

/* Start with slot 6, drive 2; the swap prompt can select drive 1. Resolve
 * the volume each time: swapping or renaming must not leave a cached path. */
static unsigned char companion_unit = 0xE0;
static unsigned char companion_path(const char* suffix)
{
    unsigned char parms[4], n;
    parms[0] = 2; parms[1] = companion_unit;
    parms[2] = (unsigned char)((unsigned)copy_buf & 0xFF);
    parms[3] = (unsigned char)((unsigned)copy_buf >> 8);
    if (mli_call(0xC5, parms) || !(n = copy_buf[0] & 15)) return 0;
    other_full[0] = '/';
    memcpy(other_full + 1, copy_buf + 1, n);
    strcpy(other_full + n + 1, suffix);
    return 1;
}

static unsigned char disk_question(const char* name)
{
    char key;
    question_begin();
    cprintf("Insert %s S6,D%u: %s D1/2 RET ESC",
            question, (companion_unit >> 7) + 1, name);
    revers(0);
    key = cgetc();
    if (key == KEY_ESC) return 0;
    if (key == '1' || key == '2') companion_unit = key == '1' ? 0x60 : 0xE0;
    return 1;
}

static unsigned char ask_disk(const char* name)
{
    FILE* f;
    char* colon;
    /* The same catalog travels on every category disk. Its description
     * starts with the exact volume name, so routing cannot drift from the
     * distribution manifest and works during a single-drive swap. */
    strcpy(question, "tool disk");
    a2file_file("EXTRAS.CAT");
    f = fopen(other_full, "rb");
    if (!f && companion_path("/A2FILE/EXTRAS.CAT")) f = fopen(other_full, "rb");
    if (f) {
        while (fread(copy_buf, 1, 78, f) == 78) {
            copy_buf[77] = 0;
            if (strncmp((char*)copy_buf, name, 12)) continue;
            colon = strchr((char*)copy_buf + 12, ':');
            if (colon && colon > (char*)copy_buf + 12 && colon <= (char*)copy_buf + 27) {
                *colon = 0; strcpy(question, (char*)copy_buf + 12);
            }
            break;
        }
        fclose(f);
    }
    return disk_question(name);
}

/* Local overlays take precedence. A stale local file is still rejected by
 * the caller: the companion only supplies files absent from the boot disk. */
static FILE* open_overlay(const char* name, unsigned char ask)
{
    FILE* f;
    for (;;) {
    a2file_file(name);
    strcat(other_full, ".PLG");
    f = fopen(other_full, "rb");
    if (!f && companion_path("/A2FILE/")) {
        strcat(other_full, name);
        strcat(other_full, ".PLG");
        f = fopen(other_full, "rb");
    }
    if (f || !ask) return f;
    if (!ask_disk(name)) return 0;
    }

}

/* Loads the overlay `name` -- A2FILE/NAME.PLG, a BIN file linked with the
 * program -- into the $1B00 window, unless it is already there: leafing
 * through a directory of images rereads nothing. Its first eight bytes are
 * the header described in a2fc_plugin.h: the signature word is the address
 * of main in the link that produced it (overlay.s), or PLUGIN_MAGIC for a
 * third-party overlay, which only `any` accepts (the overlay menu); a file
 * from another build is refused, like a missing file, and the message line
 * says so. A big overlay (OVERLAY_BIG) also takes the graphics page: the
 * tags are set aside before overwriting it, and overlay_run rereads the
 * panels on return. Returns 0 if nothing is loaded. */
/* 0 outside media, 1 awaiting consent, 2 accepted for this browsing session.
 * Only foreground viewers inherit this scope; every exit clears it. No AUX
 * write or /RAM reconstruction happens in this gate itself. */
static unsigned char media_aux_scope;
static unsigned char confirm_aux(void)
{
    if (media_aux_scope == 2) return 1;
    if (!confirm("Uses AUX memory: ALL /RAM files will be LOST. Continue?")) return 0;
    if (media_aux_scope) media_aux_scope = 2;
    return 1;
}
#define OVL ((struct Overlay*)OVERLAY_WINDOW)
static unsigned char load_overlay(const char* name, unsigned char any)
{
    FILE* f;
    unsigned char ok = 0;
    if (!strcmp(overlay_loaded, name))
        return !(OVL->flags & OVERLAY_AUX) || confirm_aux();
    overlay_loaded[0] = 0;
    f = open_overlay(name, 1);
    if (f) {
        if (fread(OVERLAY_WINDOW, 1, 8, f) == 8
            && (OVL->signature == a2fc_link_id || (any && (OVL->signature == PLUGIN_MAGIC || OVL->signature == MEDIA_PLUGIN_MAGIC)))) {
            if ((OVL->flags & OVERLAY_AUX) && !confirm_aux()) {
                fclose(f); return 0;
            }
            if ((OVL->flags & OVERLAY_BIG) && !batch_snapshot) keep_tags(1);
            fread(OVERLAY_WINDOW + 8, 1, (OVL->flags & OVERLAY_BIG ? OVERLAY_LARGE : OVERLAY_SMALL) - 8, f);
            strcpy(overlay_loaded, name);
            ok = 1;
        }
        fclose(f);
    }
    /* A one-drive swap loaded the code, but its input may be on the disk
     * just removed. Restore that volume before the overlay opens its file. */
    if (ok && companion_unit == 0x60) {
        char* slash;
        strncpy(other_full, full[0] == '/' ? full : cfg_path, 16);
        other_full[16] = 0;
        slash = strchr(other_full + 1, '/'); if (slash) *slash = 0;
        strcpy(question, other_full + 1);
        while (!exists(other_full)) {
            if (!disk_question(name)) {
                overlay_loaded[0] = 0;
                if (OVL->flags & OVERLAY_BIG) {
                    read_panel(0); read_panel(1); keep_tags(0); draw_all();
                }
                return 0;
            }
        }
    }
    if (!ok) {
        clear_row(22);
        gotoxy(0, 22);
        cprintf("A2FILE/%s.PLG is missing or stale on this volume.", name);
    }
    return ok;
}
#define overlay(name) load_overlay(name, 0)

/* Runs the overlay `name` through its entry point, with `arg` (the key
 * that invokes it, 0 from the menu) in the service table. A big overlay
 * hands control back on a graphics page of its own: the screen returns to
 * text, both panels are reread, the tags restored, the name it left in
 * `reselect` found again, everything redrawn, and its `note` written on
 * row 22. */
static struct A2fcApi api;
static void select_name(struct Panel* pan, const char* name);
static unsigned char __fastcall__ prepare_audio(unsigned char arg);
#include "media.h"
static void overlay_run(const char* name, unsigned char arg)
{
    struct Panel* pan = &panels[active];
    unsigned char big, media=media_type(name), dir;
    media_aux_scope = media ? 1 : 0;
again:
    if(media && !media_prepare(media)) {draw_all();goto media_done;}
    /* The entry under the cursor and its path, kept safe: a big overlay
     * covers the entry table as it loads. */
    if (arg != 'B' && !batch_snapshot) {
    full[0] = 0;
    if (pan->count) { selected = pan->e[pan->cursor]; build_full(full, pan, &selected); }
    else selected.name[0] = 0;
    }
    if (!load_overlay(name, 1)) goto media_done;
    /* A big overlay has already set the tags aside and covered the entry
     * table as it loaded (load_overlay): even without an entry point, the
     * panels must be reread, otherwise the screen keeps the upper half of
     * the overlay in place of the entries. A missing entry point can only
     * come from a malformed third-party overlay (PLUGIN_MAGIC without an
     * entry). */
    big = OVL->flags & OVERLAY_BIG;
    api.arg = prepare_audio(arg);
    reselect[0] = 0;
    note[0] = 0;
    if (OVL->entry) OVL->entry(&api);
    else { extern const char msg_noentry[]; strcpy(note, msg_noentry); }
    if (big) {
        overlay_loaded[0] = 0;   /* its upper half is already covered by the tables */
        switch_to_text();
        read_panel(0);
        read_panel(1);
        keep_tags(0);
        if (reselect[0]) select_name(&panels[active], reselect);
        draw_all();
        if (note[0]) message(note);
    } else if (!OVL->entry) message(note);
    if(media && media_request) {
        dir=media_request==KEY_RIGHT;
        pan->first=media_first[dir];
        if(!read_panel(active))goto media_done;
        keep_tags(0);
        select_name(pan,album[dir]);
        if(!pan->count || strcmp(pan->e[pan->cursor].name,album[dir]))goto media_done;
        name=media_names[media-1];
        goto again;
    }
media_done:
    media_aux_scope = 0;
}

#pragma code-name (push, "LC")
#pragma rodata-name (push, "LC")
static const char batch_cancel[] = "Cancelled; remaining sources kept.";
/* BATCH keeps its snapshot above its own code. MOVE may use the whole
 * graphics page; the next phase takes a fresh snapshot after panel refresh. */
static void batch_stage(unsigned char arg)
{
    struct Panel* pan = &panels[active];
    MB->ready = 255;
    keep_tags(1);
    batch_snapshot = 1;
    full[0] = 0;
    memmove((void*)0x3000, pan->e, pan->count * sizeof(struct Entry));
    overlay_run("BATCH", arg);
    batch_snapshot = 0;
    if (MB->ready == 255) {
        MB->ready = 0;
        overlay_loaded[0] = 0;
        read_panel(0); read_panel(1); keep_tags(0); draw_all();
        strcpy(note, "Batch unavailable; any A2MOVE.LST kept.");
        message(note);
    }
}

static void move_marked(void)
{
    memset(MB, 0, sizeof *MB);
    batch_stage('W');
    if (!MB->owned || !MB->ready) return;
    progress_abort = 0;
    while (MB->index < MB->count) {
        batch_stage('R');
        if (!MB->ready) { strcpy(MB->reason, note); break; }
        overlay_run("MOVE", 'B');
        if (!reselect[0]) { strcpy(MB->reason, note); break; }
        ++MB->index;
        if (abort_key()) { strcpy(MB->reason, batch_cancel); break; }
    }
    batch_stage('F');
}

#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* The IMAGE overlay: the loader and the decoder, in A2FILE/IMAGE.PLG     */
/* ---------------------------------------------------------------------- */

/* Everything from here to the pop is linked separately, into the $1B00
 * window: ordinary RAM, at the same price as $4000, but which costs the
 * resident program nothing. The core knows how to recognise an image
 * (image_kind) and load the overlay; it no longer knows how to decode.
 * The text and hex viewers (TEXT, HEX), deletion (DELETE) and help (HELP)
 * are other overlays, each marked the same way. */
#pragma code-name (push, "IMAGE")
#pragma rodata-name (push, "IMAGERO")

/* Routes writes to $2000-$3FFF to AUX (80STORE + HIRES + PAGE2), as
 * hgr_loader.s does; the MLI then writes there too. */
static void aux_writes(unsigned char on)
{
    if (on) { *(unsigned char*)0xC002 = 0; *(unsigned char*)0xC004 = 0; *(unsigned char*)0xC057 = 0; *(unsigned char*)0xC001 = 0; *(unsigned char*)0xC055 = 0; }
    else { *(unsigned char*)0xC054 = 0; *(unsigned char*)0xC000 = 0; }
}

/* An RLE v1 stream (HGRR or DHRR) decompressed to $2000: `bytes` bytes,
 * the first half of a DHRR going to AUX (by AUXMOVE, see advance). The
 * file is open on the header. A run may straddle the boundary between the
 * two planes: it is written in pieces, and the plane switches on crossing
 * $4000. */
static unsigned int dn;
static unsigned char dplane, dplanes;

/* Advances by `n` bytes written; switches plane at $4000. */
static void advance(unsigned int n)
{
    dn += n;
    if (dn == 8192) {
        dn = 0; ++dplane;
        if (dplane == 1 && dplanes == 2) {
            /* The first plane of a DHRR is the auxiliary bank's: decoded in
             * the main bank, it goes there by AUXMOVE, like the raw plane.
             * The file is thus never read under an AUX routing of
             * $2000-$3FFF (80STORE + PAGE2), a routing that also moves
             * $400-$7FF: on the //c, the SmartPort firmware keeps its state
             * in the holes of the text page, and a read done under that
             * routing never came back. */
            aux_hgr_to_aux();
        }
    }
}

static unsigned char decode_rle(FILE* f, unsigned int bytes)
{
    unsigned int count, chunk;
    int t, v;
    dn = 0; dplane = 0; dplanes = bytes > 8192 ? 2 : 1;
    vf = f;
    view_seek(8);
    while (dplane < dplanes) {
        t = view_getc();
        if (t < 0) break;
        if (t & 0x80) {
            count = (t & 0x7F) + 3;
            v = view_getc();
            if (v < 0) break;
            while (count && dplane < dplanes) {
                chunk = count < 8192 - dn ? count : 8192 - dn;
                memset(HGR_MAIN + dn, v, chunk);
                count -= chunk;
                advance(chunk);
            }
        } else {
            count = t + 1;
            while (count && dplane < dplanes) {
                /* empty buffer: view_getc refills it and takes one byte, given back here */
                if (vpos >= vlen) { if (view_getc() < 0) { count = 0xFFFF; break; } --vpos; }
                chunk = vlen - vpos;
                if (chunk > count) chunk = count;
                if (chunk > 8192 - dn) chunk = 8192 - dn;
                memcpy(HGR_MAIN + dn, copy_buf + vpos, chunk);
                vpos += chunk;
                count -= chunk;
                advance(chunk);
            }
            if (count == 0xFFFF) break;
        }
    }
    aux_writes(0);
    return dplane == dplanes;
}


/* Identifies and loads the image `full` (entry `e`) into page 1. Returns
 * the format, IMG_NONE if the file is not an image. */
static unsigned char load_image(const struct Entry* e)
{
    FILE* f;
    unsigned int size = page_size(&e->size) ? (unsigned int)e->size : 0;
    unsigned char kind = IMG_NONE, ok = 0;
    /* The 80-column firmware leaves 80STORE armed and uses PAGE2 to reach
     * the auxiliary bank. With HIRES still active (a previous image),
     * $2000-$3FFF would follow that routing and the read would go to AUX:
     * screen frozen on the old image, or half an image. So we always start
     * from a known MAIN routing. */
    aux_writes(0);
    f = fopen(full, "rb");
    if (!f) return IMG_NONE;
    if (fread(copy_buf, 1, 8, f) == 8) {
        if (!memcmp(copy_buf, "DHRR\1\0\0\x40", 8)) kind = IMG_DHRR;
        else if (!memcmp(copy_buf, "HGRR\1\0\0\x20", 8)) kind = IMG_HGRR;
        else if (size > 8192) kind = IMG_DHGR;   /* 16,384 or 16,376 */
        else if (size) kind = IMG_HGR;
    }
    if (kind == IMG_DHRR) { aux_dirty = 1; ok = decode_rle(f, 16384); }
    else if (kind == IMG_HGRR) ok = decode_rle(f, 8192);
    else if (kind == IMG_HGR) { rewind(f); ok = fread(HGR_MAIN, 1, 8192, f) >= 8184; }
    else if (kind == IMG_DHGR) {
        /* The auxiliary plane is read into main $2000, then goes to AUX by
         * AUXMOVE (aux_hgr_to_aux), not by an MLI call that would itself
         * write into a window routed to AUX: ProDOS only promises its calls
         * in main memory, and the 80STORE trick, though it works on many
         * machines, is not guaranteed -- where it failed, the image became
         * "not an image". The main plane is then read straight in: that is
         * ordinary memory. */
        aux_dirty = 1;
        rewind(f);
        ok = fread(HGR_MAIN, 1, 8192, f) == 8192;
        /* The main plane may be eight bytes short, like the single page:
         * what is missing is the screen hole nobody displays. */
        if (ok) { aux_hgr_to_aux(); ok = fread(HGR_MAIN, 1, 8192, f) >= 8184; }
    }
    fclose(f);
    return ok ? kind : IMG_NONE;
}

static void view_image(void);
void __fastcall__ image_entry(const struct A2fcApi* a)
{
    (void)a;
    view_image();
}
#pragma rodata-name (pop)
#pragma code-name (pop)

static void loading(const char* name)
{
    clear_row(22);
    gotoxy(0, 22);
    cprintf("Loading %s...", name);
}

/* The image under the cursor, full screen, HGR or DHGR according to what
 * the file holds. Left / Right move to the previous / next image of the
 * same directory without going back to the panels: the DHGR directory is
 * leafed through like an album, and the cursor follows. Any other key
 * returns, and the message line says which format was recognised.
 *
 * The text screen is never cleared: the panels stay in $400-$7FF for the
 * whole browsing session, and only what changes is rewritten -- the two
 * cursor lines, the info line, the message line. On return, a panel is
 * redrawn only if rereading it shows something other than on entry (/RAM
 * rebuilt from scratch, floppy changed). */
static void view_image(void)
{
    struct Panel* pan = &panels[active];
    unsigned char index = pan->cursor, next, p, dir;
    char key;
    aux_dirty = 0;
    /* The image covers the entry tables: the tags are set aside, the panels
     * reread on return, and the active panel before each next image so as
     * to find the neighbour there. */
    keep_tags(1);
    for (p = 0; p < 2; ++p) seen[p] = panel_hash(&panels[p]);
    a2fc_view = 1;
    loading(pan->e[index].name);
    for (;;) {
        full[0] = 0;
        if (!build_full(full, pan, &pan->e[index])) break;
        strcpy(input, pan->e[index].name);
        /* The neighbours that look like an image, on each side: their names
         * survive the image that is about to cover the table. An arrow thus
         * knows, without rereading the directory, whether it has somewhere
         * to go, and announces the next one before even looking for it. */
        for (dir = 0; dir < 2; ++dir) {
            album[dir][0] = 0;
            next = index;
            for (;;) {
                if (!dir) { if (!next) break; --next; }
                else { if (next + 1 >= pan->count) break; ++next; }
                if (image_kind(&pan->e[next]) == 1) { strcpy(album[dir], pan->e[next].name); break; }
            }
        }
        /* NOTHING may write to $2000-$3FFF while the graphics page is on
         * the air: otherwise we saw the previous image being eaten away by
         * the entry table, then the new one painted band by band (and, in
         * DHGR, the AUX plane before the MAIN plane). So the screen stays
         * on text -- the panels, intact in $400-$7FF -- for the duration of
         * the decoding, and the image lights up only once complete. */
        img_kind = load_image(&pan->e[index]);
        if (img_kind == IMG_NONE) break;
        if (img_kind == IMG_HGR || img_kind == IMG_HGRR) show_hgr();
        else switch_to_hgr();
        /* An arrow with no neighbour on its side does nothing: the image stays. */
        do key = cgetc(); while ((key == KEY_LEFT || key == KEY_RIGHT) && !album[key == KEY_RIGHT][0]);
        if (key != KEY_LEFT && key != KEY_RIGHT) break;
        dir = key == KEY_RIGHT;
        /* Back to text before read_panel rewrites the entry table, hence the
         * graphics page; the neighbour's name is shown while it is looked
         * for, and the cursor joins it as soon as it is there. */
        switch_to_text();
        loading(album[dir]);
        read_panel(active);
        keep_tags(0);
        for (next = 0; next < pan->count && strcmp(pan->e[next].name, album[dir]); ++next) {}
        if (next >= pan->count) break;   /* the directory changed under our feet */
        land(next);
        index = next;
    }
    switch_to_text();
    a2fc_view = 0;
    /* The price of DHGR: its auxiliary half ($2000-$3FFF in the AUX bank) is
     * memory that the ProDOS virtual disk uses -- 18 blocks, measured on the
     * bench, and that is exactly where the data of a file written to /RAM
     * begins. They are lost, so the volume is wrong: the next write would
     * return anything at all. We rebuild it from scratch through its own
     * driver, which gives an empty and consistent volume, and we say so --
     * as soon as a DHGR load has WRITTEN to AUX, whether it succeeded or not
     * (a truncated file has already done the damage), even if the last image
     * was an HGR. A plain HGR image only writes to the main bank and
     * triggers nothing. */
    ram_note = aux_dirty && ram_format() ? RAM_NOTE : (const char*)"";
    /* The tables are reread; the screen, though, has not moved, and a panel
     * that shows the same thing as on entry is not redrawn. read_panel
     * brings the cursor back inside the panel if it has shrunk (directory
     * changed under our feet, /RAM rebuilt under whoever was in it). */
    for (p = 0; p < 2; ++p) read_panel(p);
    keep_tags(0);
    for (p = 0; p < 2; ++p) if (panel_hash(&panels[p]) != seen[p]) draw_panel(p);
    draw_status();
    draw_info();
    if (!full[0]) { too_long(); return; }
    clear_row(22);
    gotoxy(0, 22);
    if (img_kind == IMG_NONE) cprintf("%s: not an image.", input);
    else cprintf("%s: %s, %lu bytes on screen.%s", input, IMG_NAMES[img_kind], IMG_BYTES[img_kind], ram_note);
}

/* ---------------------------------------------------------------------- */
/* Text editor -- the big EDIT overlay, in A2FILE/EDIT.PLG                */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "EDIT")
#pragma rodata-name (push, "EDITRO")
static const char ed_savekeys[] = "S Save,X Save and exit,Q Quit without saving,ESC Continue editing";
static const char ed_status[]  = " %-30.30s  Line %u  Col %u  %u/%u bytes %s";
static const char ed_openf[]   = "Open failed.";
static const char ed_buffull[] = "Buffer full.";
static const char ed_nodir[]   = "Open a directory first.";
static const char ed_exists[]  = "File exists: select it to edit.";
static const char ed_toobig[]  = "Too big for the editor (5 KB).";

/* The text lives in the HGR MAIN page, above the overlay's code
 * ($2C00-$3FEF: 5 KB), CR line endings, bit 7 stripped on loading.
 * The cursor is an offset into the buffer; the screen shows 22 lines from
 * `etop`, the start of a line, with no wrapping of long lines. */
#define EDIT_ROWS 22
static unsigned char efresh;
static unsigned int elen, ecur, etop, ewant;
static unsigned char edirty, etype;
static unsigned int eaux;

static unsigned int line_start(unsigned int pos)
{
    while (pos && EDIT_BUF[pos - 1] != '\r') --pos;
    return pos;
}

static unsigned int line_end(unsigned int pos)
{
    while (pos < elen && EDIT_BUF[pos] != '\r') ++pos;
    return pos;
}

static unsigned int next_line(unsigned int pos)
{
    pos = line_end(pos);
    return pos < elen ? pos + 1 : pos;
}

/* Redraws the lines from `from` (screen row number) on. */
static void edit_draw(unsigned char from)
{
    unsigned int pos = etop;
    unsigned char row, col;
    for (row = 0; row < from; ++row) pos = next_line(pos);
    for (row = from; row < EDIT_ROWS; ++row) {
        gotoxy(0, row);
        col = 0;
        while (pos < elen && EDIT_BUF[pos] != '\r') {
            if (col < 79) cputc(EDIT_BUF[pos] < 32 ? '.' : EDIT_BUF[pos]);
            ++pos;
            ++col;
        }
        if (col < 79) cclear(79 - col);
        if (pos < elen) ++pos;
    }
}

static void edit_status(void)
{
    unsigned int line = 0, pos = 0, ls = line_start(ecur);
    while (pos < ls) { pos = next_line(pos); ++line; }
    bar_begin();
    revers(1);
    cprintf(ed_status, full, line + 1, ecur - ls + 1, elen, EDIT_MAX, edirty ? "*" : " ");
    revers(0);
    keys_bar(69, "ESC Menu");
}

/* Places the cursor on screen; scrolls if the line is not visible. */
static unsigned char edit_place(void)
{
    unsigned int ls = line_start(ecur), pos;
    unsigned char row, scrolled = 0;
    while (ls < etop) { etop = line_start(etop - 1); scrolled = 1; }
    for (;;) {
        pos = etop;
        for (row = 0; row < EDIT_ROWS && pos < ls; ++row) pos = next_line(pos);
        if (pos == ls && row < EDIT_ROWS) break;
        etop = next_line(etop);
        scrolled = 1;
    }
    if (scrolled) edit_draw(0);
    edit_status();
    gotoxy(ecur - ls < 79 ? (unsigned char)(ecur - ls) : 79, row);
    return scrolled;
}

static void edit_vertical(int lines)
{
    unsigned int ls = line_start(ecur), target = ls;
    while (lines > 0 && next_line(target) < elen + 1 && line_end(target) < elen) { target = next_line(target); --lines; }
    while (lines < 0 && target) { target = line_start(target - 1); ++lines; }
    ecur = target + ewant;
    if (ecur > line_end(target)) ecur = line_end(target);
}

static unsigned char edit_insert(char c)
{
    if (elen >= EDIT_MAX) { return 0; }
    memmove(EDIT_BUF + ecur + 1, EDIT_BUF + ecur, elen - ecur);
    EDIT_BUF[ecur++] = c;
    ++elen;
    edirty = 1;
    return 1;
}

static void edit_delete(void)
{
    if (ecur >= elen) return;
    memmove(EDIT_BUF + ecur, EDIT_BUF + ecur + 1, elen - ecur - 1);
    --elen;
    edirty = 1;
}

/* Stage and read back the complete save before renaming the original.
 * The text pagination buffer is idle while editing; it holds two paths. */
static const char ed_safety_0[] = "A2FC.ED.BAK must be recovered first.";
static const char ed_safety_1[] = "Save failed; original kept.";
static const char ed_safety_2[] = "Save refused; original kept.";
static const char ed_safety_3[] = "Save failed: recover A2FC.EDIT / A2FC.ED.BAK.";
static const char ed_safety_4[] = "Saved; A2FC.ED.BAK retained.";
#define EDIT_TMP ((char*)text_starts)
#define EDIT_BAK (EDIT_TMP + PATH_LEN)
static unsigned char edit_save(void)
{
    FILE* f;
    unsigned int n, pos;
    unsigned char ok, old;
    strcpy(EDIT_TMP, full); *strrchr(EDIT_TMP, '/') = 0;
    strcpy(EDIT_BAK, EDIT_TMP);
    if (!push_name(EDIT_TMP, "A2FC.EDIT") || !push_name(EDIT_BAK, "A2FC.ED.BAK")) {
        too_long(); return 0;
    }
    if (exists(EDIT_BAK) || _oserror != 0x46) {
        message(ed_safety_0); return 0;
    }
    _filetype = etype; _auxtype = eaux;
    f = new_output(EDIT_TMP);
    if (!f) { report_error("Save"); return 0; }
    ok = fwrite(EDIT_BUF, 1, elen, f) == elen;
    if (fclose(f)) ok = 0;
    if (ok) {
        f = fopen(EDIT_TMP, "rb");
        if (!f) ok = 0;
        else {
            pos = 0;
            while ((n = fread(copy_buf, 1, 512, f)) != 0) {
                if (n > elen - pos || memcmp(copy_buf, EDIT_BUF + pos, n)) { ok = 0; break; }
                pos += n;
            }
            if (ferror(f) || pos != elen) ok = 0;
            if (fclose(f)) ok = 0;
        }
    }
    if (!ok) { remove(EDIT_TMP); message(ed_safety_1); return 0; }
    old = exists(full);
    if ((old && (efresh || (gfi[3] & 0xC2) != 0xC2)) || (!old && _oserror != 0x46) ||
        (old && rename(full, EDIT_BAK))) {
        remove(EDIT_TMP); message(ed_safety_2); return 0;
    }
    if (rename(EDIT_TMP, full)) {
        if (old) rename(EDIT_BAK, full);
        message(ed_safety_3); return 0;
    }
    if (old && remove(EDIT_BAK)) message(ed_safety_4);
    efresh = edirty = 0;
    ++a2fc_ops;
    return 1;
}

/* E: edits the file `full` (type and auxtype kept when writing), or a new
 * file if `fresh`. Returns 1 if something was written. */
static unsigned char edit_file(unsigned char fresh, unsigned char type, unsigned int aux)
{
    FILE* f;
    unsigned int i, ls;
    unsigned char row, written = 0;
    char key;
    efresh = fresh;
    elen = ecur = etop = ewant = 0;
    edirty = 0;
    etype = type;
    eaux = aux;
    if (!fresh) {
        f = fopen(full, "rb");
        if (!f) { strcpy(note, ed_openf); return 0xFF; }
        elen = fread(EDIT_BUF, 1, EDIT_MAX, f);   /* the size is checked by the caller */
        if (ferror(f) || elen != selected.size) {
            fclose(f); strcpy(note, ed_openf); return 0xFF;
        }
        if (fclose(f)) { strcpy(note, ed_openf); return 0xFF; }
        for (i = 0; i < elen; ++i) { EDIT_BUF[i] &= 0x7F; if (EDIT_BUF[i] == '\n') EDIT_BUF[i] = '\r'; }
    }
    a2fc_view = 5;
    clrscr();
    cursor(1);
    edit_draw(0);
    edit_place();
    for (;;) {
        key = cgetc();
        ls = line_start(ecur);
        row = 0xFF;                     /* 0xFF: nothing to redraw */
        switch (key) {
        case KEY_LEFT: if (ecur) --ecur; ewant = ecur - line_start(ecur); break;
        case KEY_RIGHT: if (ecur < elen) ++ecur; ewant = ecur - line_start(ecur); break;
        case KEY_UP: edit_vertical(-1); break;
        case KEY_DOWN: edit_vertical(1); break;
        case 16: edit_vertical(-(EDIT_ROWS - 2)); break;      /* Ctrl-P */
        case 14: edit_vertical(EDIT_ROWS - 2); break;         /* Ctrl-N */
        case 1: ecur = ls; ewant = 0; break;                  /* Ctrl-A */
        case 5: ecur = line_end(ecur); ewant = ecur - ls; break;   /* Ctrl-E */
        case 20: ecur = 0; ewant = 0; break;                  /* Ctrl-T */
        case 2: ecur = elen; ewant = ecur - line_start(ecur); break;   /* Ctrl-B */
        case KEY_DELETE:
            if (ecur) { --ecur; row = EDIT_BUF[ecur] == '\r' ? 0 : 1; edit_delete(); }
            ewant = ecur - line_start(ecur);
            break;
        case 4:                                               /* Ctrl-D */
            if (ecur < elen) { row = EDIT_BUF[ecur] == '\r' ? 0 : 1; edit_delete(); }
            break;
        case KEY_RETURN: if (edit_insert('\r')) row = 2; ewant = 0; break;   /* 2: from the split line */
        case KEY_TAB: for (i = 0; i < 4; ++i) edit_insert(' '); row = 1; ewant = ecur - ls; break;
        case KEY_ESC:
            bar_begin();
            keys_bar(0, ed_savekeys);
            key = cgetc();
            if (key == 's' || key == 'S') written |= edit_save();
            else if (key == 'x' || key == 'X') { if (edit_save()) { written = 1; goto leave; } }
            else if (key == 'q' || key == 'Q') { if (!edirty) goto leave; bar_begin(); keys_bar(0, "Y Discard the changes,N Keep editing"); key = cgetc(); if (key == 'y' || key == 'Y') goto leave; }
            break;
        default:
            if (key >= 32 && key < 127) { if (edit_insert(key)) row = 1; else message(ed_buffull); ewant = ecur - ls; }
            break;
        }
        /* row 0/1: redraw from the current line; 2: from the previous
         * one, whose end has just moved down to a new line. */
        if (row != 0xFF && !edit_place()) {
            unsigned int pos = etop; unsigned char r = 0;
            ls = line_start(row == 2 ? ecur - 1 : ecur);
            while (pos < ls) { pos = next_line(pos); ++r; }
            edit_draw(r);
            edit_place();
        } else edit_place();
    }
leave:
    cursor(0);
    a2fc_view = 0;
    return written;
}

/* E: edits the file under the cursor, or a new file if it is a directory;
 * the core rereads the panels and puts the cursor back on `reselect`. */
void __fastcall__ edit_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e = &selected;
    unsigned char fresh = 0;
    (void)a;
    if (!pan->count || !pan->path[0]) { strcpy(note, ed_nodir); return; }
    if (is_dir(e)) {
        if (!prompt("New text file", NULL, 0)) return;
        if (strlen(pan->path) + 1 + strlen(input) >= PATH_LEN) { extern const char msg_toolong[]; strcpy(note, msg_toolong); return; }
        sprintf(full, "%s/%s", pan->path, input);
        if (exists(full)) { strcpy(note, ed_exists); return; }
        fresh = 1;
    } else if (!build_full(full, pan, e)) { extern const char msg_toolong[]; strcpy(note, msg_toolong); return; }
    else if (e->size > (unsigned long)EDIT_MAX) { strcpy(note, ed_toobig); return; }
    strcpy(reselect, fresh ? input : e->name);
    /* The tags are sorted indexes: a new file shifts them, so they are
     * forgotten in that case. */
    if (edit_file(fresh, fresh ? 0x04 : e->type, fresh ? 0 : e->aux) == 1 && fresh) memset(picked, 0, sizeof picked);
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Mockingboard music                                                     */
/* ---------------------------------------------------------------------- */

#pragma code-name (push, "LC")
#pragma rodata-name (push, "LC")
static unsigned char __fastcall__ prepare_audio(unsigned char arg)
{
    if (!(OVL->flags & OVERLAY_AUDIO)) return arg;
    return music_detect_card();
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Help                                                                   */
/* ---------------------------------------------------------------------- */

/* The help is read from A2FILE/A2FILE.HELP (next to A2FILE.CODE), one line
 * per element: "x,y,KEY,label" for a button, "x,y,#TITLE" for a section
 * title, "x,y,~text" for plain text ('=' and '-' are keys). The text goes
 * through the HGR page, like the editor: nothing in memory
 * besides the help. */
/* The HELP overlay: the help page, in A2FILE/HELP.PLG. */
#pragma code-name (push, "HELP")
#pragma rodata-name (push, "HELPRO")
const char msg_nohelp[] = "A2FILE/A2FILE.HELP is missing.";
static const char help_file[] = "A2FILE.HELP";
static const char HELP_KEYS[] = "ANY Return to the panels";
static void view_help(void)
{
    const char* s = HELP_BUF;
    FILE* f;
    unsigned int n;
    unsigned char x, y, klen, i, kind;
    a2file_file(help_file);
    f = fopen(other_full, "rb");
    if (!f) { { extern const char msg_nohelp[]; message(msg_nohelp); }; return; }
    n = fread(HELP_BUF, 1, 0x1FF0, f);
    fclose(f);
    HELP_BUF[n] = 0;
    keep_tags(1);
    a2fc_view = 4;
    clrscr();
    while (*s) {
        x = 0; while (*s >= '0' && *s <= '9') x = x * 10 + (*s++ - '0');
        if (*s++ != ',') break;
        y = 0; while (*s >= '0' && *s <= '9') y = y * 10 + (*s++ - '0');
        if (*s++ != ',' || x >= 80 || y >= 23) break;
        gotoxy(x, y);
        kind = *s;
        if (kind == '#' || kind == '~') {         /* # section title, ~ plain text */
            if (kind == '#') { revers(1); cputc(' '); }
            ++s;
            while (*s && *s != '\n' && *s != '\r') cputc(*s++);
            if (kind == '#') { cputc(' '); revers(0); }
        } else {
            for (klen = 0; s[klen] && s[klen] != ',' && s[klen] != '\r' && s[klen] != '\n'; ++klen) {}
            if (s[klen] != ',') break;
            revers(1);
            if (klen == 1) { cputc(' '); cputc(*s); cputc(' '); }
            else for (i = 0; i < 3; ++i) cputc(i < klen ? s[i] : ' ');
            revers(0);
            cputc(' ');
            s += klen + 1;
            while (*s && *s != '\n' && *s != '\r') cputc(*s++);
        }
        while (*s == '\n' || *s == '\r') ++s;
    }
    bar_begin();
    keys_bar(0, HELP_KEYS);
    cgetc();
    a2fc_view = 0;
    read_panel(0);
    read_panel(1);
    keep_tags(0);
    draw_all();
}

void __fastcall__ help_entry(const struct A2fcApi* a)
{
    (void)a;
    view_help();
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Disk images -- the DISKIMG big overlay                                  */
/* ---------------------------------------------------------------------- */

/* W: write an image (.PO, .DSK or .DO, .2MG) to a floppy, read a floppy
 * into a new image, copy a floppy to another one -- or onto itself with a
 * single drive, swapping the floppy at each pass. The blocks go through
 * READ_BLOCK and WRITE_BLOCK, whether the driver is the Disk II's, a
 * SmartPort's (/RAM is excluded): the target floppy must already be formatted (F
 * does it), nothing here writes a track.
 *
 * The staging area of one pass: three blocks in the main bank ($3600-$3BFF,
 * above the overlay's code), and for the single-drive copy eighty more
 * blocks in the auxiliary bank, $2000-$BFFF, where /RAM lives -- which is
 * therefore rebuilt from scratch afterwards, as after a DHGR image. A
 * 280-block floppy is thus copied in four passes. The overlay's variables
 * live at $3E00, outside the low RAM. */
#pragma code-name (push, "DISKIMG")
#pragma rodata-name (push, "DISKIMGRO")

/* The texts, as named arrays: cc65 2.18 puts string literals in RODATA
 * whatever the rodata-name pragma, and those of an overlay would weigh on
 * the main window. */
static const char S_TITLE[] = "  A2 FILE CMD  -  DISK IMAGES";
static const char S_INTRO[] = "PO/DSK/DO/2MG. Target must be formatted. Disk writes are read back.";
static const char S_W[] = "W  Write %s to a disk";
static const char S_R[] = "R  Read a disk into a new image file, in this directory";
static const char S_O[] = "O  Copy disk (one drive: swap SOURCE and TARGET)";
static const char S_KEYS[] = "W Write,R Read,O Copy,ESC Back";
static const char S_PICK_KEYS[] = "1-8 Choose the disk,ESC Back";
static const char S_DEV[] = "%c  %s  %-17s %5u blocks%s";
static const char S_WHERE[] = "slot %u drive %u";
static const char S_NOVOL[] = "(no ProDOS volume)";
static const char S_INUSE[] = "  IN USE";
static const char S_EMPTY[] = "";
static const char S_HOLDS[] = "Disk in use: choose another.";
static const char S_LOST[] = " EVERYTHING on %s (%s) WILL BE LOST. ";
static const char S_ERASE[] = "Type ERASE then RETURN to go on";
static const char S_WORD[] = "ERASE";
static const char S_TO[] = "Write the image to which disk?";
static const char S_FROM[] = "Read which disk into an image?";
static const char S_CFROM[] = "Copy FROM which disk?";
static const char S_CTO[] = "Copy TO which drive? Same drive: swap disks.";
static const char S_NOTIMG[] = "The selection is not a disk image (.PO, .DSK, .2MG).";
static const char S_SMALL[] = "That disk is smaller than the image.";
static const char S_NODIR[] = "Open a ProDOS directory first: the image goes there.";
static const char S_NOSIZE[] = "Unknown size: neither a ProDOS volume nor a Disk II.";
static const char S_NAME[] = "Image name, without suffix";
static const char S_LONG[] = "Name too long for its suffix.";
static const char S_ORDER[] = "\1P ProDOS order (.PO) or D DOS 3.3 order (.DSK)?";
static const char S_DOT[] = "%s.%s";
static const char S_SLASH[] = "%s/%s";
static const char S_DSK[] = "DSK";
static const char S_PO[] = "PO";
static const char S_EXISTS[] = "A file of that name exists.";
static const char S_CREATE[] = "Cannot create the image file.";
static const char S_DONE[] = "%u blocks %s %s.%s";
static const char S_VERIFIED[] = " Verified.";
static const char S_WRITTEN[] = "written to";
static const char S_READ[] = "read from";
static const char S_COPIED[] = "copied to";
static const char S_INSERT[] = "Insert %s for %s in %s. Key/ESC.";
static const char S_SOURCE[] = "SOURCE";
static const char S_TARGET[] = "TARGET copy";
static const char S_READING[] = "Reading";
static const char S_WRITING[] = "Writing / verifying";
static const char S_CHECKFAIL[] = "Readback failed at block %u: %s.";
static const char S_DIFFER[] = "data mismatch";
static const char S_FAILED[] = "Failed: %s.";
static const char S_E_CANCEL[] = "cancelled";
static const char S_E_IO[] = "I/O error";
static const char S_E_NODEV[] = "no device there";
static const char S_E_WP[] = "the disk is write protected";
static const char S_E_SWITCH[] = "the disk was switched";
static const char S_E_CODE[] = "ProDOS error $%02X";
static const char S_RAM[] = "  /RAM was rebuilt empty.";

#define DI_BLOCK ((unsigned char*)0x3C00)   /* the block for MLI calls */
#define DI_MAIN ((unsigned char*)0x3600)    /* three staging blocks */
#define DI_MAIN_BLOCKS 3
#define DI_AUX 0x2000                       /* eighty more in AUX */
#define DI_AUX_BLOCKS 80
#define DI ((struct DiskImg*)0x3E00)

enum { SIDE_DEVICE, SIDE_PO, SIDE_DSK };
struct Side { unsigned char kind, unit; FILE* f; unsigned long base; };
struct Dev { unsigned char unit, inuse; unsigned int blocks; char name[NAME_LEN]; };
struct DiskImg {
    struct Side src, dst;
    struct Dev dev[8];
    unsigned char ndev, aux_used;
    unsigned int total;
    unsigned char parms[6];
    unsigned char checking;
    unsigned int checkblock;
    const char* source_name;
};

/* ProDOS block b of a track occupies two physical sectors (low half then
 * high half): these, in pairs, as in po2dsk.py. */
static const unsigned char DSK_SECTORS[16] = { 0x0, 0xE, 0xD, 0xC, 0xB, 0xA, 0x9, 0x8, 0x7, 0x6, 0x5, 0x4, 0x3, 0x2, 0x1, 0xF };

/* "slot s drive d" of the unit, in input. */
static const char* di_where(unsigned char unit)
{
    sprintf(input, S_WHERE, (unit >> 4) & 7, (unit >> 7) + 1);
    return input;
}

/* Reads (write = 0) or writes block `block` of side `s`, via DI_BLOCK.
 * Returns 0 or the ProDOS error; a short file counts as an I/O error. */
static unsigned char di_xfer(struct Side* s, unsigned int block, unsigned char write)
{
    unsigned char half, n = 1;
    unsigned int len = 512;
    unsigned char* p = DI->parms;
    unsigned long off;
    if (s->kind == SIDE_DEVICE) {
        p[0] = 3; p[1] = s->unit;
        p[2] = 0x00; p[3] = 0x3C;
        p[4] = (unsigned char)block; p[5] = (unsigned char)(block >> 8);
        return mli_call(write ? 0x81 : 0x80, p);
    }
    if (s->kind == SIDE_DSK) { n = 2; len = 256; }
    for (half = 0; half < n; ++half) {
        if (s->kind == SIDE_DSK) off = (((unsigned long)(block >> 3) << 4) + DSK_SECTORS[((block & 7) << 1) + half]) << 8;
        else off = (unsigned long)block << 9;
        if (fseek(s->f, s->base + off, SEEK_SET)) return 0x27;
        if ((write ? fwrite(DI_BLOCK + half * 256, 1, len, s->f) : fread(DI_BLOCK + half * 256, 1, len, s->f)) != len) return 0x27;
    }
    return 0;
}

/* Staging block i: DI_BLOCK goes there (put) or comes back from it. */
static void di_stage(unsigned char i, unsigned char put)
{
    if (i < DI_MAIN_BLOCKS) {
        if (put) memcpy(DI_MAIN + i * 512, DI_BLOCK, 512);
        else memcpy(DI_BLOCK, DI_MAIN + i * 512, 512);
    } else {
        DI->aux_used = 1;
        aux_copy((unsigned)DI_BLOCK, DI_AUX + ((unsigned)(i - DI_MAIN_BLOCKS) << 9), put);
    }
}

static unsigned char di_ask(const char* which)
{
    question_begin();
    cprintf(S_INSERT, which, DI->source_name, di_where(DI->src.unit));
    revers(0);
    return cgetc() != KEY_ESC;
}

/* A .DSK image writes its sectors at scattered positions in the file (the
 * DOS 3.3 order, see DSK_SECTORS): the first one jumps past the end of a
 * brand new file, and ProDOS refuses SET_MARK beyond the EOF. So the file
 * is given its full size first, in zeros and in order, before the
 * scattered writes -- they then all fall below the EOF. A .PO writes block
 * after block and would not need it, but pre-filling it only costs one
 * pass and keeps the code simple. */
static unsigned char di_presize(struct Side* s, unsigned int blocks)
{
    unsigned int b;
    memset(copy_buf, 0, 512);
    fseek(s->f, s->base, SEEK_SET);
    for (b = 0; b < blocks; ++b)
        if (fwrite(copy_buf, 1, 512, s->f) != 512) return 0x27;
    return 0;
}

/* Copies DI->total blocks from src to dst, one staging area per pass; with
 * `swap` (a single drive), asks for the floppy at each pass. Returns 0,
 * the ProDOS error, or $FF if the user gave up. */
static unsigned char di_copy(unsigned char swap)
{
    unsigned int done = 0, total = DI->total, left;
    unsigned char n, i, r, per = swap ? DI_MAIN_BLOCKS + DI_AUX_BLOCKS : DI_MAIN_BLOCKS;
    if (DI->dst.kind != SIDE_DEVICE && (r = di_presize(&DI->dst, total))) return r;
    progress_total = 1;
    progress_done = 0;
    while ((left = total - done) != 0) {
        n = left < per ? (unsigned char)left : per;
        if (swap && !di_ask(S_SOURCE)) return 0xFF;
        for (i = 0; i < n; ++i) {
            if ((r = di_xfer(&DI->src, done + i, 0))) return r;
            di_stage(i, 1);
            progress_bar(S_READING, done + i + 1, total);
        }
        if (swap && !di_ask(S_TARGET)) return 0xFF;
        for (i = 0; i < n; ++i) {
            di_stage(i, 0);
            if ((r = di_xfer(&DI->dst, done + i, 1))) return r;
            if (DI->dst.kind == SIDE_DEVICE) {
                DI->checking = 1;
                DI->checkblock = done + i;
                memcpy(copy_buf, DI_BLOCK, 512);
                if ((r = di_xfer(&DI->dst, DI->checkblock, 0))) return r;
                if (memcmp(copy_buf, DI_BLOCK, 512)) return 0xFE;
                DI->checking = 0;
            }
            progress_bar(S_WRITING, done + i + 1, total);
        }
        done += n;
    }
    return 0;
}

/* The block devices ProDOS knows (DEVLST), their volume if there is one
 * (ON_LINE), their size (the volume's, or 280 for a Disk II: its driver
 * is in the language card, below $FF00 where the /RAM one lives), and
 * whether the program is running on them. */
static void di_scan(void)
{
    unsigned char i, n = *(unsigned char*)0xBF31 + 1, len;
    unsigned char* online = copy_buf;
    unsigned char* p = DI->parms;
    unsigned int drv, dummy;
    struct Dev* d;
    DI->ndev = 0;
    for (i = 0; i < n && DI->ndev < 8; ++i) {
        d = &DI->dev[DI->ndev];
        d->unit = ((unsigned char*)0xBF32)[i] & 0xF0;
        drv = ((unsigned int*)0xBF10)[d->unit >> 4];
        d->blocks = drv >= 0xD000 && drv < 0xFF00 ? 280 : 0;
        d->name[0] = 0;
        d->inuse = 0;
        p[0] = 2; p[1] = d->unit;
        p[2] = (unsigned char)((unsigned)online & 0xFF); p[3] = (unsigned char)((unsigned)online >> 8);
        if (!mli_call(0xC5, p) && (len = online[0] & 0x0F) != 0) {
            d->name[0] = '/';
            memcpy(d->name + 1, online + 1, len);
            d->name[len + 1] = 0;
            /* the volume size stands for the disk's, except on a
             * Disk II: a floppy is 280 blocks, whatever volume was
             * written on it */
            if (!d->blocks) volume_blocks(d->name, &d->blocks, &dummy);
            d->inuse = (!strncmp(cfg_path, d->name, len + 1) && cfg_path[len + 1] == '/') ||
                (!strncmp(full, d->name, len + 1) && full[len + 1] == '/');
        }
        ++DI->ndev;
    }
}

static void di_title(const char* sub)
{
    clrscr();
    revers(1);
    gotoxy(0, 0);
    cprintf("%-79.79s", S_TITLE);
    revers(0);
    cputsxy(0, 2, sub);
}

/* The list of devices; returns the one the user picks by its number,
 * NULL on Escape. For writing (`writing`), the program's floppy is
 * refused. */
static struct Dev* di_pick(const char* what, unsigned char writing)
{
    struct Dev* d = DI->dev;
    unsigned char i;
    char key;
    di_title(what);
    for (i = 0; i < DI->ndev; ++i, ++d) {
        gotoxy(2, 4 + i);
        cprintf(S_DEV, '1' + i, di_where(d->unit), d->name[0] ? (const char*)d->name : S_NOVOL, d->blocks, d->inuse ? S_INUSE : S_EMPTY);
    }
    bar_begin();
    keys_bar(0, S_PICK_KEYS);
    for (;;) {
        key = cgetc();
        if (key == KEY_ESC) return NULL;
        if (key < '1' || key >= '1' + DI->ndev) continue;
        d = &DI->dev[key - '1'];
        if ((writing && d->inuse) || ((unsigned int*)0xBF10)[d->unit >> 4] == 0xFF00) {
            message(S_HOLDS); continue;
        }
        return d;
    }
}

/* The warning, then the word ERASE spelled out in full: nothing is
 * written before that. */
static unsigned char di_erase(const struct Dev* d)
{
    gotoxy(0, 20);
    revers(1);
    cprintf(S_LOST, di_where(d->unit), d->name[0] ? (const char*)d->name : S_NOVOL);
    revers(0);
    return prompt(S_ERASE, NULL, 0) && !strcmp(input, S_WORD);
}

/* Opens the image `full` (entry e): the sector order from its name (.DSK
 * or .DO: DOS 3.3; .2MG: its header says; otherwise ProDOS), the number
 * of blocks from its size. Returns 0 if it is not an image. */
static unsigned char di_open_image(struct Side* s, const struct Entry* e)
{
    unsigned char n = strlen(e->name);
    const char* end = e->name + n;
    unsigned long size = e->size;
    s->kind = SIDE_PO;
    s->base = 0;
    if ((n > 4 && !strcmp(end - 4, ".DSK")) || (n > 3 && !strcmp(end - 3, ".DO"))) s->kind = SIDE_DSK;
    s->f = fopen(full, "rb");
    if (!s->f) return 0;
    if (fseek(s->f, 0, SEEK_END) || ftell(s->f) != size || fseek(s->f, 0, SEEK_SET)) return 0;
    if (n > 4 && !strcmp(end - 4, ".2MG")) {
        if (fread(DI_BLOCK, 1, 64, s->f) != 64 || memcmp(DI_BLOCK, "2IMG", 4) || DI_BLOCK[0x0C] > 1 ||
            DI_BLOCK[0x0D] || DI_BLOCK[0x0E] || DI_BLOCK[0x0F]) return 0;
        s->kind = DI_BLOCK[0x0C] ? SIDE_PO : SIDE_DSK;
        s->base = *(uint32_t*)(DI_BLOCK + 0x18);
        size = *(uint32_t*)(DI_BLOCK + 0x1C);
        if (s->base < 64 || s->base > e->size || size > e->size - s->base) return 0;
    }
    if (((unsigned char*)&size)[3]) return 0; /* ProDOS EOF is 24 bits */
    DI->total = (unsigned int)(size >> 9);
    return DI->total != 0 && (size & 511) == 0 && (s->kind != SIDE_DSK || !(DI->total & 7));
}

static const char* di_error(unsigned char code)
{
    switch (code) {
    case 0xFF: return S_E_CANCEL;
    case 0x27: return S_E_IO;
    case 0x28: return S_E_NODEV;
    case 0x2B: return S_E_WP;
    case 0x2E: return S_E_SWITCH;
    }
    sprintf(input, S_E_CODE, code);
    return input;
}

void __fastcall__ diskimg_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e = &selected;
    struct Dev* from;
    struct Dev* to;
    struct Side* src = &DI->src;
    struct Side* dst = &DI->dst;
    const char* verb;
    unsigned char r = 0, image = pan->count && pan->path[0] && !is_dir(e);
    char key;
    (void)a;
    /* The block buffers live in the graphics page ($3600-$3DFF): a picture
     * viewed earlier may have left HIRES armed, with 80STORE then routing
     * $2000-$3FFF to the AUX bank -- READ_BLOCK would read the wrong place.
     * We switch HIRES off (text itself keeps 80STORE for its even columns)
     * and put reads/writes back on the main bank. aux_copy does its own
     * routing for the auxiliary scratch space. */
    *(unsigned char*)0xC056 = 0;       /* LORES: $2000-$3FFF out of the 80STORE routing */
    *(unsigned char*)0xC002 = 0;       /* RAMRD main bank */
    *(unsigned char*)0xC004 = 0;       /* RAMWRT main bank */
    DI->aux_used = 0;
    DI->checking = 0;
    src->f = dst->f = NULL;
    di_title(S_INTRO);
    if (image) { gotoxy(2, 4); cprintf(S_W, e->name); }
    cputsxy(2, 5, S_R);
    cputsxy(2, 6, S_O);
    bar_begin();
    keys_bar(0, S_KEYS);
    do key = cgetc() & 0xDF; while (key != 'W' && key != 'R' && key != 'O' && key != 0x1B);
    if (key == 0x1B) return;
    di_scan();
    if (key == 'W') {
        verb = S_WRITTEN;
        if (!image || !full[0] || !di_open_image(src, e)) { strcpy(note, S_NOTIMG); goto out; }
        if (!(to = di_pick(S_TO, 1))) goto out;
        if (to->blocks && to->blocks < DI->total) { strcpy(note, S_SMALL); goto out; }
        if (!di_erase(to)) goto out;
        dst->kind = SIDE_DEVICE;
        dst->unit = to->unit;
        r = di_copy(0);
    } else if (key == 'R') {
        verb = S_READ;
        if (!pan->path[0] || pan->fs) { strcpy(note, S_NODIR); goto out; }
        if (!(to = di_pick(S_FROM, 0))) goto out;
        DI->total = to->blocks;
        if (!DI->total) { strcpy(note, S_NOSIZE); goto out; }
        if (!strncmp(pan->path, to->name, strlen(to->name))) { strcpy(note, S_HOLDS); goto out; }
        if (!prompt(S_NAME, NULL, 0)) goto out;
        if (strlen(input) > 11 || strlen(pan->path) + 17 >= PATH_LEN) { strcpy(note, S_LONG); goto out; }
        message(S_ORDER);
        do key = cgetc() & 0xDF; while (key != 'P' && key != 'D' && key != 0x1B);
        if (key == 0x1B) goto out;
        sprintf(reselect, S_DOT, input, key == 'D' ? S_DSK : S_PO);
        sprintf(full, S_SLASH, pan->path, reselect);
        if (exists(full)) { strcpy(note, S_EXISTS); goto out; }
        _filetype = 0x06;
        _auxtype = 0;
        dst->kind = key == 'D' ? SIDE_DSK : SIDE_PO;
        dst->base = 0;
        dst->f = new_output(full);
        if (!dst->f) { strcpy(note, S_CREATE); goto out; }
        src->kind = SIDE_DEVICE;
        src->unit = to->unit;
        r = di_copy(0);
        if (r) { fclose(dst->f); dst->f = NULL; remove(full); }
    } else {
        verb = S_COPIED;
        if (!(from = di_pick(S_CFROM, 0))) goto out;
        DI->total = from->blocks;
        if (!DI->total) { strcpy(note, S_NOSIZE); goto out; }
        if (!(to = di_pick(S_CTO, 1))) goto out;
        if (to->blocks && to->blocks < DI->total) { strcpy(note, S_SMALL); goto out; }
        if (!di_erase(to)) goto out;
        src->kind = dst->kind = SIDE_DEVICE;
        src->unit = from->unit;
        dst->unit = to->unit;
        DI->source_name = from->name;
        r = di_copy(from == to);
    }
    if (!r) sprintf(note, S_DONE, DI->total, verb, di_where(to->unit), dst->kind == SIDE_DEVICE ? S_VERIFIED : S_EMPTY);
out:
    if (src->f) fclose(src->f);
    if (dst->f && fclose(dst->f) && !r) r = 0x27;
    if (r) {
        if (DI->checking) sprintf(note, S_CHECKFAIL, DI->checkblock, r == 0xFE ? S_DIFFER : di_error(r));
        else sprintf(note, S_FAILED, di_error(r));
        reselect[0] = 0;
    }
    if (DI->aux_used && ram_format()) strcat(note, S_RAM);
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* The overlay menu -- the big overlay MENU                               */
/* ---------------------------------------------------------------------- */

/* ! : the list of the A2FILE/ .PLG overlays, each with the description line
 * of its header, run on the current selection. One more command no longer
 * needs a key nor a rebuild: a third-party overlay whose signature is
 * PLUGIN_MAGIC shows up there like the others. Return drops the chosen
 * name into `input`, Escape leaves it empty; the core then runs the
 * overlay through overlay_run. The list lives in the graphics page,
 * outside this overlay's code. */
#pragma code-name (push, "MENU")
#pragma rodata-name (push, "MENURO")
static const char mn_catalog[] = "EXTRAS.CAT";
static const char mn_catalog_path[] = "/A2FILE/EXTRAS.CAT";
static const char mn_dir[] = "/A2FILE";
static const char mn_suffix[] = ".PLG";
static const char mn_self[] = "MENU.PLG";
static const char mn_bad[] = "(unreadable)";
static const char mn_stale[] = "(from another build of A2 File Cmd)";
static const char mn_noentry[] = "(no entry point)";
static const char mn_title[] = "  A2FILE/*.PLG  -  the overlays, run on the selected entry";
static const char mn_empty[] = "No overlay here.";
static const char mn_keys[] = "U/D Choose,L/R 6 rows,RET Open,ESC Back";
static const char mn_cat0[] = "Files";
static const char mn_cat1[] = "Images";
static const char mn_cat2[] = "Music";
static const char mn_cat3[] = "Disks";
static const char mn_cat4[] = "Programming";
static const char mn_cat5[] = "System";
static const char mn_cat6[] = "Archives";
static const char mn_cat7[] = "Other";
static const char* const mn_categories[] = {
    mn_cat0, mn_cat1, mn_cat2, mn_cat3, mn_cat4, mn_cat5, mn_cat6, mn_cat7
};
static const char mn_group0[] = "|TEXT|HEX|EDIT|SEARCH|FIND|FIXTYPES|GOTO|MDVIEW|RENAME|SYNC|MOVE|TREE|DELETE|ATTR|TXTCONV|TAGPAT|COMPARE|AWP|";
static const char mn_group1[] = "|IMAGE|DGRVIEW|EXTASIE|PACKFOT|PAINT816|LZ4FH|PRINTSHOP|FONTVIEW|";
static const char mn_group2[] = "|MUSIC|PT3|";
static const char mn_group3[] = "|FORMAT|DISKIMG|IMGFS|DOS33|BOOTBLK|BLKVIEW|BLKEDIT|DISKCMP|IMGCONV|MKIMAGE|RESCUE|UNDELETE|VOLNAME|VOLINFO|WIPE|VERIFY|";
static const char mn_group4[] = "|BASLIST|DISASM|INTBASIC|RUN|CRC|IDENT|";
static const char mn_group5[] = "|HELP|DATE|";
static const char mn_group6[] = "|BINARY2|UNSHRINK|";
static const char* const mn_groups[] = {
    mn_group0, mn_group1, mn_group2, mn_group3, mn_group4, mn_group5, mn_group6
};
#define MENU_CATEGORIES 8
static unsigned char menu_category(const char* name)
{
    unsigned char i, len = strlen(name);
    const char* p;
    for (i = 0; i < MENU_CATEGORIES - 1; ++i) {
        p = mn_groups[i];
        while (*p) {
            ++p;
            if (!strncmp(p, name, len) && p[len] == '|') return i;
            while (*p && *p != '|') ++p;
        }
    }
    return MENU_CATEGORIES - 1;
}

static const char mn_count[] = "%2u/%-2u";
static const char mn_titlefmt[] = "%-79.79s";
static const char mn_nodir[]   = "The program directory is unknown.";

/* The row uses the whole 80 columns: two of margin, twelve for the name
 * (a .PLG name is eleven characters at most), the rest for the description. */
static const char mn_row[]     = "  %-12s%-65.51s";
struct MenuItem { char name[12]; char desc[52]; };
#define MENU_ITEMS ((struct MenuItem*)0x3000)
#define MENU_MAX 64                 /* 64 x 64 bytes: $3000-$3FFF */
#define MENU_ROWS 18                /* rows 2..19 per page, like a panel */
#define MENU_STEP 6                 /* horizontal arrows: six entries */
void __fastcall__ menu_entry(const struct A2fcApi* a)
{
    struct MenuItem* m = MENU_ITEMS;
    const struct Overlay* hdr = (const struct Overlay*)copy_buf;
    unsigned char n = 0, i, j, cur = 0, len, pass, category = MENU_CATEGORIES;
    unsigned char count, chosen = 0;
    unsigned char* order = (unsigned char*)copy_buf;
    FILE* f;
    char key;
    (void)a;
    input[0] = 0;
    a2file_file("");
    if (!other_full[0]) { strcpy(note, mn_nodir); return; }
    other_full[strlen(other_full) - 1] = 0;   /* "/VOL/A2FILE/" -> "/VOL/A2FILE" */
    for (pass = 0; pass < 2; ++pass) {
        if (pass && !companion_path(mn_dir)) continue;
        if (!dir_open(other_full)) continue;
        while (n < MENU_MAX && dir_next()) {
            len = strlen(dir_entry.name);
            if (dir_entry.type != 0x06 || len < 5 || strcmp(dir_entry.name + len - 4, mn_suffix) || !strcmp(dir_entry.name, mn_self) || !strcmp(dir_entry.name, "COPY.PLG") || !strcmp(dir_entry.name, "OPEN.PLG") || !strcmp(dir_entry.name, "NAV.PLG") || !strcmp(dir_entry.name, "BATCH.PLG")) continue;
            dir_entry.name[len - 4] = 0;
            for (i = 0; i < n; ++i) if (!strcmp(m[i].name, dir_entry.name)) break;
            if (i < n) continue;
            strcpy(m[n].name, dir_entry.name);
            ++n;
        }
        dir_close();
    }
    for (i = 0; i < n; ++i) {          /* the header of each: its description */
        strcpy(m[i].desc, mn_bad);
        f = open_overlay(m[i].name, 0);
        if (!f) continue;
        len = fread(copy_buf, 1, 80, f);
        fclose(f);
        copy_buf[8 + 51] = 0;
        if (len < 9 || (hdr->signature != a2fc_link_id && hdr->signature != PLUGIN_MAGIC)) strcpy(m[i].desc, mn_stale);
        else if (!hdr->entry) strcpy(m[i].desc, mn_noentry);
        else strcpy(m[i].desc, hdr->desc);
    }
    /* The catalog keeps all commands visible during a one-drive swap.
     * Only selecting a command can ask for its disk, never listing it. */
    a2file_file(mn_catalog);
    f = fopen(other_full, "rb");
    if (!f && companion_path(mn_catalog_path)) f = fopen(other_full, "rb");
    if (f) {
        while (n < MENU_MAX && fread(copy_buf, 1, 78, f) == 78) {
            if (copy_buf[11]) continue; /* routing-only catalog record */
            copy_buf[77] = 0;
            for (i = 0; i < n; ++i) if (!strcmp(m[i].name, (char*)copy_buf)) break;
            if (i == n) { memcpy(&m[n], copy_buf, sizeof(struct MenuItem)); m[n].desc[51] = 0; ++n; }
        }
        fclose(f);
    }
    for (;;) {
        /* Rebuild a sorted index in copy_buf, no extra BSS or AUX memory. */
        count = 0;
        if (category == MENU_CATEGORIES) count = MENU_CATEGORIES;
        else for (i = 0; i < n; ++i) if (menu_category(m[i].name) == category) {
            j = count;
            while (j && strcmp(m[order[j - 1]].name, m[i].name) > 0) {
                order[j] = order[j - 1]; --j;
            }
            order[j] = i; ++count;
        }
        clrscr();
        revers(1);
        cprintf(mn_titlefmt, mn_title);
        revers(0);
        if (category != MENU_CATEGORIES) cputsxy(2, 1, mn_categories[category]);
        for (;;) {
            unsigned char top = cur - cur % MENU_ROWS;
            for (i = 0; i < MENU_ROWS; ++i) {
                gotoxy(0, 2 + i);
                revers(top + i == cur && count);
                if (top + i < count) {
                    if (category == MENU_CATEGORIES) cprintf(mn_titlefmt, mn_categories[top + i]);
                    else cprintf(mn_row, m[order[top + i]].name, m[order[top + i]].desc);
                } else cclearxy(0, 2 + i, 79);
                revers(0);
            }
            if (!count) cputsxy(2, 2, mn_empty);
            gotoxy(70, 0); revers(1);
            cprintf(mn_count, count ? cur + 1 : 0, count);
            revers(0);
            bar_begin();
            keys_bar(0, mn_keys);
            key = cgetc();
            if (key == KEY_ESC) {
                if (category == MENU_CATEGORIES) { input[0] = 0; return; }
                category = MENU_CATEGORIES; cur = chosen; break;
            }
            if (!count) continue;
            if (key == KEY_RETURN) {
                if (category != MENU_CATEGORIES) { strcpy(input, m[order[cur]].name); return; }
                category = chosen = cur; cur = 0; break;
            }
            if (key == KEY_UP && cur) --cur;
            else if (key == KEY_DOWN && cur + 1 < count) ++cur;
            else if (key == KEY_LEFT) cur = cur >= MENU_STEP ? cur - MENU_STEP : 0;
            else if (key == KEY_RIGHT) cur = cur + MENU_STEP < count ? cur + MENU_STEP : count - 1;
            else {
                if (key >= 'a' && key <= 'z') key -= 32;
                for (i = 1; i <= count; ++i) {
                    j = (cur + i) % count;
                    if ((category == MENU_CATEGORIES ? mn_categories[j][0] : m[order[j]].name[0]) == key) { cur = j; break; }
                }
            }
        }
    }
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* File operations                                                        */
/* ---------------------------------------------------------------------- */

static void refresh_both(void)
{
    read_panel(0);
    read_panel(1);
    draw_panel(0);
    draw_panel(1);
    draw_status();
    draw_info();
}

/* Reads a directory into pool[base..]: names, types, auxtypes. Returns 0
 * if the directory cannot be read or if the pool overflows. */
static unsigned char list_dir(const char* path, unsigned char base, unsigned char* count)
{
    unsigned char n = 0;
    if (!tree_stack_ok() || !dir_open(path)) return 0;
    while (dir_next()) {
        if (base + n >= POOL_SIZE) { dir_close(); return 0; }
        strcpy(pool[base + n].name, dir_entry.name);
        pool[base + n].type = dir_entry.type;
        pool[base + n].aux = dir_entry.aux;
        ++n;
    }
    dir_close();
    *count = n;
    return !dir_error;
}

/* Appends "/name" to a path; returns 0 beyond the 64 ProDOS characters. */
static unsigned char push_name(char* path, const char* name)
{
    unsigned char len = strlen(path);
    if (len + 1 + strlen(name) >= PATH_LEN) return 0;
    path[len] = '/';
    strcpy(path + len + 1, name);
    return 1;
}

/* GET_FILE_INFO: lighter than an fopen, and gfi[4] keeps the type. */
static unsigned char exists(const char* path)
{
    return file_info(path);
}

/* ESC during a copy, a move, a delete: the operation stops at the end of
 * the current file, the panels are re-read. Polls the keyboard without
 * waiting; any other key is swallowed. */
static unsigned char abort_key(void)
{
    if (!progress_abort && kbhit() && cgetc() == KEY_ESC) progress_abort = 1;
    return progress_abort;
}

/* The whole row 22: "  3/12  NAME            [####....] 12345/67890".
 * Forty bar cells. Redrawn only when a cell changes or the name changes:
 * a cprintf on every 512-byte block slowed the copy down more than the
 * disk did. */
static void progress_bar(const char* name, unsigned long copied, unsigned long size)
{
    unsigned char filled = size ? (unsigned char)(copied * 40 / size) : 40, i;
    if (copied && filled == bar_last && name == bar_name) return;
    bar_last = filled;
    bar_name = name;
    gotoxy(0, 22);
    cprintf("%3u/%-3u %-15.15s [", progress_done + 1, progress_total, name);
    for (i = 0; i < 40; ++i) cputc(i < filled ? '#' : '.');
    cprintf("] %6lu/%-5lu", copied, size);
}

/* Removes entry i from the panel's table without re-reading the disk: a
 * deleted or moved file disappears at once. */
static void drop_entry(struct Panel* pan, unsigned char i)
{
    memmove(&pan->e[i], &pan->e[i + 1], (pan->count - i - 1) * sizeof(struct Entry));
    if (--pan->count && pan->cursor >= pan->count) pan->cursor = pan->count - 1;
}

/* Copy state uses the idle text pagination buffer, not the recursive stack.
 * A small overlay leaves both panel tables and the directory pool intact. */
struct CopyState {
    char target[PATH_LEN], backup[PATH_LEN];
    const char* name;
    unsigned long size;
    unsigned char type, had_old, owned, ok;
    unsigned int aux;
};
#define CP ((struct CopyState*)text_starts)

#pragma code-name(push, "COPY")
#pragma rodata-name(push, "COPYRO")
static unsigned char may_overwrite(const char* name)
{
    char key;
    if (over_policy == OVERWRITE_ALL) return 1;
    if (over_policy == SKIP_ALL) return 0;
    question_begin();
    cprintf("%s exists: Overwrite, Skip, All, None? ", name);
    revers(0);
    for (;;) {
        key = cgetc() | 0x20;
        if (key == 'o') return 1;
        if (key == 's') return 0;
        if (key == 'a') { over_policy = OVERWRITE_ALL; return 1; }
        if (key == 'n' || key == (KEY_ESC | 0x20)) { over_policy = SKIP_ALL; return 0; }
    }
}

/* Back up the old entry before reserving the output. Never truncate or
 * clean up a name unless exclusive CREATE granted ownership. */
static unsigned char copy_stage(void)
{
    FILE *in, *out;
    unsigned int n;
    unsigned long copied = 0;
    CP->had_old = CP->owned = CP->ok = 0;
    if (exists(CP->target)) {
        if (gfi[4] == 15 || !may_overwrite(CP->name)) {
            ++progress_skipped; ++progress_done; return 2;
        }
        if ((gfi[3] & 0xC2) != 0xC2) return 0;
        strcpy(CP->backup, CP->target);
        *strrchr(CP->backup, '/') = 0;
        if (!push_name(CP->backup, "A2FC.BAK") || rename(CP->target, CP->backup)) return 0;
        CP->had_old = 1;
    } else if (_oserror != 0x46) return 0;
    in = fopen(full, "rb");
    if (!in) return 0;
    if (fseek(in, 0, SEEK_END) || (long)(CP->size = ftell(in)) < 0 || fseek(in, 0, SEEK_SET)) {
        fclose(in); return 0;
    }
    _filetype = CP->type; _auxtype = CP->aux;
    out = new_output(CP->target);
    if (!out) { fclose(in); return 0; }
    CP->owned = CP->ok = 1;
    while ((n = fread(copy_buf, 1, 512, in)) != 0) {
        if (fwrite(copy_buf, 1, n, out) != n || abort_key()) { CP->ok = 0; break; }
        copied += n;
        progress_bar(CP->name, copied, CP->size);
    }
    if (ferror(in) || copied != CP->size) CP->ok = 0;
    if (fclose(in)) CP->ok = 0;
    if (fclose(out)) CP->ok = 0;
    return 0;
}
#pragma rodata-name(pop)
#pragma code-name(pop)

#pragma code-name(push, "COPY")
#pragma rodata-name(push, "COPYRO")
/* Read back both complete streams before a move may delete its source.
 * Half of copy_buf belongs to each stream: no extra disk buffer or heap. */
static unsigned char copy_check(void)
{
    FILE *in, *out;
    unsigned int n;
    unsigned long checked = 0;
    if (CP->ok) {
        in = fopen(full, "rb"); out = fopen(CP->target, "rb");
        if (!in || !out) CP->ok = 0;
        while (CP->ok) {
            n = fread(copy_buf, 1, 256, in);
            if (fread(copy_buf + 256, 1, 256, out) != n ||
                memcmp(copy_buf, copy_buf + 256, n) || abort_key()) { CP->ok = 0; break; }
            checked += n;
            if (n < 256) break;
        }
        if (in) { if (ferror(in)) CP->ok = 0; if (fclose(in)) CP->ok = 0; }
        if (out) { if (ferror(out)) CP->ok = 0; if (fclose(out)) CP->ok = 0; }
        if (checked != CP->size) CP->ok = 0;
    }
    if (!CP->ok) {
        if (CP->owned) remove(CP->target);
        if (CP->had_old && rename(CP->backup, CP->target))
            message("Copy failed. Original retained as A2FC.BAK.");
        else if (!progress_abort) message("Copy failed; source retained.");
        return 0;
    }
    if (CP->had_old && remove(CP->backup)) {
        message("Copy verified; A2FC.BAK retained. Source kept."); return 0;
    }
    ++a2fc_ops; ++progress_done;
    return 1;
}
#pragma rodata-name(pop)
#pragma code-name(pop)

static unsigned char copy_file(const char* name, unsigned char type, unsigned int aux)
{
    unsigned char r = 0;
    strcpy(CP->target, other_full);
    CP->name = name; CP->type = type; CP->aux = aux;
    if (overlay("COPY")) {
        r = copy_stage();
        if (r != 2) r = copy_check();
    }
    strcpy(other_full, CP->target);
    return r;
}

/* The three tree walks that follow are recursive: their local variables
 * must live on the stack, not in statics as -Cl wants for the rest of the
 * program, otherwise the inner level overwrites the outer level's path
 * length and the parent directory is never found again. */
#pragma static-locals (push, off)

/* The number of files under `full` (directories excluded), for the
 * progress counter. 0xFFFF if the tree cannot be walked. */
static unsigned int count_tree(unsigned char base)
{
    unsigned char n, i, len = strlen(full);
    unsigned int files = 0, sub;
    if (!list_dir(full, base, &n)) return 0xFFFF;
    for (i = 0; i < n; ++i) {
        if (pool[base + i].type != 0x0F) { ++files; continue; }
        if (!push_name(full, pool[base + i].name)) return 0xFFFF;
        sub = count_tree(base + n);
        full[len] = 0;
        if (sub == 0xFFFF) return sub;
        files += sub;
    }
    return files;
}

/* Copies the contents of directory `full` into directory `other_full`,
 * which already exists, subdirectories included; a subdirectory already
 * present is filled in, not recreated. */
static unsigned char copy_tree(unsigned char base)
{
    unsigned char n, i, sl = strlen(full), dl = strlen(other_full), ok = 1;
    if (!list_dir(full, base, &n)) { dir_fail(); return 0; }
    for (i = 0; i < n && ok; ++i) {
        const struct Mini* m = &pool[base + i];
        if (abort_key()) { ok = 0; break; }
        if (!push_name(full, m->name) || !push_name(other_full, m->name)) { too_long(); ok = 0; }
        else if (m->type == 0x0F) {
            if (!exists(other_full) && mkdir(other_full)) { report_error("Mkdir"); ok = 0; }
            else ok = copy_tree(base + n);
        } else ok = copy_file(m->name, m->type, m->aux) != 0;
        full[sl] = 0;
        other_full[dl] = 0;
    }
    return ok;
}

/* Deletes everything the directory `full` contains, then the directory. */
/* The DELETE overlay, first half: delete_tree, which moving a directory
 * also loads, once the copy is done. */
#pragma code-name (push, "DELETE")
#pragma rodata-name (push, "DELETERO")
static unsigned char delete_tree(unsigned char base)
{
    unsigned char n, i, len = strlen(full), ok = 1;
    if (!base && count_tree(0) == 0xFFFF) { dir_fail(); return 0; }
    if (!list_dir(full, base, &n)) { dir_fail(); return 0; }
    progress_total += n;
    for (i = 0; i < n && ok; ++i) {
        progress_bar(pool[base + i].name, progress_done, progress_total);
        if (abort_key()) { ok = 0; break; }
        if (!push_name(full, pool[base + i].name)) { too_long(); ok = 0; break; }
        if (pool[base + i].type == 0x0F) ok = delete_tree(base + n);
        else if (remove(full)) { report_error("Delete"); ok = 0; }
        else { ++a2fc_ops; ++progress_done; }
        full[len] = 0;
    }
    if (ok && rmdir(full)) { report_error("Delete"); ok = 0; }
    if (ok) {
        ++a2fc_ops;
        ++progress_done;
    }
    return ok;
}
#pragma rodata-name (pop)
#pragma code-name (pop)

#pragma static-locals (pop)

/* Copies the entry into the other panel's directory: a file, or a whole
 * directory. Returns 1 if everything is copied. */
static unsigned char copy_one(const struct Entry* e)
{
    struct Panel* dst = &panels[!active];
    unsigned char len;
    if (!build_full(full, &panels[active], e) || !build_full(other_full, dst, e)) { too_long(); return 0; }
    if (!is_dir(e)) return copy_file(e->name, e->type, e->aux) != 0;
    len = strlen(full);
    if (!strncmp(dst->path, full, len) && (dst->path[len] == '/' || !dst->path[len])) {
        { extern const char msg_intoself[]; message(msg_intoself); };
        return 0;
    }
    if (!exists(other_full)) {
        if (mkdir(other_full)) { report_error("Mkdir"); return 0; }
        ++a2fc_ops;
    }
    return copy_tree(0);
}

/* The files targeted by C, V and D: the panel's tags, otherwise the
 * cursor. Returns their number and drops them into `picked`. */
static unsigned char pick_targets(void)
{
    struct Panel* pan = &panels[active];
    unsigned char i, n = 0;
    if (!pan->count || !pan->path[0]) return 0;
    for (i = 0; i < pan->count; ++i) if (tagged(pan, i)) picked[n++] = i;
    if (!n) picked[n++] = pan->cursor;
    return n;
}

static unsigned char target_check(void)
{
    struct Panel* dst = &panels[!active];
    if (!panels[active].path[0]) { message("Open a directory first."); return 0; }
    if (dst->fs) { { extern const char msg_otherro[]; message(msg_otherro); }; return 0; }
    if (!dst->path[0]) { message("Open a directory in the other panel."); return 0; }
    if (!strcmp(dst->path, panels[active].path)) { { extern const char msg_samedir[]; message(msg_samedir); }; return 0; }
    return 1;
}

#pragma code-name (push, "BATCH")
#pragma rodata-name (push, "BATCHRO")
#include "batch.h"
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* The IMGFS overlay: extracting files from an image (C)                   */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "IMGFS")
#pragma rodata-name (push, "IMGFSRO")
static const char im_target[]  = "Open a ProDOS folder in the other panel.";
static const char im_reopen[]  = "Cannot reopen the image.";
#pragma static-locals (push, off)

/* Writes the ProDOS file with key block `key`, size `size`, to `out`, read
 * from the open image (img_f). The storage type follows from the size:
 * seedling (<= 512: the key is the data block) or sapling (the key is an
 * index block of 256 pointers, low bytes [0..255] then high bytes
 * [256..511]); a null block pointer is a hole (zeros). Tree files
 * (> 128 KB) are rare on a floppy and refused. `idx` is a 512-byte buffer
 * outside the panel tables. Returns 0 on error, 2 if the file is too
 * large. */
static unsigned char img_read_file(unsigned int key, unsigned long size, FILE* out, unsigned char* idx)
{
    unsigned int need = (unsigned int)((size + 511) >> 9), i, n, blk;
    unsigned long left = size;
    if (size > 128UL * 1024) return 2;
    if (size > 512 && !img_read_block(key, idx)) return 0;
    for (i = 0; i < need; ++i) {
        blk = size <= 512 ? key : (idx[i] | ((unsigned int)idx[256 + i] << 8));
        n = left > 512 ? 512 : (unsigned int)left;
        if (blk) { if (!img_read_block(blk, copy_buf)) return 0; }
        else memset(copy_buf, 0, 512);
        if (fwrite(copy_buf, 1, n, out) != n) return 0;
        left -= n;
    }
    return 1;
}

/* C on an image opened as a directory: extracts the tagged files, else the
 * file under the cursor, to the ProDOS directory of the other panel
 * (subdirectories have to be entered and extracted one at a time). The
 * index buffer borrows the destination panel's table, unused during the
 * operation; both panels are re-read on return. */
static void extract_targets(void)
{
    struct Panel* pan = &panels[active];
    struct Panel* dst = &panels[!active];
    unsigned char* idx = (unsigned char*)dst->e;
    unsigned char n, i, done = 0, big = 0, r;
    FILE* out;
    if (dst->fs || !dst->path[0]) { message(im_target); return; }
    n = pick_targets();
    if (!n) return;
    progress_total = n;
    progress_done = 0;
    i = pan->path[pan->img_len];         /* reopen the image without losing the inner path */
    pan->path[pan->img_len] = 0;
    r = img_open(pan->path);
    pan->path[pan->img_len] = i;
    if (!r) { message(im_reopen); return; }
    for (i = 0; i < n; ++i) {
        const struct Entry* e = &pan->e[picked[i]];
        if (is_up(e) || is_dir(e)) { ++progress_done; continue; }
        if (strlen(dst->path) + 1 + strlen(e->name) >= PATH_LEN) { too_long(); break; }
        sprintf(other_full, "%s/%s", dst->path, e->name);
        _filetype = e->type;
        _auxtype = e->aux;
        out = new_output(other_full);
        if (!out) { report_error("Create"); break; }
        progress_bar(e->name, 0, e->size);
        r = img_read_file(e->mdate, e->size, out, idx);
        if (fclose(out)) r = 0;
        if (r != 1) { remove(other_full); if (r == 0) { report_error("Extract"); break; } ++big; }
        else { ++a2fc_ops; ++done; }
        ++progress_done;
        progress_bar(e->name, e->size, e->size);
    }
    fclose(img_f);
    refresh_both();                       /* the destination table was used as a buffer */
    clear_row(22);
    gotoxy(0, 22);
    cprintf("%u file%s extracted", done, done == 1 ? "" : "s");
    if (big) cprintf(", %u too big (>128K)", big);
    cputc('.');
}

void __fastcall__ imgfs_entry(const struct A2fcApi* a)
{
    (void)a;
    extract_targets();
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* The DOS33 overlay: DOS 3.3 catalog, extraction, and M                  */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "DOS33")
#pragma rodata-name (push, "DOS33RO")
static const char d3_target[]  = "Open a ProDOS folder in the other panel.";
static const char d3_reopen[]  = "Cannot reopen the image.";
static const char d3_done[]    = "%u file%s extracted.";
#pragma static-locals (push, off)

/* C on a DOS 3.3 image or disk: extracts the tagged files (else the one
 * under the cursor) to the ProDOS directory of the other panel. Each file's
 * T/S list is followed; the DOS-specific leading bytes are stripped (two for
 * an Applesoft/Integer program, four for a binary) so that the file is
 * usable, the rest of the sectors is written as is (the trailing padding of
 * a last sector is harmless). The T/S buffer borrows the destination
 * panel's table, unused during the operation. */
static void dos_extract(void)
{
    struct Panel* pan = &panels[active];
    struct Panel* dst = &panels[!active];
    unsigned char* tsbuf = (unsigned char*)dst->e;
    unsigned char n, i, done = 0, r;
    FILE* out;
    if (dst->fs || !dst->path[0]) { message(d3_target); return; }
    n = pick_targets();
    if (!n) return;
    dos_unit = 0;
    if (pan->img_len) {
        i = pan->path[pan->img_len];
        pan->path[pan->img_len] = 0;
        r = img_open(pan->path);
        pan->path[pan->img_len] = i;
        if (!r) { message(d3_reopen); return; }
    } else dos_unit = (unsigned char)pan->dir_key;
    for (i = 0; i < n; ++i) {
        const struct Entry* e = &pan->e[picked[i]];
        unsigned char tslt = (unsigned char)(e->mdate >> 8), tsls = (unsigned char)e->mdate;
        unsigned char t, j, skip = 0, first = 1;
        if (is_up(e)) continue;
        if (strlen(dst->path) + 1 + strlen(e->name) >= PATH_LEN) { too_long(); break; }
        sprintf(other_full, "%s/%s", dst->path, e->name);
        _filetype = e->type;
        _auxtype = e->type == 0xFC ? 0x0801 : 0;
        out = new_output(other_full);
        if (!out) { report_error("Create"); break; }
        r = 1;
        while (tslt && tslt < 35 && r) {
            unsigned char nt = copy_buf[1], ns = copy_buf[2];
            if (!dos_read_sector(tslt, tsls)) { r = 0; break; }
            nt = copy_buf[1]; ns = copy_buf[2];
            memcpy(tsbuf, copy_buf + 0x0C, 244);
            tslt = nt; tsls = ns;
            for (j = 0; j < 122; ++j) {
                t = tsbuf[j * 2];
                if (!t) { tslt = 0; break; }
                if (!dos_read_sector(t, tsbuf[j * 2 + 1])) { r = 0; break; }
                if (first) { first = 0; skip = (e->type == 0xFC || e->type == 0xFA) ? 2 : e->type == 0x06 ? 4 : 0; }
                if (fwrite(copy_buf + skip, 1, 256 - skip, out) != 256 - skip) { r = 0; break; }
                skip = 0;
            }
        }
        if (fclose(out)) r = 0;
        if (!r) { remove(other_full); report_error("Extract"); break; }
        ++a2fc_ops;
        ++done;
    }
    if (img_f) { fclose(img_f); img_f = 0; }
    refresh_both();
    clear_row(22);
    gotoxy(0, 22);
    cprintf(d3_done, done, done == 1 ? "" : "s");
}

void __fastcall__ dos33_entry(const struct A2fcApi* a)
{
    (void)a;
    dos_extract();
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* The UNSHRINK overlay: a ShrinkIt archive (.SHK, NuFX) extracted to the   */
/* directory of the other panel -- in A2FILE/UNSHRINK.PLG, a big overlay.    */
/* The LZW/RLE core is in assembly (src/unshrink.s), at the head of the      */
/* overlay ($1B00-$1FFF) and copied to AUX at the same address so it runs    */
/* under RAMRD/RAMWRT AUX, where the dictionary tables live; this C driver,  */
/* for its part, stays in MAIN ($2000-$2FFF). Launched from the ! menu on    */
/* the selected archive.                                                     */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "UNSHRINK")
#pragma rodata-name (push, "UNSHRINKRO")
#pragma static-locals (push, off)

/* Every string of this overlay is a NAMED array (const char[]), not a
 * "..." literal: cc65 gathers literals into RODATA -- the main window, full
 * to the last bit, where every extra byte brings the end of A2FILE.CODE
 * closer to $BF00, where the launcher keeps its C stack (31 bytes of
 * literal were enough to freeze the boot). A named array follows the
 * UNSHRINKRO segment, in the overlay's file. Likewise, the bulky state
 * lives in a structure at a fixed address, $3000, outside LOWBSS (full) and
 * the C stack (192 bytes); true locals go on the C stack
 * (static-locals off). */

/* The assembly core, src/unshrink.s. Its AUX addresses, repeated here. */
void __fastcall__ us_init(unsigned int fmt_esc);
unsigned int __fastcall__ us_chunk(unsigned int in_addr);
#define US_INBUF  0x6000            /* the input window, 8 KB, in AUX */
#define US_OUTBUF 0x8000            /* the decoded block, 4096 bytes, in AUX */
#define US_WINDOW 8192
#define US_NEED   4100              /* a whole compressed block, header included */

struct UsState {
    FILE* in;
    FILE* out;
    unsigned int records, threads, attrib, filetype, auxtype, storage;
    unsigned int win_len, win_pos, n_done, name_len;
    unsigned long teof, ceof, rem_in, rem_out, total, done;
    unsigned char fmt, klass, kind, sep, disk;
    char name[17];
    unsigned char th[8 * 16];       /* up to eight thread headers */
    unsigned char hdr[256];         /* the attributes of one record */
};
#define US ((struct UsState*)0x3000)
#define U16(p, o) ((unsigned int)(p)[o] | ((unsigned int)(p)[(o) + 1] << 8))
/* 32 bits without any support routine (long shift, multiplication): the
 * slightest cc65 helper the resident does not already have gets linked into
 * ITS window, full to the last bit -- memcmp and the 32-bit multiplication
 * cost 91 bytes too many on the first try. Hence the byte-wise union, the
 * hand-written compare, and blocks*512 done with shifts. */
static unsigned long us_u32(const unsigned char* p)
{
    union { unsigned long l; unsigned char b[4]; } u;
    u.b[0] = p[0]; u.b[1] = p[1]; u.b[2] = p[2]; u.b[3] = p[3];
    return u.l;
}
static unsigned char us_eq(const unsigned char* a, const unsigned char* b, unsigned char n)
{
    while (n--) if (*a++ != *b++) return 0;
    return 1;
}
#define U32(p, o) us_u32((p) + (o))

static const char us_notfile[]  = "Select a ShrinkIt archive (.SHK).";
static const char us_notarch[]  = "Not a ShrinkIt (NuFX) archive.";
static const char us_notdir[]   = "The other panel must show a ProDOS directory.";
static const char us_noram[]    = "Extract to a disk, not /RAM (it shares aux memory).";
static const char us_corrupt[]  = "Corrupt archive.";
static const char us_unsupp[]   = "Unsupported compression (only LZW/1, LZW/2, stored).";
static const char us_done[]     = "%u file(s) extracted.";
static const char us_path[]     = "%s/%s";
static const char us_po[]       = ".PO";
static const char us_create[]   = "Create";
static const char us_extract[]  = "Extract";
static const char us_rb[]       = "rb";
static const unsigned char us_magic_master[] = { 0x4E, 0xF5, 0x46, 0xE9, 0x6C, 0xE5 };
static const unsigned char us_magic_record[] = { 0x4E, 0xF5, 0x46, 0xD8 };

/* Keeps the AUX input window holding at least one whole block: brings the
 * remainder back to the head (through main memory, 512 bytes at a time),
 * then reads the rest of the thread. Returns 0 on a failed read. */
static unsigned char us_fill(void)
{
    unsigned int left = US->win_len - US->win_pos, off, n;
    if (left >= US_NEED || !US->rem_in) return 1;
    for (off = 0; off < left; off += 512) {
        aux_copy((unsigned int)copy_buf, US_INBUF + US->win_pos + off, 0);
        aux_copy((unsigned int)copy_buf, US_INBUF + off, 1);
    }
    US->win_len = left;
    US->win_pos = 0;
    while (US->win_len <= US_WINDOW - 512 && US->rem_in) {
        n = US->rem_in > 512 ? 512 : (unsigned int)US->rem_in;
        if (fread(copy_buf, 1, n, US->in) != n) return 0;
        if (n < 512) memset(copy_buf + n, 0, 512 - n);
        aux_copy((unsigned int)copy_buf, US_INBUF + US->win_len, 1);
        US->win_len += 512;
        US->rem_in -= n;
    }
    return 1;
}

/* The first n bytes of the decoded block (OUTBUF, AUX) into the file. */
static unsigned char us_write(unsigned int n)
{
    unsigned int off, k;
    for (off = 0; off < n; off += 512) {
        k = n - off > 512 ? 512 : n - off;
        aux_copy((unsigned int)copy_buf, US_OUTBUF + off, 0);
        if (fwrite(copy_buf, 1, k, US->out) != k) return 0;
    }
    return 1;
}

/* A ProDOS name from the archive name: the last component, upper case,
 * letters, digits and periods, a letter first, 15 characters. */
static void us_prodos_name(const char* src, unsigned int len)
{
    unsigned int i, start = 0, n = 0;
    char c;
    for (i = 0; i < len; ++i) if (src[i] == (char)US->sep) start = i + 1;
    for (i = start; i < len && n < 15; ++i) {
        c = src[i];
        if (c >= 'a' && c <= 'z') c -= 32;
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.')) c = '.';
        if (!n && !(c >= 'A' && c <= 'Z')) { US->name[n++] = 'X'; if (n == 15) break; }
        US->name[n++] = c;
    }
    if (!n) US->name[n++] = 'X';
    US->name[n] = 0;
    US->name_len = n;
}

/* A data thread (data fork or disk image) to the directory of the other
 * panel. Returns 0 on a failure already reported. */
static unsigned char us_extract_thread(void)
{
    unsigned int n, used, hdr;
    unsigned char r = 1;
    if (US->disk) {                        /* a disk image: NAME.PO, blocks of 512 */
        if (US->name_len > 12) US->name_len = 12;
        strcpy(US->name + US->name_len, us_po);
        /* blocks * 512, through a union of two 16-bit integers (no long shift,
         * whose support routines would get linked into the resident, full):
         * low word = blocks << 9, high word = blocks >> 7. */
        { union { unsigned long l; unsigned int w[2]; } ro;
          ro.w[0] = US->auxtype << 9; ro.w[1] = US->auxtype >> 7; US->rem_out = ro.l; }
        _filetype = 0x06;
        _auxtype = 0;
    } else {
        US->rem_out = US->teof;
        _filetype = (unsigned char)US->filetype;
        _auxtype = US->auxtype;
    }
    US->total = US->rem_out;
    US->done = 0;
    sprintf(other_full, us_path, panels[!active].path, US->name);
    US->out = new_output(other_full);
    if (!US->out) { strcpy(note, "Create failed; existing files kept."); return 0; }
    progress_bar(US->name, 0, US->total);
    US->rem_in = US->ceof;
    if (US->fmt == 0) {                    /* stored as is */
        while (US->rem_out && r) {
            n = US->rem_out > 512 ? 512 : (unsigned int)US->rem_out;
            if (fread(copy_buf, 1, n, US->in) != n || fwrite(copy_buf, 1, n, US->out) != n) r = 0;
            else { US->rem_out -= n; US->rem_in -= n; US->done += n; progress_bar(US->name, US->done, US->total); }
        }
    } else {                               /* LZW/1 or LZW/2: the stream header, then block by block */
        hdr = US->fmt == 2 ? 4 : 2;        /* LZW/1: crc(2) vol esc; LZW/2: vol esc */
        if (fread(copy_buf, 1, hdr, US->in) != hdr) r = 0;
        else {
            US->rem_in -= hdr;
            us_init(((unsigned int)copy_buf[hdr - 1] << 8) | US->fmt);
            US->win_len = US->win_pos = 0;
            while (US->rem_out && r) {
                if (!us_fill()) { r = 0; break; }
                used = us_chunk(US_INBUF + US->win_pos);
                US->win_pos += used;
                n = US->rem_out > 4096 ? 4096 : (unsigned int)US->rem_out;
                if (!us_write(n)) { r = 0; break; }
                US->rem_out -= n;
                US->done += n;
                progress_bar(US->name, US->done, US->total);
            }
        }
    }
    if (fclose(US->out)) r = 0;
    if (!r) { remove(other_full); strcpy(note, "Extract failed: read/write error."); return 0; }
    /* what remains of the thread (ShrinkIt's padding byte, a truncated thread) */
    if (US->rem_in) fseek(US->in, (long)US->rem_in, SEEK_CUR);
    ++US->n_done;
    return 1;
}

void __fastcall__ unshrink_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    unsigned int i, t, len;
    unsigned char* th;
    (void)a;
    if (!pan->count || !pan->path[0] || is_dir(&selected) || !full[0]) { strcpy(note, us_notfile); return; }
    if (!panels[!active].path[0] || panels[!active].fs) { strcpy(note, us_notdir); return; }
    /* The auxiliary bank carries the LZW dictionary AND the /RAM disk:
     * extracting to /RAM would destroy it (and ram_format rebuilds it empty
     * afterwards). We refuse; any other volume will do. */
    if (!strncmp(panels[!active].path, "/RAM", 4) || !strncmp(full, "/RAM", 4)) {
        strcpy(note, us_noram); return;
    }
    if (strlen(panels[!active].path) + 17 >= PATH_LEN) { too_long(); return; }
    /* After a picture, HIRES stays armed. With 80STORE, PAGE2 then dictates
     * the bank for $2000-$3FFF even under RAMRD/RAMWRT AUX: the LZW
     * dictionary would overwrite the C driver and the panel tables in MAIN.
     * LORES hands that area back to RAMRD/RAMWRT without touching 80-column text. */
    *(volatile unsigned char*)0xC056 = 0;
    /* The core, at the head of the overlay ($1B00-$1FFF), copied to AUX at
     * the same address: that copy is the one that will run under RAMRD AUX. */
    aux_copy(0x1B00, 0x1B00, 1);
    aux_copy(0x1D00, 0x1D00, 1);
    aux_copy(0x1F00, 0x1F00, 1);
    US->n_done = 0;
    US->in = fopen(full, us_rb);
    if (!US->in) { report_error(us_extract); goto out; }
    if (fread(US->hdr, 1, 48, US->in) != 48) goto corrupt;
    if (US->hdr[0] == 0x0A && US->hdr[1] == 0x47 && US->hdr[2] == 0x4C) {   /* Binary II: 128 bytes to skip */
        if (fread(US->hdr + 48, 1, 80, US->in) != 80 || fread(US->hdr, 1, 48, US->in) != 48) goto corrupt;
    }
    if (!us_eq(US->hdr, us_magic_master, 6)) { strcpy(note, us_notarch); fclose(US->in); goto out; }
    US->records = U16(US->hdr, 8);
    progress_total = US->records;
    for (i = 0; i < US->records; ++i) {
        progress_done = i;
        /* the record: magic, crc, attrib_count, then the rest of the attributes */
        if (fread(US->hdr, 1, 8, US->in) != 8 || !us_eq(US->hdr, us_magic_record, 4)) goto corrupt;
        US->attrib = U16(US->hdr, 6);
        if (US->attrib < 8 || US->attrib > 256) goto corrupt;
        if (fread(US->hdr + 8, 1, US->attrib - 8, US->in) != US->attrib - 8) goto corrupt;
        US->threads = U16(US->hdr, 0x0A);
        US->sep = US->hdr[0x10];
        US->filetype = U16(US->hdr, 0x16);
        US->auxtype = U16(US->hdr, 0x1A);
        US->storage = U16(US->hdr, 0x1E);
        len = U16(US->hdr, US->attrib - 2);            /* name in the header (old ShrinkIt) */
        US->name[0] = 0;
        US->name_len = 0;
        if (len) {
            if (len > 255 || fread(US->hdr, 1, len, US->in) != len) goto corrupt;
            us_prodos_name((char*)US->hdr, len);
        }
        if (US->threads > 8) goto corrupt;
        if (fread(US->th, 1, US->threads * 16, US->in) != US->threads * 16) goto corrupt;
        for (t = 0; t < US->threads; ++t) {
            th = US->th + t * 16;
            US->klass = th[0];
            US->fmt = th[2];
            US->kind = th[4];
            US->teof = U32(th, 8);
            US->ceof = U32(th, 12);
            if (US->klass == 3 && US->kind == 0) {              /* the file name */
                len = US->ceof > 512 ? 512 : (unsigned int)US->ceof;
                if (fread(copy_buf, 1, len, US->in) != len) goto corrupt;
                if (US->ceof > len) fseek(US->in, (long)(US->ceof - len), SEEK_CUR);
                us_prodos_name((char*)copy_buf, US->teof > len ? len : (unsigned int)US->teof);
            } else if (US->klass == 2 && (US->kind == 0 || US->kind == 1)) {   /* data or disk image */
                if (US->fmt != 0 && US->fmt != 2 && US->fmt != 3) {
                    strcpy(note, us_unsupp);
                    fseek(US->in, (long)US->ceof, SEEK_CUR);
                    continue;
                }
                US->disk = US->kind == 1;
                if (!US->name_len) us_prodos_name(us_create, 6);   /* no name: "CREATE" */
                if (!us_extract_thread()) { fclose(US->in); goto out; }
            } else {
                fseek(US->in, (long)US->ceof, SEEK_CUR);       /* resource fork, comment */
            }
        }
    }
    fclose(US->in);
    sprintf(note, us_done, US->n_done);
    goto out;
corrupt:
    fclose(US->in);
    strcpy(note, us_corrupt);
out:
    if (ram_format()) strcat(note, " /RAM rebuilt empty.");
    strcpy(reselect, selected.name);
}

#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

static void copy_or_move(unsigned char move)
{
    struct Panel* pan = &panels[active];
    unsigned char n, i, done = 0, removed = 0;
    unsigned int sub;
    if (pan->fs == FS_DOS33) { overlay_run("DOS33", 'C'); return; }   /* DOS 3.3 extraction */
    if (pan->fs) { overlay_run("IMGFS", 0); return; }   /* extraction from a ProDOS image */
    if (!target_check()) return;
    n = pick_targets();
    if (!n) return;
    pool = (struct Mini*)panels[!active].e;
    /* The "file x of y" counter needs to know y: a first pass counts the
     * files, directories included. */
    progress_total = 0;
    progress_done = 0;
    progress_skipped = 0;
    progress_abort = 0;
    over_policy = ASK;
    if (move) memset(pan->tags, 0, sizeof pan->tags);   /* the tags are in picked: the entries are about to move */
    for (i = 0; i < n; ++i) {
        const struct Entry* e = &pan->e[picked[i]];
        if (is_up(e)) continue;
        if (!is_dir(e)) { ++progress_total; continue; }
        if (!build_full(full, pan, e)) { too_long(); refresh_both(); return; }   /* the pool has overwritten the other panel */
        sub = count_tree(0);
        if (sub == 0xFFFF) { dir_fail(); refresh_both(); return; }
        progress_total += sub;
    }
    for (i = 0; i < n; ++i) {
        const struct Entry* e = &pan->e[picked[i] - removed];
        unsigned int skipped_before = progress_skipped;
        if (is_up(e)) { ++done; continue; }
        if (abort_key() || !copy_one(e)) break;
        /* Moving is copying then deleting: a skipped file (Skip) has not
         * been copied, it stays; a directory in which a file was skipped
         * stays as well, whole, rather than losing part of it. */
        if (move && progress_skipped == skipped_before) {
            build_full(full, pan, e);
            if (is_dir(e) ? !(overlay("DELETE") && delete_tree(0)) : remove(full) != 0) { if (!is_dir(e) && !progress_abort) report_error("Delete source"); break; }
            drop_entry(pan, picked[i] - removed);      /* gone: the source shows it right away */
            ++removed;
            draw_panel(active);
        }
        ++done;
        read_panel(!active);                           /* arrived: the target shows it right away */
        draw_panel(!active);
    }
    refresh_both();
    if (progress_abort) { sprintf(question, "Interrupted: %u of %u done.", done, n); message(question); }
    else if (done == n) {
        clear_row(22);
        gotoxy(0, 22);
        cprintf("%u file%s %s", progress_done - progress_skipped, progress_done - progress_skipped == 1 ? "" : "s", move ? "moved" : "copied");
        if (progress_skipped) cprintf(", %u skipped", progress_skipped);
        cputc('.');
    }
}

/* The DELETE overlay, second half: the D command. */
#pragma code-name (push, "DELETE")
#pragma rodata-name (push, "DELETERO")
#ifdef A2FC_6502
#pragma rodata-name(push, "RODATA")
#endif
static const char dl_nothing[] = "Nothing to delete here.";
#ifdef A2FC_6502
#pragma rodata-name(pop)
#endif
static const char dl_ask1[]    = "Delete %s%s?";
static const char dl_inside[]  = " and everything inside";
static const char dl_askn[]    = "Delete %u tagged files?";
static const char dl_done[]    = "%u item%s deleted.";
static const char dl_stop[]    = "Interrupted: %u of %u deleted.";
static void delete_targets(void)
{
    struct Panel* pan = &panels[active];
    unsigned char n, i, done = 0, removed = 0;
    const struct Entry* e;
    n = pick_targets();
    if (!n) { message(dl_nothing); return; }
    pool = (struct Mini*)panels[!active].e;
    e = &pan->e[picked[0]];
    if (n == 1 && is_up(e)) { message(dl_nothing); return; }
    if (n == 1) sprintf(question, dl_ask1, e->name, dl_inside + (is_dir(e) ? 0 : sizeof dl_inside - 1));   /* "": the end of the array */
    else sprintf(question, dl_askn, n);
    if (!confirm(question)) return;
    /* Start with the selected entries.  Directory walks add their children
     * to the denominator as they are discovered, so nested deletes show
     * useful progress without a slow preliminary scan. */
    progress_total = n;
    progress_abort = 0;
    memset(pan->tags, 0, sizeof pan->tags);            /* the tags are in picked: the entries are about to move */
    for (i = 0; i < n; ++i) {
        e = &pan->e[picked[i] - removed];
        if (is_up(e)) continue;
        progress_bar(e->name, progress_done, progress_total);
        if (abort_key()) break;
        if (!build_full(full, pan, e)) { too_long(); break; }
        if (is_dir(e)) { if (!delete_tree(0)) break; }
        else if (remove(full)) { report_error("Delete"); break; }
        else { ++a2fc_ops; ++progress_done; }
        ++done;
        drop_entry(pan, picked[i] - removed);          /* gone: the panel shows it right away */
        ++removed;
        draw_panel(active);
    }
    refresh_both();
    if (progress_abort) { sprintf(question, dl_stop, done, n); message(question); }
    else if (done == n) {
        clear_row(22);
        gotoxy(0, 22);
        cprintf(dl_done, done, done > 1 ? "s" : "");
    }
}

void __fastcall__ delete_entry(const struct A2fcApi* a)
{
    (void)a;
    delete_targets();
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* The ATTR overlay, in A2FILE/ATTR.PLG: R, K, A and L. */
#pragma code-name (push, "ATTR")
#pragma rodata-name (push, "ATTRRO")
static const char at_name[] = "New name";
static const char at_dir[] = "New directory";
static const char at_type[] = "File type";
static const char at_aux[] = "Aux type";

static const char at_rename[]  = "Select something to rename.";
static const char at_novol[]   = "Open a volume first.";
static const char at_pick[]    = "Select a file or directory.";
static const char at_dirtype[] = "A directory keeps its type.";
static void rename_selected(const struct Entry* e)
{
    if (is_up(e) || !panels[active].path[0]) { message(at_rename); return; }
    if (!prompt(at_name, e->name, 0)) return;
    if (!build_full(full, &panels[active], e)) { too_long(); return; }
    if (strlen(panels[active].path) + 1 + strlen(input) >= PATH_LEN) { too_long(); return; }
    sprintf(other_full, "%s/%s", panels[active].path, input);
    if (rename(full, other_full)) { report_error("Rename"); return; }
    ++a2fc_ops;
    read_panel(active);
    select_name(&panels[active], input);
    show_active();
}

static void make_directory(void)
{
    struct Panel* pan = &panels[active];
    if (!pan->path[0]) { message(at_novol); return; }
    if (!prompt(at_dir, NULL, 0)) return;
    if (strlen(pan->path) + 1 + strlen(input) >= PATH_LEN) { too_long(); return; }
    sprintf(full, "%s/%s", pan->path, input);
    if (mkdir(full)) { report_error("Mkdir"); return; }
    ++a2fc_ops;
    refresh_both();
    select_name(pan, input);
    show_active();
}

/* A: type and auxtype; L: lock. Both go through GET_FILE_INFO then
 * SET_FILE_INFO on the same block, and reread the panel. */
static void change_attributes(const struct Entry* e, unsigned char lock)
{
    unsigned char type;
    unsigned int aux;
    if (is_up(e) || !panels[active].path[0]) { message(at_pick); return; }
    if (!build_full(full, &panels[active], e)) { too_long(); return; }
    if (!lock) {
        if (is_dir(e)) { message(at_dirtype); return; }
        sprintf(input, "%02X", e->type);
        if (!prompt(at_type, input, 2)) return;
        type = (unsigned char)hex_value(input);
        sprintf(input, "%04X", e->aux);
        if (!prompt(at_aux, input, 4)) return;
        aux = hex_value(input);
    }
    if (!file_info(full)) { report_error("Get info"); return; }
    if (lock) gfi[3] = is_locked(e) ? 0xC3 : 0x01;   /* everything, or read-only */
    else { gfi[4] = type; gfi[5] = (unsigned char)(aux & 0xFF); gfi[6] = (unsigned char)(aux >> 8); }
    if (!set_info()) { report_error("Set info"); return; }
    ++a2fc_ops;
    strcpy(input, e->name);
    read_panel(active);
    select_name(&panels[active], input);
    show_active();
}

void __fastcall__ attr_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e = &pan->e[pan->cursor];
    (void)a;
    if (api.arg == 'K') make_directory();
    else if (!pan->count) return;
    else if (api.arg == 'R') rename_selected(e);
    else change_attributes(e, api.arg == 'L');
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* The RUN overlay, in A2FILE/RUN.PLG: X, F, and Return on a SYS or a
 * BAS. */
#pragma code-name (push, "RUN")
#pragma rodata-name (push, "RUNRO")
#include "config.h"

#include "launch.h"

void __fastcall__ run_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    (void)a;
    if (a->arg == 'S') { api.arg = save_config(); return; }
    if (pan->count) run_selected(a->selected);
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* Return on a .PO/.DSK/.DO/.2MG file of a real directory: open it read-only
 * as a directory (read_image_panel). The image's path becomes pan->path,
 * pan->fs its sector order, and the volume directory (block 2) is displayed.
 * Returns 1 if the entry was an image (handled), 0 otherwise. */
static unsigned char open_image(struct Panel* pan, const struct Entry* e)
{
    unsigned char ord = pan->fs ? FS_PRODOS : image_order(e->name);
    char* slash;
    if (!ord || e->size < 512 || ((e->size & 511) && (e->size & 511) != 64)) return 0;   /* 64: the 2IMG header */
    if (!build_full(full, pan, e)) { too_long(); return 1; }
    strcpy(input, e->name);
    strcpy(pan->path, full);
    pan->img_len = strlen(full);
    pan->fs = ord;
    pan->dir_key = 2;
    pan->cursor = pan->top = pan->first = 0;
    if (!read_panel(active)) {      /* not a ProDOS volume: back to the directory */
        strcpy(pan->path, full);
        slash = strrchr(pan->path, '/');
        if (slash) *slash = 0; else pan->path[0] = 0;
        pan->fs = FS_PRODOS;
        open_path(pan);
        select_name(pan, input);
        { extern const char msg_notimg[]; message(msg_notimg); };
    }
    show_active();
    return 1;
}

/* Classification must return before loading the chosen overlay: loading
 * it from inside OPEN would overwrite code still on the return stack. */
#pragma code-name(push, "OPEN")
#pragma rodata-name(push, "OPENRO")
static unsigned char looks_like_music(const struct Entry* e)
{
    unsigned char n = strlen(e->name);
    return !is_dir(e) && e->type == 0x06 && n > 3 && !strcmp(e->name + n - 3, ".MB");
}
static const char ov_raw[] = "IMAGE", ov_ext[] = "EXTASIE", ov_pack[] = "PACKFOT";
static const char ov_paint[] = "PAINT816", ov_dgr[] = "DGRVIEW", ov_hex[] = "HEX";
static const char ov_text[] = "TEXT", ov_awp[] = "AWP", ov_run[] = "RUN", ov_music[] = "MUSIC";
static const char ov_font[] = "FONTVIEW";
static const char ov_lz[] = "LZ4FH", ov_ps[] = "PRINTSHOP", ov_pt3[] = "PT3";
static const char* const image_viewers[] = {ov_hex, ov_raw, ov_ext, ov_pack, ov_paint, ov_dgr};
static const char open_dgr[] = "DGR";
static const char open_error[] = "Cannot identify file: read/close error.";
static const char* file_viewer(const struct Entry* e, unsigned char pictures)
{
    unsigned char kind = image_kind(e);
    FILE* f;
    unsigned char n, failed;
    /* Album scans can reject unrelated names without opening every file. */
    if (pictures >= 2) {
        n = strlen(e->name);
        if (pictures == 2 ? !looks_like_music(e) :
            !(n > 4 && !strcmp(e->name+n-4, ".PT3"))) return ov_hex;
        pictures = 0;
    }
    if (e->type == 7) return ov_font;
    if (e->type == 8 && e->aux == 0x8066) return ov_lz;
    if (e->type == 6 && (e->aux & 0xCFFF) == 0x4800 &&
        (e->size == 572 || e->size == 576)) return ov_ps;
    if (!pictures && e->type == 0xFA) return ov_run;
    n = strlen(e->name);
    if (!pictures && n>4 && !strcmp(e->name+n-4,".PT3")) return ov_pt3;
    /* Probe only in main-RAM copy_buf, never in a graphics/AUX bank.
     * Explicit packed metadata wins; the other formats can identify
     * themselves even without a filename suffix or a ProDOS image type.
     * A partial DGR signature still belongs to DGRVIEW's validation. */
    if (kind < 2) {
        f = fopen(full, "rb");
        if (!f) return 0;
        n = fread(copy_buf, 1, 8, f);
        failed = ferror(f) != 0;
        if (fclose(f)) failed = 1;
        if (failed) return 0;
        if (n >= 3 && !memcmp(copy_buf, open_dgr, 3)) kind = 5;
        else if (n == 8 && (!memcmp(copy_buf, "HGRR\1\0\0\x20", 8) ||
                           !memcmp(copy_buf, "DHRR\1\0\0\x40", 8))) kind = 1;
        /* I supplies the missing intent for an unmarked lo-res screen or
         * pixmap. Return must not mistake every small BIN for a sprite. */
        else if (!kind && pictures && (e->type == 0x06 || e->type == 0x08) &&
                 e->size && e->size <= 2048) kind = 5;
    }
    if (kind) return image_viewers[kind];
    if (pictures) return ov_raw; /* I may explicitly try an untyped raw file. */
    if (looks_like_music(e)) return ov_music;
    if (e->type == 0x04) return ov_text;
    if (e->type == 0x1A) return ov_awp;
    if (e->type == 0xFF || e->type == 0xFC) return ov_run;
    return ov_hex;
}
void __fastcall__ open_entry(const struct A2fcApi* a)
{
    const char* viewer;
    input[0] = 0;
    if (selected.name[0] && !is_dir(&selected) && full[0]) {
        viewer = file_viewer(&selected, a->arg);
        if (viewer) strcpy(input, viewer);
        else message(open_error);
    }
}
#pragma rodata-name(pop)
#pragma code-name(pop)
static void open_viewer(unsigned char pictures)
{
    input[0] = 0;
    overlay_run("OPEN", pictures);
    if (input[0]) overlay_run(input, 0);
}

static void open_selected(void)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e;
    if (!pan->count) return;
    e = &pan->e[pan->cursor];
    if (!pan->path[0] && is_dir(e) && !e->access) {   /* a real DOS 3.3 disk from the list */
        pan->fs = FS_DOS33;
        pan->img_len = 0;
        pan->dir_key = e->mdate;                       /* the ProDOS unit */
        strcpy(pan->path, "/DOS 3.3");
        pan->cursor = pan->top = pan->first = 0;
        read_panel(active);
        show_active();
        return;
    }
    if (is_dir(e)) { if (overlay("NAV")) enter_dir(pan, e); show_active(); return; }
    if (open_image(pan, e)) return;
    if (!build_full(full, pan, e)) { too_long(); return; }
    open_viewer(0);
}

/* ---------------------------------------------------------------------- */
/* Tags, sort, search                                                     */
/* ---------------------------------------------------------------------- */

static void toggle_tag(void)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e;
    if (!pan->count || !pan->path[0]) return;
    e = &pan->e[pan->cursor];
    if (!is_dir(e)) set_tag(pan, pan->cursor, !tagged(pan, pan->cursor));
    land(pan->cursor);                 /* the tag shows; the cursor stays where it is */
}

/* Ctrl-T tags every file of the panel (mode 1), Ctrl-N untags them all
 * (0), * inverts the tags (2); directories are never tagged. */
static void retag(unsigned char mode)
{
    struct Panel* pan = &panels[active];
    unsigned char i;
    if (!pan->path[0]) return;
    for (i = 0; i < pan->count; ++i)
        set_tag(pan, i, !is_dir(&pan->e[i]) && (mode == 2 ? !tagged(pan, i) : mode));
    show_active();
}

/* ' then a key: the next entry whose name starts with it. Hosted in TEXT,
 * alongside sort, to leave resident space for the companion-disk loader. */
#pragma code-name (push, "TEXT")
#pragma rodata-name (push, "TEXTRO")
static const char tx_jump[] = "\1Jump to name starting with: ";
static const char tx_noname[] = "No such name in this panel.";
static void find_letter(void)
{
    struct Panel* pan = &panels[active];
    unsigned char i, j;
    char key;
    message(tx_jump);
    key = cgetc();
    clear_row(22);
    if (key >= 'a' && key <= 'z') key -= 32;
    if (!pan->count) return;
    for (i = 1; i <= pan->count; ++i) {
        j = (pan->cursor + i) % pan->count;
        if (pan->e[j].name[pan->path[0] ? 0 : 1] == key) { land(j); return; }
    }
    message(tx_noname);
}

#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Main loop                                                              */
/* ---------------------------------------------------------------------- */

/* Moves the cursor; past the edges of a directory read by windows, loads
 * the next or previous window. */
static void move_cursor(int delta)
{
    struct Panel* pan = &panels[active];
    int target;
    if (!pan->count) return;
    target = (int)pan->cursor + delta;
    if (target >= pan->count && pan->more) {
        pan->first += WINDOW;
        pan->cursor = pan->top = 0;
        read_panel(active);
        show_active();
        return;
    }
    if (target < 0 && pan->first) {
        pan->first -= WINDOW;
        pan->cursor = pan->top = 0;
        read_panel(active);
        set_cursor(pan, pan->count - 1);
        show_active();
        return;
    }
    if (target < 0) target = 0;
    if (target >= pan->count) target = pan->count - 1;
    land((unsigned char)target);
}

static void swap_panels(void)
{
    active = !active;
    draw_panel(0);
    draw_panel(1);
    draw_status();
    draw_info();
}

/* The key of the command bar button under column x, according to
 * MAIN_KEYS and the layout of keys_bar: three columns of key, the label,
 * one space. A one-letter key is itself; TAB, RET and SPC are the keys
 * they name. 0 between two buttons. */
static char key_of(const char* s)
{
    return s[1] == ' ' ? *s : *s == 'T' ? KEY_TAB : *s == 'R' ? KEY_RETURN : ' ';
}

#ifndef A2FC_NOMOUSE
static char bar_key(unsigned char x)
{
    const char* s = MAIN_KEYS;
    unsigned char x0 = 0, w;
    char key;
    while (*s) {
        key = key_of(s);
        s = strchr(s, ' ') + 1;
        for (w = 3; *s && *s != ','; ++s) ++w;
        if (x < x0 + w) return key;
        x0 += w + 1;
        if (*s) ++s;
    }
    return 0;
}
#endif

/* 1..9 and 0: the ten buttons of the bar, in order -- the function keys
 * of Norton Commander and A2Command. */
static char bar_nth(unsigned char n)
{
    const char* s = MAIN_KEYS;
    while (n--) { s = strchr(s, ','); if (!s) return 0; ++s; }
    return key_of(s);
}

/* A click. On the command bar, the button's key. On an entry, selection
 * -- the panel becomes active if it was not -- or opening if it was
 * already selected: two clicks open. On a panel's header, the sort (the
 * column line) or the parent directory (the path). Returns the equivalent
 * key, 0 when everything has already been done. */
#ifndef A2FC_NOMOUSE
static char click(void)
{
    unsigned char x = mouse_x, y = mouse_y, i, swapped;
    struct Panel* pan;
    if (y == 23) return bar_key(x);
    if (y >= 20) return 0;
    swapped = (x >= 40) != active;
    if (swapped) swap_panels();
    pan = &panels[active];
    if (y < 2) return swapped ? 0 : y ? 's' : KEY_ESC;
    i = pan->top + y - 2;
    if (i >= pan->count) return 0;
    if (i == pan->cursor) return swapped ? 0 : KEY_RETURN;
    land(i);
    return 0;
}

/* Waits for a key, or a click when a mouse is present. The pointer follows
 * the mouse once it has moved once, and is erased before control returns,
 * so that no redraw paints over it. A click returns the key it stands
 * for, 0 if it did everything itself. */
#endif
static char wait_key(void)
{
#ifdef A2FC_NOMOUSE
    return cgetc();
#else
    unsigned char st;
    char key;
    if (!a2fc_mouse) return cgetc();
    if (pointer) mouse_show();
    for (;;) {
        if (kbhit()) { key = cgetc(); break; }
        st = mouse_read();
        if (st & 0x20) { pointer = 1; mouse_show(); }
        if ((st & 0xC0) == 0x80) { mouse_hide(); key = click(); break; }
    }
    mouse_hide();
    return key;
#endif
}

/* The service table: what a third party's overlay receives at its entry
 * point (a2fc_plugin.h). The program's own overlays do not need it, they
 * are linked with it. */
static struct A2fcApi api = {
    A2FC_API_VERSION, 0,
    panels, &active, full, other_full, input, copy_buf, &dir_entry,
    message, confirm, prompt, progress_bar, keys_bar, bar_begin, draw_all, read_panel, report_error, wait_key,
    build_full, dir_open, dir_next, dir_close, mli_call,
    fopen, fread, fwrite, fclose, fseek, remove, cprintf, sprintf, cputs, cputc, gotoxy, revers, cclearxy, clrscr, cgetc,
    memcpy, memset, strcpy, strcmp, strlen, &_filetype, &_auxtype, reselect, note, &selected, cfg_path,
    ram_format, media_key, media_wait, music_info };

int main(void)
{
    char key;
    struct Panel* pan;
    struct Entry* ent;
    videomode(VIDEOMODE_80COL);
#ifdef A2FC_TRACE
    *(unsigned char*)0x03A0 = 1;
#endif
    memset(_LOWBSS_RUN__, 0, (size_t)_LOWBSS_SIZE__);
#ifdef A2FC_TRACE
    *(unsigned char*)0x03A0 = 2;
#endif
    a2fc_slot = 0xFF;
    panels[0].e = ENTRIES;
    panels[1].e = ENTRIES + MAX_ENTRIES;
    /* The left panel opens on the boot volume, the right one on its DEMO
     * directory; without a prefix, or without DEMO, read_panel falls back
     * to the volume list, which is also a good starting point. */
    if (!getcwd(panels[0].path, PATH_LEN)) panels[0].path[0] = 0;
    strcpy(panels[1].path, panels[0].path);
    if (panels[1].path[0] && strlen(panels[1].path) + 5 < PATH_LEN)
        strcat(panels[1].path, "/DEMO");
    strcpy(cfg_path, panels[0].path);
    if (strlen(cfg_path) + 18 < PATH_LEN) strcat(cfg_path, "/A2FILE/A2FILE.CFG");
    else cfg_path[0] = 0;
    if (overlay("RUN")) load_config();
    overlay_loaded[0] = 0;
#ifdef A2FC_TRACE
    *(unsigned char*)0x03A0 = 3;
#endif
#ifndef A2FC_NOMOUSE
    a2fc_mouse = mouse_init();
#endif
    /* VDrive: a serial card and two more volumes in DEVLST, before reading
     * the panels (the volume list shows them). */
#ifndef A2FC_NOVDRIVE
    key = vsdrive_install();
#else
    key = 0;                    /* ARCH=6502: no VDrive, no room for it */
#endif
#ifdef A2FC_TRACE
    *(unsigned char*)0x03A0 = 4;
#endif
    read_panel(0);
    read_panel(1);
#ifdef A2FC_TRACE
    *(unsigned char*)0x03A0 = 5;
#endif
    draw_all();
#ifndef A2FC_NOVDRIVE
#ifdef A2FC_TRACE
    *(unsigned char*)0x03A0 = 6;
#endif
    if (key) { extern const char msg_vdrive[]; sprintf(question, msg_vdrive, key >> 4, key & 15); message(question); }
#endif
    for (;;) {
        pan = &panels[active];
        key = wait_key();
        if (key >= '0' && key <= '9') key = bar_nth(key == '0' ? 9 : key - '1');
        if (key != KEY_ESC && key != 'q' && key != 'Q') clear_row(22);
        /* An image opened as a directory is read-only: only navigation,
         * tagging, C/V (extract) and the formatter act; the commands that
         * would write or that need a real path are refused with a clear
         * message. */
        /* `| 0x20` and not `& 0xDF`: strchr answers the terminator for a
         * zero key, and click() returns zero for a click it has already
         * acted on -- which used to be refused as a write to a read-only
         * image. Lower case leaves 0 mapped to ' ', outside the list. */
        if (pan->fs && strchr("rkaldxewthim", key | 0x20)) {
            { extern const char msg_roimg[]; message(msg_roimg); };
            continue;
        }
        switch (key) {
        case KEY_UP: move_cursor(-1); break;
        case KEY_DOWN: move_cursor(1); break;
        /* The horizontal arrows page, they do not open: in a directory of
         * a hundred files, going up and down is what one does most often,
         * and the Apple IIe keyboard has no PgUp. RET opens, ESC goes up
         * to the parent -- the only two other ways of doing it stay
         * unchanged. */
        case '<': case '-': case KEY_LEFT: move_cursor(-ROWS); break;
        case '>': case '+': case KEY_RIGHT: move_cursor(ROWS); break;
        case '[': set_cursor(pan, 0); show_active(); break;
        case ']': if (pan->count) set_cursor(pan, pan->count - 1); show_active(); break;
        case ' ': toggle_tag(); break;
        case '*': retag(2); break;
        case 20: retag(1); break;                             /* Ctrl-T: tag everything */
        case 14: retag(0); break;                             /* Ctrl-N: nothing */
        case 18: refresh_both(); break;                       /* Ctrl-R: reread the panels */
        case '\'': if (overlay("TEXT")) find_letter(); break;
        case KEY_TAB: swap_panels(); break;
        case KEY_RETURN: open_selected(); break;
        case KEY_ESC:
            if (pan->path[0]) { if (overlay("NAV")) go_up(pan); show_active(); }
            break;
        case '/':
            pan->path[0] = 0;
            open_path(pan);
            show_active();
            break;
        case '=':
            /* Back to plain ProDOS: a panel left inside a disk image kept
             * fs and an img_len that indexed the OLD path, and read_panel
             * then split the new one past its terminator. A path that is
             * itself inside an image simply fails to open, and says so. */
            panels[!active].fs = FS_PRODOS;
            strcpy(panels[!active].path, pan->path);
            open_path(&panels[!active]);
            draw_panel(!active);
            break;
        case 'c': case 'C': copy_or_move(0); break;
        case 'v': case 'V': copy_or_move(1); break;
        case 'r': case 'R': case 'k': case 'K': case 'a': case 'A': case 'l': case 'L':
            overlay_run("ATTR", key & 0xDF);
            break;
        case 'm': case 'M': overlay_run("COMPARE", 'M'); break;
        case 'd': case 'D': if (overlay("DELETE")) delete_targets(); break;
        case 's': case 'S': overlay_run("TEXT", 'S'); break;
        /* The entry under the cursor ONCE: pan->e[pan->cursor] is an entry of
         * 29 bytes, so each mention costs a multiplication, and these two
         * cases used it three times apiece. The pointer paid for the reader
         * below, which would not have fitted under $BEE0 otherwise. */
        case 't': case 'T':
            if (!pan->count) break;
            ent = &pan->e[pan->cursor];
            if (is_dir(ent) || !build_full(full, pan, ent)) break;
            key = ent->type;
            if ((unsigned char)key == 0xFC) overlay_run("BASLIST", 0);   /* big overlay */
            else if ((unsigned char)key == 0x1A) overlay_run("AWP", 0);
            else if ((unsigned char)key == 0xFA) overlay_run("INTBASIC", 0);
            else if (overlay("TEXT")) view_text(full);
            break;
        case 'h': case 'H':
            if (!pan->count) break;
            ent = &pan->e[pan->cursor];
            if (is_dir(ent) || !build_full(full, pan, ent)) break;
            if (overlay("HEX")) view_hex(full, ent->size);
            break;
        case 'x': case 'X': overlay_run("RUN", 'X'); break;
        case 'f': case 'F': overlay_run("FORMAT", 'F'); break;
        case 'e': case 'E': overlay_run("EDIT", 'E'); break;
        case 'w': case 'W': overlay_run("DISKIMG", 'W'); break;
        case '!':
            overlay_run("MENU", 0);
            if (!strcmp(input, "MOVE") && tag_count(&panels[active])) move_marked();
            else if (input[0]) overlay_run(input, 0);
            break;
        case 'i': case 'I':
            if (pan->count && !is_dir(&pan->e[pan->cursor]) && pan->path[0]) {
                open_viewer(1);
            }
            break;
        case '?': if (overlay("HELP")) view_help(); break;
        case 'q': case 'Q':
            if (confirm("Quit to ProDOS?")) {
                api.arg = 0;
                overlay_run("RUN", 'S');
                if (!api.arg && !confirm("Configuration warning. Quit anyway?")) break;
                /* The ProDOS prefix follows the active panel: Bitsy Bye
                 * resumes in the directory we were in. */
                if (pan->path[0]) chdir(pan->path);
                switch_to_text();
                clrscr();
                return 0;   /* crt0: QUIT ProDOS, Bitsy Bye resumes. */
            }
            break;
        }
    }
}
