/* repair.c -- repair a ProDOS volume, one verified block at a time.
 *
 * Increments 9 to 12 of docs/FIXIT.md section 8, the WRITE chantier. FIXIT
 * reads and names; REPAIR is the separate overlay recours 5 of section 4
 * promised: the Read window is full to seven bytes, so nothing of a FIXIT
 * pass survives to be repaired, and REPAIR redoes its own pass -- the same
 * walker, src/plugins/fixit_walk.h, compiled here with the plan and the
 * writes selected in.
 *
 * What this overlay does, in order: read the volume, build a plan, show it,
 * ask for the word FIX, re-read and revalidate the header, write, and walk
 * the volume again. Nothing is written before the word is typed, and every
 * block written is read back and compared; a block that cannot be verified
 * has its original rewritten and verified in turn.
 *
 * THE PLAN IS NOT A LIST. Nothing of what the first pass found is kept but
 * a counter per check, the number of bitmap pages each bitmap check touches
 * and the number of writes the directory corrections will cost. A corrected
 * bitmap page is recomputed, page by page, from a fresh walk: during the
 * apply pass the tree is walked once per 4 096-block window, exactly as the
 * check does, and the page is derived from seen[] and from the page on the
 * disk. A directory correction is written where the walk computes its
 * value, for the same reason. A list of blocks would be a copy of the
 * truth; the walk is the truth. The table plan[32] docs/FIXIT.md section 4
 * reserved was measured and dropped: it cost 632 bytes of code and 205 of
 * BSS in a window that was already 500 short, and it held nothing the
 * second walk does not recompute.
 *
 * ELEVEN corrections are applied: four in the bitmap and the seven of the
 * directory tree. Each one is a single verified write, so a block carrying
 * several is written once per correction -- grouping them would ask for a
 * patch list this window cannot hold (docs/FIXIT.md sections 4 and 5).
 *
 * Six of FIXIT's thirty checks are not carried here, because REPAIR repairs
 * none of them and the window is full: ENT_NAME, ENT_ACCESS, FILE_EOF,
 * HDR_NAME, VOLDIR_SIZE and DIR_HEADER (docs/FIXIT.md sections 4 and 5).
 *
 * A BIG overlay, window $1B00-$3F9D (__OVLSIZE__=0x249E, as FIXIT and
 * VOLINFO): code, rodata AND bss end before the copy of the service table
 * at $3F9E. It never calls read_panel or draw_all, and its last words go
 * through api->note.
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
    "Repair a ProDOS volume: plan, type FIX, every write read back"
};
#pragma rodata-name (pop)

/* The walker of FIXIT, with the plan and the writes compiled in. */
#define REPAIR 1
#include "fixit_walk.h"

static const char CRLF[] = "\r\n";
static void line(const char* t) { v_cputs(t); v_cputs(CRLF); }

/* Is this still the disk the plan was built on? Block 2 has just been read
 * again: its whole header entry -- name, type, size, bitmap, counts, dates --
 * must be the thirty-nine bytes the plan pass copied into hdr[]. A floppy
 * swapped while the question was on the screen does not receive block
 * numbers read from the other one (section 5). Comparing the entry whole
 * costs less than spelling three fields out and catches more. */
static unsigned char same_header(void)
{
    unsigned char i;

    for (i = 0; i < HDRLEN; ++i)
        if (blk[H_STORAGE + i] != hdr[i]) return 0;
    return 1;
}

/* The plan, with nothing written yet: one line per check with the number of
 * corrections it carries, then what the plan refuses and why. The summary
 * line already holds the total and the number of blocks the plan will
 * write, so the per-check page count the bitmap lines used to print went
 * with the seven directory repairs (docs/FIXIT.md section 4). The plan
 * always fits one screen -- eleven checks at most -- so an unknown key has
 * nothing to redraw. */
