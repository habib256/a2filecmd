/* BOOTBLK replaces blocks 0 and 1 only after reading both source blocks
 * and both originals. Each write is read back; any failed installation
 * restores and verifies BOTH originals, including a write that returned an
 * error after actually reaching the disk. Power loss is not recoverable by
 * this in-memory backup. No auxiliary memory is used.
 *
 * BIG owns the main graphics page: originals at $3000-$33FF, replacement
 * at $3400-$37FF. Code and BSS are linked below $3000. copy_buf is reserved
 * for verification. Messages survive the core's panel reload via api->note.
 * The native service/volume-name stubs below keep the original 6502 ABI.
 */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0, 0, 0,
    "Rewrite the ProDOS boot blocks of a volume"
};
#pragma rodata-name (pop)

/* MLI parameter blocks (cc65 packs them): READ_BLOCK $80 / WRITE_BLOCK $81
 * {3, unit, buffer, block}, ON_LINE $C5 {2, unit, buffer}. */
struct Blk { unsigned char n, unit; unsigned char* buf; unsigned int block; };
struct Onl { unsigned char n, unit; unsigned char* buf; };

static const char m_ro[]   = "Not a ProDOS volume.";
static const char m_sel[]  = "Select a volume.";
static const char m_same[] = "That is the volume booted from.";
static const char m_nf[]   = "Volume not on line.";
static const char m_read[] = "Boot blocks unreadable: nothing written.";
static const char m_restored[] = "Boot write failed; both original blocks restored and verified.";
static const char m_failed[] = "BOOT RESTORE FAILED: target may not boot. Recover before retrying.";
#ifndef ORIGINAL
#define ORIGINAL ((unsigned char*)0x3000)
#define REPLACEMENT ((unsigned char*)0x3400)
#endif
static const char a_1[]    = "Rewrite the boot blocks of ";
static const char a_2[]    = " from ";
static const char a_3[]    = "?";
static const char d_1[]    = "Boot blocks of ";
static const char d_2[]    = " rewritten from ";

/* Nothing here is read before being written at entry. */
static const struct A2fcApi* A;
static struct Panel* pan;                   /* the active panel */
static struct Entry* sel;                   /* the entry under the cursor */
static unsigned char* BUF;                  /* api->copy_buf: ON_LINE, then a block */
static char* DST;                           /* where vol_of writes */
static char TGT[NAME_LEN];                  /* "/TARGET" */
static char SRC[NAME_LEN];                  /* "/BOOT", the volume booted from */
static char LINE[72];                       /* the question, then the last word */
static unsigned char blen;                  /* what LINE holds */
static unsigned char inpath;                /* the panel is inside a volume */
static unsigned char tunit, sunit, b, failed;
static struct Blk blk = { 3, 0, 0, 0 };     /* DATA: set once, loaded with the file */
static struct Onl onl = { 2, 0, 0 };

static void msg(const char* s) { A->strcpy(A->note, s); }

/* The stubs into the service table (see above). */
#ifndef PLUGIN_HOST
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
static unsigned char __fastcall__ ask(const char* s) STUB(confirm)
static unsigned char __fastcall__ mli(unsigned char cmd, void* block) STUB(mli)

/* LINE, at blen, gets `s`; blen follows. */
static void __fastcall__ cat(const char* s)
{
    asm("sta ptr1");
    asm("stx ptr1+1");
    asm("ldx %v", blen);
    asm("ldy #0");
    asm("ct1: lda (ptr1),y");
    asm("sta %v,x", LINE);
    asm("beq ct2");
    asm("inx");
    asm("iny");
    asm("bne ct1");
    asm("ct2: stx %v", blen);
}

/* The first component of `p` ("/VOL/DIR/FILE", or "/VOL") into DST,
 * NAME_LEN - 1 characters at most, zero terminated. */
static void __fastcall__ vol_of(const char* p)
{
    asm("sta ptr1");
    asm("stx ptr1+1");
    asm("lda %v", DST);
    asm("sta ptr2");
    asm("lda %v+1", DST);
    asm("sta ptr2+1");
    asm("ldy #0");
    asm("vo1: lda (ptr1),y");
    asm("beq vo3");                 /* the end of the path */
    asm("cpy #0");
    asm("beq vo2");                 /* the leading slash is kept */
    asm("cmp #$2F");
    asm("beq vo3");                 /* the slash that ends the volume name */
    asm("vo2: sta (ptr2),y");
    asm("iny");
    asm("cpy #%b", NAME_LEN - 1);
    asm("bne vo1");
    asm("vo3: lda #0");
    asm("sta (ptr2),y");
}

/* The unit (DSSS0000) of the volume named "/NAME" in the ON_LINE list left
 * in BUF, or 0 -- never a valid unit, slot 0 being the machine itself. */
