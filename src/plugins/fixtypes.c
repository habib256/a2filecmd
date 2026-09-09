/* fixtypes.c -- set the ProDOS type and auxtype of the tagged files (or the
 * one under the cursor) from the .SUFFIX of their name, then, if asked,
 * drop that suffix from the name. A small service-table overlay.
 *
 * From the ! menu, on a ProDOS directory (the volume list, an image or a
 * DOS 3.3 disk are refused). Small, so the entry tables at $2000 stay
 * where they are: the targets are simply the tagged entries of
 * api->panels[*api->active], or the one under the cursor when nothing is
 * tagged. Each one whose suffix is in the table gets GET_FILE_INFO ($C4)
 * then SET_FILE_INFO ($C3) with the table's type and auxtype;
 * directories, unknown suffixes and ProDOS refusals are counted as
 * skipped. Then "Drop suffix?": if yes, a second pass over the
 * same entries RENAMEs ($C2) each one to its name without the suffix,
 * unless the suffix must stay (ProDOS boots .SYSTEM files by that name,
 * A2FC opens disk images .PO .DSK .DO .2MG .HDV by theirs) or nothing
 * would be left of the name. A name already taken needs no test of ours:
 * ProDOS answers $47 and the file keeps the name it had.
 *
 * Written for size (1,280 bytes), like volname.c, and every trick was
 * needed:
 *
 *  - the services are reached through one plain-6502 trampoline; the
 *    stubs before it put the slot in a byte of their own rather than in
 *    Y, which lets them keep the optimiser (with it, the ldy of
 *    volname.c dies before the jmp; without it, each stub drags a dead
 *    epilogue). The four services called with one argument share a
 *    single stub, the caller setting the slot;
 *  - the walk of the entries, the suffix match, the length byte of the
 *    path and the cut of the name are inline 6502, the last two in one
 *    block so that the pointer set up for the first serves the second;
 *  - the two Pascal paths live in api->copy_buf, the last line is built
 *    in api->note -- the only buffer that survives the redraw -- and the
 *    BSS holds nothing but a few bytes of state;
 *  - the rules are read backwards: each record is its suffix reversed and
 *    ending with the dot (the terminator, so no length byte), then the
 *    type, the auxtype high byte and its low byte. Matching from the end
 *    of the name that way, .SYS and .SYSTEM cannot be confused, and the
 *    whole table stays under 256 bytes, so one X register walks it. The
 *    first NKEEP records are the suffixes that stay in the name. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[25];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, 0, plugin_entry, 0, 0, 0,
    "ProDOS types by suffix"
};
#pragma rodata-name (pop)

#define NKEEP  6                /* the first six suffixes stay in the name */
static const unsigned char rules[] = {
    'M','E','T','S','Y','S','.', 0xFF,0x20,0x00,
    'O','P','.',                 0x06,0x00,0x00,
    'K','S','D','.',             0x06,0x00,0x00,
    'O','D','.',                 0x06,0x00,0x00,
    'G','M','2','.',             0x06,0x00,0x00,
    'V','D','H','.',             0x06,0x00,0x00,
    'K','H','S','.',             0xE0,0x80,0x02,
    'K','D','S','.',             0xE0,0x80,0x02,
    'Y','X','B','.',             0xE0,0x80,0x00,
    'Y','N','B','.',             0xE0,0x80,0x00,
    'P','W','A','.',             0x1A,0x00,0x00,
    'B','D','A','.',             0x19,0x00,0x00,
    'P','S','A','.',             0x1B,0x00,0x00,
    'S','A','B','.',             0xFC,0x08,0x01,
    'S','Y','S','.',             0xFF,0x20,0x00,
    'T','X','T','.',             0x04,0x00,0x00,
    'D','M','.',                 0x04,0x00,0x00,
    'V','S','C','.',             0x04,0x00,0x00,
    'N','I','B','.',             0x06,0x00,0x00,
    'B','M','.',                 0x06,0x00,0x00,
    'C','I','P','.',             0x06,0x20,0x00,
    'R','G','H','.',             0x06,0x20,0x00,
    'R','H','D','.',             0x06,0x20,0x00,
    0
};

