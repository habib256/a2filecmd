/* gmagic.c -- Graphics Magician pictures (Penguin Software, 1982-1984):
 * the picture lists of PICEDIT -- lines, flood fills with 108 patterns,
 * brush stamps, text -- drawn on hi-res page 1 as the original routines
 * draw them. From Return on a BIN file that starts like one (OPEN's probe,
 * src/open.s); the overlay checks every picture before drawing.
 *
 * Clean-room: docs/GRAPHICS-MAGICIAN-FORMAT.md is the only source, and
 * tools/gmagic_ref.py, written from it, is the reference this overlay is
 * tested against (tools/test_gmagic.py: Appendix B's 152 pages, both
 * processors). The patterns and brushes are the spec's Appendix A
 * (interoperability data); text uses A2FC's BOLD.SET, not Penguin's font.
 *
 * Read-only, main bank only: no AUX, no disk write. A BIG overlay whose
 * code also runs from $0C00 and, for its checks, from $2000 (sdk/gmagic.cfg).
 * All of it is gmagic.s; this file gives it the header and checks the
 * offsets it reads the program through. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);   /* gmagic.s */

#ifndef GM_TEST
struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[29]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = { MEDIA_PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
    {0,0,0}, "Graphics Magician pictures" };
#pragma rodata-name (pop)
#endif

/* gmagic.s writes these offsets as constants (API_*, E_TYPE): the build
 * stops here if the table or the entry ever moved. */
#define GM_AT(t, f, n) ((int)offsetof(t, f) - (n)) * ((int)offsetof(t, f) - (n))
typedef char gm_offsets_checked[1 -
    (GM_AT(struct A2fcApi, full, 6) +
     GM_AT(struct A2fcApi, copy_buf, 12) +
     GM_AT(struct A2fcApi, fopen, 46) +
     GM_AT(struct A2fcApi, fread, 48) +
     GM_AT(struct A2fcApi, fclose, 52) +
     GM_AT(struct A2fcApi, fseek, 54) +
     GM_AT(struct A2fcApi, cgetc, 74) +
     GM_AT(struct A2fcApi, strcpy, 80) +
     GM_AT(struct A2fcApi, reselect, 90) +
     GM_AT(struct A2fcApi, note, 92) +
     GM_AT(struct A2fcApi, selected, 94) +
     GM_AT(struct A2fcApi, media_key, 100) +
     GM_AT(struct Entry, type, 17) +
     (SEEK_SET - 2) * (SEEK_SET - 2))];
