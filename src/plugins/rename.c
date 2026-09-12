/* rename.c -- rename the tagged files of the active panel (or the one under
 * the cursor when nothing is tagged) by pattern: a prefix, a suffix, a new
 * extension, the extension stripped, or a number appended in panel order.
 * A small service-table overlay.
 *
 * From the ! menu. The volume list and a foreign file system are refused.
 * The operation is one key on the message line; P, S and E then read their
 * text with the core's prompt (a ProDOS-name fragment). Each new name is
 * built in `nm`, and the rename is MLI RENAME $C2 on the two Pascal paths
 * "/VOL/DIR/OLD" and "/VOL/DIR/NEW" built in api->copy_buf -- the service
 * table has no rename() of its own.
 *
 * What the overlay does not check itself, ProDOS does, and its error counts
 * as one skipped file: a name already taken by another file answers $47, and a name past ProDOS's fifteen
 * characters answers $40. Two tests the window has no room for, and the
 * count at the end says as much either way. The entry under the cursor is
 * renamed whatever it is when nothing is tagged, directories included
 * (tags are never on a directory); ".." is not a name on the disk, so the
 * RENAME simply fails and counts as skipped.
 *
 * It must be small: a big overlay is loaded over the panels' entry tables
 * ($2000), and this command follows the tags, which index those very
 * entries. 1,280 bytes for code, strings and variables, so, as in
 * volname.c and bootblk.c:
 *
 *  - a call through the service table costs cc65 some 35 bytes each time
 *    (load the table, push the slot, jump through jmpvec), so the services
 *    called with arguments go through stubs: a fastcall function whose
 *    body puts the slot's offset in Y and jumps to one trampoline, which
 *    drops the argument the prologue pushed, fetches the pointer from the
 *    table and jumps there with A/X and the C stack as the service expects
 *    them. The stubs are compiled without the optimiser, which would drop
 *    the ldy as dead before a jmp, and the last parameter of each is
 *    declared 16 bits so that the prologue always pushes two bytes. The
 *    two services called without arguments (cgetc, draw_all) cost eleven
 *    bytes as they are, and are left alone;
 *  - every string is laid down by one plain-6502 loop, pcat, and every
 *    number by catnum: no sprintf (a variadic call site costs sixty-five
 *    bytes) and no division (`v / 10` alone drags a runtime routine of the
 *    cc65 library into the window). No 65C02 opcode: the same source
 *    builds the 6502 edition. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[20];   /* just long enough: the window is full */
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, 0, plugin_entry, 0, 0, 0,
    "Rename tagged files"
};
#pragma rodata-name (pop)

/* RENAME $C2 {2, old, new}: two Pascal strings (cc65 packs the struct). */
struct Rn { unsigned char n; unsigned char* old; unsigned char* new; };

static const char m_dir[]   = "Open a directory.";
static const char m_ask[]   = "\1P)refix S)uffix E)xt X)strip N)um ESC";
static const char m_lab[]   = "Text";
static const char m_slash[] = "/";
static const char m_dot[]   = ".";
static const char m_ren[]   = " renamed, ";
static const char m_skp[]   = " skipped";

/* Nothing here is read before being written at entry. */
static const struct A2fcApi* A;
static struct Panel* P;
static const unsigned char* tp;     /* P->tags, walked entry by entry */
static const struct Entry* E;       /* the entry being treated */
static struct Rn rn = { 2, 0, 0 };  /* DATA: the count is set once, with the file */
static unsigned char* PB;           /* what pcat and catnum are filling */
static unsigned char pl;            /* how much of it is written */
static unsigned char mask;          /* the tag bit nexttag is on */
static char nm[32];                 /* the new name (31 at most), then the closing line */

