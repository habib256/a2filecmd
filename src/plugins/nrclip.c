/* nrclip.c -- the pages of a Springboard Newsroom clip-art disk, saved as
 * hi-res pictures. From the ! menu, with the clip-art disk in the active
 * panel (a DOS 3.3 file image or a real disk) and a ProDOS directory in
 * the other one.
 *
 * The disk layout is in docs/NEWSROOM-FORMAT.md, "Commercial clip-art
 * disks", and the reference this overlay is tested against in
 * tools/newsroom_ref.py (clip_index, clip_table, clip_piece, clip_page).
 * Each page is drawn on hi-res page 1, which the screen shows as it is
 * built (the progress display), then saved in the other panel's directory
 * as a BIN of auxiliary type $2000 holding exactly the 8,192 bytes of the
 * page, named from the page name the way A2 File Cmd names DOS 3.3 files.
 *
 * Data safety: the clip-art disk is only read; each file is created
 * exclusively (an existing name is skipped, never overwritten); a failed
 * write or close removes the file this run just created and stops; a
 * damaged page is skipped before its file exists. Main bank only: no
 * auxiliary memory, /RAM is untouched.
 *
 * A BIG overlay whose code stops before $2000 (the Makefile links it with
 * a $0500 window, XPLUGINS_HGR): the picture owns $2000-$3FFF. All of it
 * is nrclip.s, entry point included; this file gives it the header and
 * checks the offsets it reads the program through. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);   /* nrclip.s */

#ifndef NR_TEST
struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[43]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, {0,0,0},
    "Newsroom clip-art disk: pages to HGR files" };
#pragma rodata-name (pop)
#endif

/* nrclip.s writes these offsets as constants (API_*, PAN_*): the build
 * stops here if the table or the panel ever moved. */
#define NR_AT(t, f, n) ((int)offsetof(t, f) - (n)) * ((int)offsetof(t, f) - (n))
typedef char nr_offsets_checked[1 -
    (NR_AT(struct A2fcApi, panels, 2) +
     NR_AT(struct A2fcApi, active, 4) +
     NR_AT(struct A2fcApi, other_full, 8) +
     NR_AT(struct A2fcApi, copy_buf, 12) +
     NR_AT(struct A2fcApi, mli, 44) +
     NR_AT(struct A2fcApi, fopen, 46) +
     NR_AT(struct A2fcApi, fread, 48) +
     NR_AT(struct A2fcApi, fwrite, 50) +
     NR_AT(struct A2fcApi, fclose, 52) +
     NR_AT(struct A2fcApi, fseek, 54) +
     NR_AT(struct A2fcApi, remove, 56) +
     NR_AT(struct A2fcApi, sprintf, 60) +
     NR_AT(struct A2fcApi, strcpy, 80) +
     NR_AT(struct A2fcApi, note, 92) +
     NR_AT(struct Panel, fs, 94) +
     NR_AT(struct Panel, img_len, 95) +
     NR_AT(struct Panel, dir_key, 96) +
     ((int)sizeof(struct Panel) - 98) * ((int)sizeof(struct Panel) - 98) +
     (SEEK_SET - 2) * (SEEK_SET - 2) +
     (FS_DOS33 - 2) * (FS_DOS33 - 2))];
