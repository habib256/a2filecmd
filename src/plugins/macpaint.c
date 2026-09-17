/* macpaint.c -- MacPaint documents, 576 x 720 dots in black and white.
 * From Return (a .MAC name) or the ! menu, on the selected entry.
 *
 * The format, and the reference this viewer is tested against, are in
 * tools/macpaint_ref.py: a 512-byte header, then 720 lines of 72 bytes, each
 * packed with PackBits; a 128-byte MacBinary header may come first.
 *
 * The screen shows 560 dots of the 576 -- eight are cut at each edge -- and
 * 192 lines of the 720, in double hi-res black and white. Up and Down move
 * the view by half a screen; Escape, Left and Right are the media keys.
 *
 * The whole file is unpacked once without storing anything: the auxiliary
 * plane is the bank where /RAM lives, so a file that is no whole MacPaint
 * picture costs nothing. That pass also notes where every 48th line starts,
 * so that a view is drawn from a seek, not from the start of the file.
 *
 * A BIG overlay whose code stops before $2000 (the Makefile links it with a
 * $0500 window): the picture owns $2000-$3FFF. All of it is macpaint.s,
 * entry point included: in C, the calls through the service table and the
 * 32-bit seek pulled in more runtime than the 1,280 bytes hold. This file
 * gives it the header and the offsets of the services it calls. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);   /* macpaint.s */

struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[52]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = { MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUX, plugin_entry,
    {0,0,0}, "MacPaint pictures (576 x 720, scrolled)" };
#pragma rodata-name (pop)

/* The offsets of the services macpaint.s calls, in the order of its OF_
 * constants, then SEEK_SET. */
#define OFS(field) offsetof(struct A2fcApi, field)
const unsigned char mp_ofs[] = {
    OFS(full), OFS(copy_buf), OFS(note), OFS(reselect), OFS(selected),
    OFS(fopen), OFS(fread), OFS(fseek), OFS(fclose), OFS(strcpy),
    OFS(cgetc), OFS(media_key), OFS(ram_format), SEEK_SET
};