/* The stubs into the service table (see above). */
#pragma optimize (push, off)
static void tramp(void)
{
    asm("sta tmp1");
    asm("stx tmp2");
    asm("jsr incsp2");              /* the argument the stub's prologue pushed */
    asm("lda %v", A);
    asm("sta ptr1");
    asm("lda %v+1", A);
    asm("sta ptr1+1");
    asm("lda (ptr1),y");
    asm("sta jmpvec+1");
    asm("iny");
    asm("lda (ptr1),y");
    asm("sta jmpvec+2");
    asm("lda tmp1");
    asm("ldx tmp2");
    asm("jmp jmpvec");
}
#define STUB(field) { asm("ldy #%b", offsetof(struct A2fcApi, field)); asm("jmp %v", tramp); }
static void __fastcall__ msg(const char* s) STUB(message)
static unsigned char __fastcall__ prompt(const char* label, const char* initial, unsigned int hex) STUB(prompt)
static unsigned char __fastcall__ read_panel(unsigned int p) STUB(read_panel)
static unsigned char __fastcall__ mli(unsigned char cmd, void* block) STUB(mli)

/* PB, at pl, gets `s` and its terminator; pl follows. The destination is
 * advanced by pl once, so a single Y indexes both strings. One loop serves
 * the name being built and the two Pascal paths alike. */
static void __fastcall__ pcat(const char* s)
{
    asm("sta ptr1");
    asm("stx ptr1+1");
    asm("lda %v", PB);
    asm("clc");
    asm("adc %v", pl);
    asm("sta ptr2");
    asm("lda %v+1", PB);
    asm("adc #0");
    asm("sta ptr2+1");
    asm("ldy #0");
    asm("pc1: lda (ptr1),y");
    asm("sta (ptr2),y");
    asm("beq pc2");
    asm("iny");
    asm("bne pc1");
    asm("pc2: tya");
    asm("clc");
    asm("adc %v", pl);
    asm("sta %v", pl);
}

/* nm, at pl, gets the decimal of `v` (0-255): hundreds and tens by
 * subtraction, leading zeros dropped. Only ever called with PB = nm, so it
 * writes there directly and spares itself a pointer. */
static void __fastcall__ catnum(unsigned char v)
{
    asm("ldx #$FF");
    asm("sec");
    asm("cn1: inx");
    asm("sbc #100");
    asm("bcs cn1");
    asm("adc #100");
    asm("stx tmp1");                /* hundreds */
    asm("ldx #$FF");
    asm("sec");
    asm("cn2: inx");
    asm("sbc #10");
    asm("bcs cn2");
    asm("adc #10");
    asm("stx tmp2");                /* tens; A: units */
    asm("pha");
    asm("ldy %v", pl);
    asm("lda tmp1");
    asm("beq cn3");
    asm("ora #$30");
    asm("sta %v,y", nm);
    asm("iny");
    asm("cn3: lda tmp1");
    asm("ora tmp2");
    asm("beq cn4");
    asm("lda tmp2");
    asm("ora #$30");
    asm("sta %v,y", nm);
    asm("iny");
    asm("cn4: pla");
    asm("ora #$30");
    asm("sta %v,y", nm);
    asm("iny");
    asm("lda #0");
    asm("sta %v,y", nm);
    asm("sty %v", pl);
}

/* Nonzero when nothing can be renamed in the panel: the volume list, which
 * has no path, or a foreign file system, which is read-only. One pointer
 * setup for the two fields. */
static unsigned char badpanel(void)
{
    asm("lda %v", P);
    asm("sta ptr1");
    asm("lda %v+1", P);
    asm("sta ptr1+1");
    asm("ldy #%b", offsetof(struct Panel, fs));
    asm("lda (ptr1),y");
    asm("bne bp1");
    asm("ldy #0");
    asm("lda (ptr1),y");
    asm("beq bp1");
    asm("lda #0");
    asm("beq bp2");                 /* always */
    asm("bp1: lda #1");
    asm("bp2: ldx #0");
}

/* The tag bit of the entry the walk is on, and on to the next one. */
static unsigned char nexttag(void)
{
    asm("lda %v", tp);
    asm("sta ptr1");
    asm("lda %v+1", tp);
    asm("sta ptr1+1");
    asm("ldy #0");
    asm("lda (ptr1),y");
    asm("and %v", mask);
    asm("tay");
    asm("asl %v", mask);
    asm("bne nx1");
    asm("inc %v", mask);            /* past bit 7: bit 0 of the next byte */
    asm("inc %v", tp);
    asm("bne nx1");
    asm("inc %v+1", tp);
    asm("nx1: tya");
    asm("ldx #0");
}