static void plan_screen(void)
{
    unsigned char k;
    unsigned int n;

    title();
    v_cprintf(M_PLANLN, corr, blocks);
    for (k = 0; k < REP_COUNT; ++k) {
        n = counts[REPCHK[k]];
        if (n && (k > 3 || (on & BIT[k])))
            v_cprintf(M_LINE, chkname(k), n);
    }
    /* What the plan refuses, and why, said on the screen that offers it. */
    if (counts[CHK_XLINK]) line(M_XLINK);
    else if (counts[CHK_BM_LOST] && !(on & 8)) line(M_PARTIAL);
    v_cputs(M_RKEYS);
}

/* Select, plan, confirm, write, walk again. */
static void repair_main(void)
{
    unsigned char k, state, ok;
    unsigned int n;

    /* The volume the program itself runs from is refused before a single
     * block is read: ProDOS 8 keeps a bitmap block of its own in memory and
     * writes it back at the next allocation, which would undo a raw
     * correction without a word (docs/FIXIT.md section 5). */
    if (isboot) { note(M_BOOTVOL); return; }

    mode = MD_PLAN;
    hurt = 0; on = 0;
    v_memset(zz, 0, sizeof zz);
    state = scan();
    if (state != 1) { note(state ? M_NOREAD : M_BADHDR); return; }
    if (cancelled || failed || !complete) {
        note(cancelled ? M_CANCEL : failed ? M_IOERR : M_NOPLAN);
        return;
    }

    /* The header entry as the plan saw it, for the guard below: block 2 is
     * read again because the walk left the last bitmap page in blk. */
    if (!readblock(2, blk)) { note(M_NOREAD); return; }
    v_memcpy(hdr, blk + H_STORAGE, HDRLEN);

    /* The three bitmap corrections that only mark a block used are always
     * allowed; giving a lost block back has its own condition. */
    on = 7;
    if (freeing_ok()) on |= 8;
    for (k = 0; k < REP_COUNT; ++k) {
        n = counts[REPCHK[k]];
        if (k > 3 || (on & BIT[k])) corr += n;
    }
    blocks = ((on & 8) ? pgany : pgused) + dblocks;
    if (!corr) {
        note(counts[CHK_XLINK] ? M_XLINK
             : counts[CHK_BM_LOST] ? M_PARTIAL : M_CLEAN);
        return;
    }

    plan_screen();
    for (;;) {
        k = v_cgetc();
        if (k == KEY_ESC || k == KEY_RETURN) { note(M_NOTHING); return; }
        if (k == 'f' || k == 'F') break;
    }
    if (!v_prompt(M_ASK, 0, 0) || v_strcmp(A->input, M_WORD)) {
        note(M_NOTHING); return;
    }
    if (!readblock(2, blk) || !same_header()) { note(M_CHANGED); return; }

    /* The apply pass walks the volume again, window by window. Each
     * directory correction is written where the walk computes its value,
     * and each bitmap page is derived from that walk before being written.
     * Writing a page changes nothing the walk depends on -- the walk reads
     * the directory tree, never the bitmap -- and writing a directory block
     * changes it the way the walk wants it, so walking then writing per
     * window is sound. The directory blocks of window 1 therefore go out
     * before any bitmap page: an interrupted counter fix leaves nothing
     * worse than before, where a page that FREES blocks before a directory
     * write is the order section 5 argues about. */
    mode = MD_APPLY;
    reset();
    title(); v_cputs(M_WRITING);
    audit();
    if (hurt > 1) return;               /* the note already names the block */

    /* The mandatory second pass: a repair is only what a fresh walk
     * confirms, and `repaired` is said only of a volume that comes back
     * with NOTHING left -- not even a finding REPAIR never offered to
     * repair. The other verdict counts what the walk still sees, so any
     * weaker test would call a volume repaired and count its remaining
     * findings in the same breath. */
    mode = MD_RESCAN;
    ok = scan() == 1 && complete && !hurt && !found;
    /* One variadic call site, two formats: a format that reads fewer
     * arguments leaves the rest of what was pushed alone. */
    v_sprintf(A->note, ok ? M_DONE : M_LEFT, applied, blocks, found);
}
