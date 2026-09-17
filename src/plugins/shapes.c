/* shapes.c -- Applesoft shape tables, drawn 24 at a time on the hi-res
 * screen. From the ! menu (or Return on a .SHAPE file), on the selected
 * file; Space/Down show the next page, B/Up the previous, Escape leaves.
 *
 * The format and the page layout -- 6 x 4 cells of 40 dots, each shape at
 * scale 1 in the middle of its cell, the status in the mixed-mode text
 * below -- are in tools/shapes_ref.py. A table is accepted when its count
 * is not zero and its offsets are all in the file; a shape that does not
 * end within the file is left blank.
 *
 * A BIG overlay whose code stops before $2000 (the Makefile links it with
 * a $0500 window): the picture owns $2000-$3FFF. All of it is shapes.s,
 * entry point included, as in macpaint.c; this file gives it the header
 * and the offsets of the services and fields it uses. Main memory only:
 * /RAM is left alone. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);   /* shapes.s */

struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[34]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = { PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
    {0,0,0}, "Applesoft shape tables, 24 a page" };
#pragma rodata-name (pop)

/* The offsets shapes.s reads, in the order of its SO_ constants. */
#define OFS(field) offsetof(struct A2fcApi, field)
const unsigned char sh_ofs[] = {
    OFS(full), OFS(copy_buf), OFS(note), OFS(reselect), OFS(selected),
    OFS(fopen), OFS(fread), OFS(fseek), OFS(fclose), OFS(strcpy),
    OFS(cgetc), OFS(memset), OFS(gotoxy), OFS(cputs), OFS(clrscr),
    OFS(keys_bar), SEEK_SET
};