static unsigned char __fastcall__ find_unit(const char* name)
{
    asm("sta ptr2");
    asm("stx ptr2+1");
    asm("lda %v", BUF);
    asm("sta ptr1");
    asm("lda %v+1", BUF);
    asm("sta ptr1+1");
    asm("ldx #16");                 /* sixteen entries at most */
    asm("stx tmp2");
    asm("fu1: ldy #0");
    asm("lda (ptr1),y");
    asm("beq fu6");                 /* the end of the list */
    asm("and #15");
    asm("beq fu4");                 /* that drive holds no volume */
    asm("sta tmp1");
    asm("ldy #1");
    asm("fu2: lda (ptr1),y");
    asm("cmp (ptr2),y");
    asm("bne fu4");
    asm("iny");
    asm("dec tmp1");
    asm("bne fu2");
    asm("lda (ptr2),y");            /* "/NAME" must end there too */
    asm("bne fu4");
    asm("ldy #0");
    asm("lda (ptr1),y");
    asm("and #$F0");
    asm("bne fu7");                 /* always: a unit is never 0 */
    asm("fu4: lda ptr1");           /* the next entry, sixteen bytes on */
    asm("clc");
    asm("adc #16");
    asm("sta ptr1");
    asm("bcc fu5");
    asm("inc ptr1+1");
    asm("fu5: dec tmp2");
    asm("bne fu1");
    asm("fu6: lda #0");
    asm("fu7: ldx #0");
}
#pragma optimize (pop)

#else
#define ask(s) A->confirm(s)
#define mli(c, p) A->mli(c, p)
static void cat(const char* s) {
    while (*s) LINE[blen++] = *s++;
    LINE[blen] = 0;
}
static void vol_of(const char* p) {
    unsigned char i = 0;
    while (p[i] && i < NAME_LEN - 1 && (!i || p[i] != '/')) {
        DST[i] = p[i]; ++i;
    }
    DST[i] = 0;
}
static unsigned char find_unit(const char* name) {
    unsigned int i;
    unsigned char n;
    for (i = 0; i < 256 && BUF[i]; i += 16) {
        n = BUF[i] & 15;
        if (n && strlen(name) == n + 1 && !memcmp(BUF + i + 1, name + 1, n))
            return BUF[i] & 0xF0;
    }
    return 0;
}
#endif

/* Keep the saved bytes out of the readback buffer. A failed WRITE may have
 * modified the medium, so callers must restore even that very block. */
static unsigned char write_checked(unsigned char* bytes)
{
    unsigned int i;
    blk.unit = tunit;
    blk.buf = bytes;
    if (mli(0x81, &blk)) return 0;
    blk.buf = BUF;
    if (mli(0x80, &blk)) return 0;
    for (i = 0; i < 512; ++i) if (BUF[i] != bytes[i]) return 0;
    return 1;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    A = api;
    BUF = api->copy_buf;
    sel = api->selected;
    pan = api->panels;
    if (*api->active) ++pan;
    if (pan->fs) { msg(m_ro); return; }       /* an image, a DOS 3.3 catalog */

    /* The target: the volume of the path, or the selected volume. */
    inpath = pan->path[0];
    DST = TGT;
    if (inpath) vol_of(pan->path);
    else {
        /* the volume list: "/VOL"; a DOS 3.3 drive has no leading slash */
        if (sel->name[0] != '/') { msg(m_sel); return; }
        vol_of(sel->name);
    }
    DST = SRC;
    vol_of(api->cfg_path);                    /* the volume booted from */

    /* One ON_LINE for both units, before BUF becomes the block buffer. */
    onl.unit = 0;
    onl.buf = BUF;
    if (mli(0xC5, &onl)) { msg(m_read); return; }
    sunit = find_unit(SRC);
    tunit = inpath ? find_unit(TGT) : (unsigned char)(sel->mdate << 4);
    if (!sunit || !tunit) { msg(m_nf); return; }
    if (sunit == tunit) { msg(m_same); return; }

    blen = 0;
    cat(a_1); cat(TGT); cat(a_2); cat(SRC); cat(a_3);
    if (!ask(LINE)) return;

    /* Preflight: no target write until all four reads succeeded. */
    for (b = 0; b < 2; ++b) {
        blk.block = b;
        blk.unit = sunit;
        blk.buf = REPLACEMENT + (unsigned int)b * 512;
        if (mli(0x80, &blk)) { msg(m_read); return; }
        blk.unit = tunit;
        blk.buf = ORIGINAL + (unsigned int)b * 512;
        if (mli(0x80, &blk)) { msg(m_read); return; }
    }
    for (b = 0; b < 2; ++b) {
        blk.block = b;
        if (!write_checked(REPLACEMENT + (unsigned int)b * 512)) {
            failed = 0;
            for (b = 0; b < 2; ++b) {
                blk.block = b;
                if (!write_checked(ORIGINAL + (unsigned int)b * 512)) failed = 1;
            }
            msg(failed ? m_failed : m_restored);
            return;
        }
    }

    blen = 0;
    cat(d_1); cat(TGT); cat(d_2); cat(SRC);
    msg(LINE);
}