static const char m_dir[]  = "Open a directory.";
static const char m_ask[]  = "Drop suffix?";
static const char m_done[] = "%u files typed, %u renamed, %u skipped";

/* MLI parameter blocks (cc65 packs them). GET_FILE_INFO $C4 takes 10
 * parameters, SET_FILE_INFO $C3 the first 7 of the same block;
 * RENAME $C2 {2, old, new}. */
struct Gfi {
    unsigned char n; unsigned char* path;
    unsigned char access, type, auxl, auxh;
    unsigned char storage; unsigned int blocks, mdate, mtime, cdate, ctime;
};
struct Rn { unsigned char n; unsigned char* old; unsigned char* new; };

/* Nothing here is read before being written at entry. */
static const struct A2fcApi* A;
static struct Panel* P;
static struct Entry* E;                 /* the entry being treated */
static unsigned char* TP;               /* its tag byte, and the bit in mask */
static unsigned char slot;              /* the service's offset in the table */
static unsigned char mask, i, n, cur, any, pass, ok;
static unsigned char typed, renamed, skipped;
static unsigned char last, cut, r, R;   /* rule_of: the last letter of the name,
                                         * the suffix with its dot, the rule and
                                         * where its type byte sits in rules[] */
static struct Gfi gfi;
static struct Rn rn = { 2, 0, 0 };      /* DATA: the count is loaded with the file,
                                         * the two paths are cut out of copy_buf */

/* The trampoline: the slot names the service, the argument the stub's
 * prologue pushed is dropped, and A/X and the C stack are as the service
 * expects them. */
#pragma optimize (push, off)
static void tramp(void)
{
    asm("lda %v", A);
    asm("sta ptr1");
    asm("lda %v+1", A);
    asm("sta ptr1+1");
    asm("ldy %v", slot);
    asm("lda (ptr1),y");
    asm("sta ptr2");
    asm("iny");
    asm("lda (ptr1),y");
    asm("sta ptr2+1");
    asm("jsr popax");
    asm("jmp (ptr2)");
}
#pragma optimize (pop)

/* The stubs. The last parameter is 16 bits wide so that the prologue
 * always pushes two bytes, which the trampoline drops. svc1 serves every
 * service taking one argument: message, confirm, draw_all, read_panel --
 * the caller sets slot, and two calls in a row set it once. */
#define SLOT(field) slot = offsetof(struct A2fcApi, field)
static unsigned char __fastcall__ svc1(const void* a) { asm("jmp %v", tramp); }
static unsigned char __fastcall__ build_full(char* out, const struct Panel* pan, const struct Entry* e)
    { asm("lda #%b", offsetof(struct A2fcApi, build_full)); asm("sta %v", slot); asm("jmp %v", tramp); }
static unsigned char __fastcall__ mli(unsigned char cmd, void* block)
    { asm("lda #%b", offsetof(struct A2fcApi, mli)); asm("sta %v", slot); asm("jmp %v", tramp); }

#pragma optimize (push, off)
/* The active panel is usable, and n, cur and any say what to walk: the
 * count, the cursor, and whether any tag bit is set. 0 = refused. */
static unsigned char prep(void)
{
    asm("lda %v", P);
    asm("sta ptr1");
    asm("lda %v+1", P);
    asm("sta ptr1+1");
    asm("ldy #0");                  /* no path: the volume list */
    asm("lda (ptr1),y");
    asm("beq pr9");
    asm("ldy #$5E");                /* fs: an image or a DOS 3.3 disk */
    asm("lda (ptr1),y");
    asm("bne pr9");
    asm("ldy #$40");                /* count */
    asm("lda (ptr1),y");
    asm("sta %v", n);
    asm("beq pr9");
    asm("ldy #$41");                /* cursor */
    asm("lda (ptr1),y");
    asm("sta %v", cur);
    asm("ldy #$5D");                /* the tag bytes, $4C to $5D */
    asm("lda #0");
    asm("pr1: ora (ptr1),y");
    asm("dey");
    asm("cpy #$4B");
    asm("bne pr1");
    asm("sta %v", any);
    asm("lda #1");
    asm("bne pr8");
    asm("pr9: lda #0");
    asm("pr8: ldx #0");
}

