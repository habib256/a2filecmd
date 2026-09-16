/* fixit.c -- read-only consistency check of a ProDOS volume.
 *
 * Increments 1 to 8 of docs/FIXIT.md section 8: the skeleton (volume
 * selection, the refusals, the volume header of block 2, the findings
 * table), the walker ported from src/plugins/volinfo.c, and the whole
 * catalogue of checks -- the thirty identifiers of
 * tools/prodos_check.py, which this file names exactly as the oracle
 * does. Increments 4 to 7 closed the last eight: DIR_PARENT and
 * ENT_HEADER_PTR (the links back up), HDR_NAME (block 2 against ON_LINE,
 * the one check that needs a device), DIR_EOF and FILE_EOF, ENT_NAME and
 * ENT_ACCESS, and BM_TAIL. Increment 8 closed the screen: one line per
 * non-zero check, eighteen lines a page, R to scan again and the verdict
 * in api->note. E, the exported report, did not fit and waits for an
 * overlay of its own (docs/FIXIT.md section 4).
 *
 * FIXIT NEVER WRITES. The Read chantier reads blocks and nothing else:
 * no WRITE_BLOCK, no file created, not even on the volume it examines.
 * The program's own volume is remembered here (api->cfg_path, by name and
 * by unit) only so the WRITE chantier can refuse it later; reading it is
 * allowed.
 *
 * A BIG overlay, window $1B00-$3F9D (__OVLSIZE__=0x249E, as VOLINFO): the
 * copy of the service table sits at the fixed address $3F9E, so code,
 * rodata AND bss must end before it. Being big it must never call
 * api->read_panel or api->draw_all -- those refill the entry tables over
 * this code -- and its last words go through api->note.
 *
 * The findings table (docs/FIXIT.md section 4): one 16-bit counter per
 * check, the first sixteen occurrences as {id, block, slot} on four
 * bytes, and an overflow flag. Beyond sixteen the screen shows the
 * counter alone: a repair is decided per check, never per occurrence.
 *
 * Every byte of this file was fought for: the window is 9 374 bytes and
 * the eight checks of increments 4 to 7 did not fit in the 49 that were
 * left. What was measured, form by form, is in docs/FIXIT.md section 4.
 *
 * The walk is VOLINFO's, window by window of 4 096 blocks, the whole
 * directory tree once per window (docs/FIXIT.md section 4: a full bitmap
 * of referenced blocks does not fit). Where VOLINFO increments one
 * anonymous counter -- bad, counts, shared, usedfree, lost -- FIXIT names
 * the fault. Two rules of section 3 hold the report together:
 *
 *  - an incomplete pass (IO_ERROR, DIR_DEPTH, DIR_LOOP, a next pointer
 *    out of range, HDR_BITMAP, Escape) silences BM_LOST, because a block
 *    nobody claims may live in the part of the tree we never reached --
 *    in EVERY window, so a cut found in window 3 takes back what windows 1
 *    and 2 already recorded (scan());
 *    BM_USED_FREE stays, a claim we did make is a fact;
 *  - a partial entry (ENT_KEY, ENT_STORAGE, IDX_RANGE, FORK_STORAGE)
 *    abandons that entry alone: FILE_BLOCKS is not emitted for it, the
 *    pass stays complete and BM_LOST still names its orphaned blocks.
 *
 * Findings that describe the directory tree are recorded on the FIRST
 * window only (dfinding), so the sixteen passes of a 32 MB volume do not
 * report the same fault sixteen times; bitmap findings are per window.
 */
#include "../a2fc_plugin.h"
#include <stddef.h>

void __fastcall__ plugin_entry(const struct A2fcApi* api);
struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char reserved[3]; char desc[63];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, {0,0,0},
    "Check a ProDOS volume: allocation, links, counters (read only)"
};
#pragma rodata-name (pop)

#include "fixit_walk.h"