/* Sets tp to the panel's tag bits and answers nonzero if any is set. */
static unsigned char anytag(void)
{
    asm("lda %v", P);
    asm("clc");
    asm("adc #%b", offsetof(struct Panel, tags));
    asm("sta %v", tp);
    asm("sta ptr1");
    asm("lda %v+1", P);
    asm("adc #0");
    asm("sta %v+1", tp);
    asm("sta ptr1+1");
    asm("ldy #%b", (MAX_ENTRIES + 7) / 8 - 1);
    asm("at1: lda (ptr1),y");
    asm("bne at3");
    asm("dey");
    asm("bpl at1");
    asm("at3: pha");
    asm("lda #1");                  /* the walk starts on bit 0 */
    asm("sta %v", mask);
    asm("pla");
    asm("at2: ldx #0");
}

/* Cuts nm at its last dot, the dot included; nothing if it has none. */
static void cut(void)
{
    asm("ldx %v", pl);
    asm("cu1: cpx #0");
    asm("beq cu2");
    asm("dex");
    asm("lda %v,x", nm);
    asm("cmp #$2E");
    asm("bne cu1");
    asm("stx %v", pl);
    asm("lda #0");
    asm("sta %v,x", nm);
    asm("cu2: lda #0");
}
#pragma optimize (pop)

#pragma static-locals (on)

/* PB gets "/VOL/DIR/name" as a Pascal string: the length byte, then the
 * characters. Both paths of the RENAME go through it. */
static void __fastcall__ mkpath(const char* name)
{
    pl = 1;
    pcat((const char*)P);           /* Panel.path is the head of the struct */
    pcat(m_slash);
    pcat(name);
    PB[0] = pl - 1;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char i, k, n, any, op, act, cur, count, renamed, skipped;

    A = api;
    act = *api->active;
    P = api->panels;
    if (act) ++P;
    if (badpanel()) { msg(m_dir); return; }
    /* The operation, one key on the message line, and the text the three
     * patterns that want one ask for right away: reading the key and the
     * text in the same loop spares a second run of comparisons. */
    msg(m_ask);
    for (;;) {
        op = api->cgetc();
        if (op == KEY_ESC) return;
        if (op >= 'a') op -= 32;
        if (op == 'X' || op == 'N') break;
        if (op == 'P' || op == 'S' || op == 'E') {
            if (!prompt(m_lab, 0, 0)) return;
            break;
        }
    }

    /* Tagged, or just the entry under the cursor. */
    any = anytag();                 /* which also sets tp and mask */
    cur = P->cursor;                /* a byte: comparing P->cursor itself would
                                     * cost a 16-bit compare and its routine */

    rn.old = api->copy_buf;         /* "/VOL/DIR/OLD" and "/VOL/DIR/NEW" */
    rn.new = rn.old + 128;

    count = 0; renamed = 0; skipped = 0;
    n = P->count;
    E = P->e;
    for (i = 0; i < n; ++i, ++E) {
        k = nexttag();                       /* this entry's tag */
        if (any) { if (!k) continue; }
        else if (i != cur) continue;

        /* The new name. */
        PB = (unsigned char*)nm;
        pl = 0;
        if (op == 'P') pcat(api->input);
        pcat(E->name);
        if (op == 'S') pcat(api->input);
        else if (op == 'N') catnum(++count);
        else if (op != 'P') {
            cut();                           /* E and X: the extension goes */
            if (op == 'E') { pcat(m_dot); pcat(api->input); }
        }
        /* A name over ProDOS's 15 characters, or one already on the disk,
         * makes the RENAME fail: both count as one skipped file. */
        PB = rn.old; mkpath(E->name);
        PB = rn.new; mkpath(nm);
        /* $47 if another file owns the name; an unchanged name succeeds. */
        if (mli(0xC2, &rn)) ++skipped; else ++renamed;
    }

    /* A small overlay redraws what it changed: the panel, then the count. */
    read_panel(act);
    api->draw_all();
    PB = (unsigned char*)nm;
    pl = 0;
    catnum(renamed); pcat(m_ren); catnum(skipped); pcat(m_skp);
    msg(nm);
}