/* The rule whose ".SUFFIX" ends E's name (1 = found), read backwards from
 * the last letter: R is then where its type byte sits in rules[], r its
 * number, cut the length of the suffix with its dot. */
static unsigned char rule_of(void)
{
    asm("lda %v", E);
    asm("sta ptr1");
    asm("lda %v+1", E);
    asm("sta ptr1+1");
    asm("ldy #$11");                /* a directory has no suffix */
    asm("lda (ptr1),y");
    asm("cmp #$0F");
    asm("beq rl9");
    asm("ldy #$FF");
    asm("rl0: iny");
    asm("lda (ptr1),y");
    asm("bne rl0");
    asm("dey");                     /* the last letter of the name */
    asm("bmi rl9");
    asm("sty %v", last);
    asm("ldx #0");
    asm("stx %v", r);
    asm("rl4: stx %v", R);          /* the record starts here */
    asm("ldy %v", last);
    asm("rl5: lda %v,x", rules);
    asm("cmp (ptr1),y");
    asm("bne rl7");
    asm("inx");
    asm("cmp #$2E");                /* the dot closes the record: matched */
    asm("beq rl6");
    asm("dey");
    asm("bpl rl5");
    asm("bmi rl7");                 /* the name is shorter than the suffix */
    asm("rl6: tya");                /* the dot must not open the name */
    asm("beq rl7b");
    asm("txa");
    asm("sec");
    asm("sbc %v", R);
    asm("sta %v", cut);
    asm("stx %v", R);               /* R on the record's type byte */
    asm("lda #1");
    asm("bne rl8");
    asm("rl7: lda %v,x", rules);    /* past what is left of the suffix */
    asm("inx");
    asm("cmp #$2E");
    asm("bne rl7");
    asm("rl7b: inx");               /* and past the type and the auxtype */
    asm("inx");
    asm("inx");
    asm("inc %v", r);
    asm("lda %v,x", rules);
    asm("bne rl4");
    asm("rl9: lda #0");
    asm("rl8: ldx #0");
}
#pragma optimize (pop)

/* One target entry, in the pass that pass names. */
static void one(void)
{
    if (!rule_of() || !build_full((char*)rn.old + 1, P, E)) goto bad;
    /* The Pascal length byte of the path, then -- second pass -- the same
     * path without its suffix in rn.new, ok saying it was built. */
    asm("ldy #0");
    asm("sty %v", ok);
    asm("lda %v+1", rn);
    asm("sta ptr1");
    asm("lda %v+2", rn);
    asm("sta ptr1+1");
    asm("op1: iny");
    asm("lda (ptr1),y");
    asm("bne op1");
    asm("dey");
    asm("tya");
    asm("ldy #0");
    asm("sta (ptr1),y");
    asm("lda %v", pass);
    asm("beq op9");
    asm("lda %v", r);
    asm("cmp #%b", NKEEP);
    asm("bcc op9");                 /* this suffix stays in the name */
    asm("lda %v+3", rn);
    asm("sta ptr2");
    asm("lda %v+4", rn);
    asm("sta ptr2+1");
    asm("lda (ptr1),y");
    asm("sec");
    asm("sbc %v", cut);
    asm("bcc op9");
    asm("beq op9");                 /* nothing would be left of the name */
    asm("sta (ptr2),y");
    asm("tay");
    asm("op2: lda (ptr1),y");
    asm("sta (ptr2),y");
    asm("dey");
    asm("bne op2");
    asm("inc %v", ok);
    asm("op9:");
    if (pass) {
        if (!ok || mli(0xC2, &rn)) return;
        ++renamed;
        return;
    }
    gfi.n = 10;                     /* GET_FILE_INFO, then the same block back */
    if (mli(0xC4, &gfi)) goto bad;
    asm("lda #7");
    asm("sta %v", gfi);
    asm("ldx %v", R);
    asm("lda %v,x", rules);
    asm("sta %v+4", gfi);           /* type */
    asm("lda %v+1,x", rules);
    asm("sta %v+6", gfi);           /* aux high */
    asm("lda %v+2,x", rules);
    asm("sta %v+5", gfi);           /* aux low */
    if (mli(0xC3, &gfi)) goto bad;
    ++typed;
    return;
bad:
    if (!pass) ++skipped;
}

