/* fontview.c -- fonts on the hi-res screen, 16 glyphs a row. From Return
 * on a FNT ($07) file, or the ! menu. Main-bank HGR only: no AUX or disk
 * writes.
 *
 * Two formats (tools/test_fontview.py has the oracle of each page):
 *
 *   MGTK fonts (Apple II DeskTop; a2stuff/a2d bin/dump_font.pl): a flag,
 *   the last character, the height, the widths, then one plane per row
 *   and column, a byte per glyph. One or two HGR bytes a glyph.
 *   Hi-res fonts (DOS Toolkit, HRCG; CiderPress II's notes): 96 or 128
 *   glyphs of 7 x 8 dots, 8 bytes each, the top row first, the leftmost
 *   dot in bit 0, a set high bit shifting the row half a dot. These are
 *   files of exactly 768 or 1,024 bytes, typed FNT or BIN; a FNT file of
 *   768 bytes that is a well-formed MGTK font of that size stays MGTK.
 *
 * All of it is fontview.s, entry point included, as in macpaint.c: in C
 * the two formats did not fit the 1,280 bytes below the picture page. This
 * file gives it the header and the offsets it reads. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);   /* fontview.s */

struct Header { unsigned int signature; unsigned char flags;
 void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3]; char desc[22]; };
#pragma rodata-name(push, "OVLHDR")
const struct Header __plugin_header = { MEDIA_PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
 {0,0,0}, "MGTK and hi-res fonts" };
#pragma rodata-name(pop)

/* The offsets fontview.s reads, in the order of its FO_ constants. */
#define OFS(field) offsetof(struct A2fcApi, field)
const unsigned char fv_ofs[] = {
 OFS(full), OFS(copy_buf), OFS(note), OFS(reselect), OFS(selected),
 OFS(fopen), OFS(fread), OFS(fclose), OFS(strcpy), OFS(media_wait),
 offsetof(struct Entry, type), offsetof(struct Entry, size)
};
