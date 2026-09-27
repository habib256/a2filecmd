/* newsroom.c -- The Newsroom (Springboard, 1984) photos PH.* and banners
 * BN.*: DOS 3.3 B files loaded at $4000, BIN $4000 once copied to ProDOS.
 * From Return (the name and the type) or the ! menu, on the selected entry.
 *
 * The format is in docs/NEWSROOM-FORMAT.md, and the reference this viewer
 * is tested against in tools/newsroom_ref.py: a frame, the clip history,
 * $FF, then a bitmap of seven dots a byte, bit 0 left, 1 = white -- an HGR
 * byte with its palette bit clear. The picture is centered on a black
 * hi-res page, the main bank only: read-only, no AUX, no disk writes.
 *
 * A BIG overlay whose code stops before $2000 (the Makefile links it with a
 * $0500 window): the picture owns $2000-$3FFF. All of it is newsroom.s,
 * entry point included -- in C it was 1,597 bytes on the 6502. This file
 * gives it the header and the offsets it reads the program through. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);   /* newsroom.s */

#ifndef NR_TEST
struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[36]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = { MEDIA_PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
    {0,0,0}, "The Newsroom photos and banners" };
#pragma rodata-name (pop)
#endif

/* The offsets newsroom.s reads, in the order of its NRO_ constants. */
#define OFS(field) offsetof(struct A2fcApi, field)
const unsigned char nr_ofs[] = {
    OFS(full), OFS(note), OFS(reselect), OFS(selected), OFS(fopen), OFS(fread),
    OFS(fclose), OFS(strcpy), OFS(media_wait),
    offsetof(struct Entry, type), offsetof(struct Entry, size)
};