/* The entries of the panel: the tagged ones, or the one under the cursor
 * when nothing is tagged. E walks the table by 29 bytes, TP and mask the
 * tag bits. */
#pragma optimize (push, off)
static void walk(void)
{
    asm("lda %v", P);
    asm("sta ptr1");
    asm("lda %v+1", P);
    asm("sta ptr1+1");
    asm("ldy #$4A");                /* pan->e */
    asm("lda (ptr1),y");
    asm("sta %v", E);
    asm("iny");
    asm("lda (ptr1),y");
    asm("sta %v+1", E);
    asm("lda ptr1");                /* pan->tags */
    asm("clc");
    asm("adc #$4C");
    asm("sta %v", TP);
    asm("lda ptr1+1");
    asm("adc #0");
    asm("sta %v+1", TP);
    asm("lda #1");
    asm("sta %v", mask);
    asm("lda #0");
    asm("sta %v", i);
    asm("wk1: lda %v", i);
    asm("cmp %v", n);
    asm("bcs wk9");
    asm("lda %v", any);
    asm("beq wk2");
    asm("lda %v", TP);
    asm("sta ptr1");
    asm("lda %v+1", TP);
    asm("sta ptr1+1");
    asm("ldy #0");
    asm("lda (ptr1),y");
    asm("and %v", mask);
    asm("bne wk3");
    asm("beq wk4");
    asm("wk2: lda %v", i);
    asm("cmp %v", cur);
    asm("bne wk4");
    asm("wk3: jsr %v", one);
    asm("wk4: asl %v", mask);
    asm("bne wk5");
    asm("lda #1");
    asm("sta %v", mask);
    asm("inc %v", TP);
    asm("bne wk5");
    asm("inc %v+1", TP);
    asm("wk5: lda %v", E);
    asm("clc");
    asm("adc #29");
    asm("sta %v", E);
    asm("bcc wk6");
    asm("inc %v+1", E);
    asm("wk6: inc %v", i);
    asm("bne wk1");
    asm("wk9:");
}
#pragma optimize (pop)

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    A = api;
    P = api->panels;
    if (*api->active) ++P;
    rn.old = api->copy_buf;         /* two Pascal paths of 65 bytes */
    gfi.path = rn.old;              /* GET_FILE_INFO only ever reads that one */
    asm("lda %v+1", rn);
    asm("clc");
    asm("adc #65");
    asm("sta %v+3", rn);
    asm("lda %v+2", rn);
    asm("adc #0");
    asm("sta %v+4", rn);
    SLOT(message);
    if (!prep()) { svc1(m_dir); return; }
    typed = renamed = skipped = pass = 0;
    walk();
    SLOT(confirm);
    if (typed && svc1(m_ask)) { pass = 1; walk(); }
    SLOT(read_panel);
    svc1(0);
    svc1((const void*)1);
    SLOT(draw_all);
    svc1(0);
    /* api->note survives the redraw; copy_buf does not. */
    api->sprintf(api->note, m_done, typed, renamed, skipped);
    SLOT(message);
    svc1(api->note);
}
