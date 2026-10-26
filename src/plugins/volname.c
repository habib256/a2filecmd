/* volname.c -- rename a ProDOS volume. A service-table overlay.
 *
 * From the ! menu. The volume is the selected entry when the active panel
 * is the volume list, otherwise the volume of the active panel's path (its
 * first component). An image or a DOS 3.3 disk is refused. The new name is
 * read with the core's prompt (a ProDOS name), then RENAME ($C2) is called
 * on the two Pascal paths "/OLD" and "/NEW".
 *
 * If ProDOS refuses while the prefix points inside that volume, the prefix
 * is emptied (SET_PREFIX of a zero-length path) and the call retried; if
 * that fails too the prefix is put back as it was. A fallback only: ProDOS
 * 8 2.4.3 renames the boot volume at the first call, prefix inside it or
 * not (bench/volname.py, from the volume list and from a directory of
 * the volume alike); it refuses only with a file open on it, which the
 * core never leaves behind. Once the volume is
 * renamed, everything that named it by its old name follows: the two
 * panels' paths and the program's own cfg_path are rewritten in place --
 * the core loads its overlays through that last one, so without the
 * rewrite the ! menu itself would be lost after renaming the boot volume
 * -- and the prefix is set to the root of the renamed volume.
 *
 * Calls through the table cost cc65
 * some 35 bytes each time (load the table, push the slot, jmpvec), so the
 * services used here are reached through stubs: a plain fastcall function
 * whose body puts the slot's offset in Y and jumps to one trampoline,
 * which drops the argument the prologue pushed, fetches the pointer from
 * the table and jumps there with A/X and the C stack as the service
 * expects them. Plain 6502 only. The stubs are compiled without the
 * optimiser, which would otherwise drop the ldy as dead before a jmp; the
 * last parameter of each is declared 16 bits so that the prologue always
 * pushes two bytes (a char would push one). The rewrite of a path and
 * the cut of the volume name are plain 6502 inline assembly for the same
 * reason: the C came out at three times the size. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[16];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0, 0, 0,
    "Rename a volume"
};
#pragma rodata-name (pop)

/* MLI parameter blocks (cc65 packs them): RENAME $C2 {2, old, new},
 * GET_PREFIX $C7 and SET_PREFIX $C6 {1, path}. */
struct Rn  { unsigned char n; unsigned char* old; unsigned char* new; };
struct Pfx { unsigned char n; unsigned char* path; };

static const char m_sel[]  = "Select a ProDOS volume.";
static const char m_used[] = "Name in use.";
static const char m_fail[] = "Rename volume";
static const char m_twin[] = "Two volumes of this name: rename refused.";
static const unsigned char nopfx = 0;       /* a zero-length Pascal path: no prefix */
/* The two lines built in place (DATA, loaded with the file): the prompt's
 * label "Rename volume /OLD to", the last message "Volume renamed to /NEW"
 * -- kept here, not in copy_buf, which rereading the panels overwrites. */
static char ask[]  = "New name for /...............";
static char done[] = "Volume renamed to /...............";
#define ASK_NAME  13
#define DONE_NAME 18

/* Nothing here is read before being written at entry. */
static const struct A2fcApi* A;
static unsigned char OLD[NAME_LEN + 1];     /* Pascal "/OLD", zero-terminated too */
static unsigned char NEW[NAME_LEN + 1];     /* Pascal "/NEW", zero-terminated too */
static unsigned char n;                     /* OLD[0] */
static unsigned char c;                    /* after name extraction: 0 checks paths, 1 rewrites */
static unsigned char* PFX;                  /* api->copy_buf: the prefix as it was, Pascal (64 at most) */
static char TMP[PATH_LEN];                  /* the tail of a path being rewritten; the name being cut */
static struct Rn rn = { 2, OLD, NEW };      /* DATA: set once, loaded with the file */
static struct Pfx pfx = { 1, 0 };

/* The stubs into the service table (see above). */
#pragma optimize (push, off)
#pragma warn (unused-param, push, off)
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
static void __fastcall__ display_message(const char* s) STUB(message)
static unsigned char __fastcall__ prompt(const char* label, const char* initial, unsigned int hex) STUB(prompt)
static void __fastcall__ report_error(const char* what) STUB(report_error)
static unsigned char __fastcall__ mli(unsigned char cmd, void* block) STUB(mli)
static char* __fastcall__ scpy(char* d, const char* s) STUB(strcpy)
static unsigned char __fastcall__ slen(const char* s) STUB(strlen)
#pragma warn (unused-param, pop)
#pragma optimize (pop)

/* A big overlay's return redraws both panels. Keep the bounded message in
 * the resident note so it remains visible after that redraw, including a
 * refusal on an image panel. This writes MAIN only, never disk or AUX. */
static void __fastcall__ msg(const char* s)
{
    scpy(A->note, s);
    display_message(A->note);
}

/* ON_LINE $C5 on unit 0: {2, unit, buffer}, 16 bytes a record. */
static struct Ol { unsigned char n, unit; unsigned char* buf; } ol = { 2, 0, 0 };

/* RENAME goes by path, and ProDOS resolves "/OLD" to either of two volumes
 * of that name: the one renamed may not be the one chosen. 0: one volume
 * at most answers to OLD; 1: two or more; 2: ON_LINE failed. The table
 * goes to copy_buf + 128, past the saved prefix (65 bytes at most); it ends
 * at the first record whose byte 0 is zero. */
static unsigned char twins(void)
{
    static unsigned char *p, k, m, j;
    p = PFX + 128; ol.buf = p;
    if (mli(0xC5, &ol)) return 2;
    m = 0; k = 16;
    do {
        if (!*p) break;
        if ((unsigned char)((*p & 15) + 1) == n) {
            for (j = 1; j < n && p[j] == OLD[j + 1]; ++j) ;
            if (j == n) ++m;
        }
        p += 16;
    } while (--k);
    return m > 1;
}

static unsigned char __fastcall__ set_prefix(const unsigned char* p) { pfx.path = (unsigned char*)p; return mli(0xC6, &pfx); }
static unsigned char rename_volume(void) { return mli(0xC2, &rn); }

/* If `path` starts with "/OLD" (whole component), checks or rewrites it
 * with "/NEW": 0 unrelated, 1 fits, 2 too long. Plain 6502:
 * the tail goes through TMP, then "/NEW" and the tail are laid down. */
#pragma optimize (push, off)
#pragma warn (unused-param, push, off)
static unsigned char __fastcall__ fix(char* path)
{
    asm("sta ptr1");
    asm("stx ptr1+1");
    asm("ldy #0");
    asm("fx1: lda (ptr1),y");
    asm("cmp %v+1,y", OLD);
    asm("bne fxno");
    asm("iny");
    asm("cpy %v", n);
    asm("bne fx1");
    asm("lda (ptr1),y");            /* what follows the head: the end or a slash */
    asm("beq fx2");
    asm("cmp #$2F");
    asm("bne fxno");
    asm("fx2: ldx #0");             /* the tail, terminator included, to TMP */
    asm("fx3: lda (ptr1),y");
    asm("sta %v,x", TMP);
    asm("beq fx4");
    asm("iny");
    asm("inx");
    asm("bne fx3");
    asm("fx4: txa");                /* the new length: the tail plus "/NEW" */
    asm("clc");
    asm("adc %v", NEW);
    asm("cmp #%b", PATH_LEN);
    asm("bcs fxlong");
    asm("lda %v", c);
    asm("beq fx8");                 /* preflight: no path bytes or panel state change */
    asm("ldy #0");
    asm("fx5: lda %v+1,y", NEW);
    asm("beq fx6");
    asm("sta (ptr1),y");
    asm("iny");
    asm("bne fx5");
    asm("fx6: ldx #0");
    asm("fx7: lda %v,x", TMP);
    asm("sta (ptr1),y");
    asm("beq fx8");
    asm("iny");
    asm("inx");
    asm("bne fx7");
    asm("fx8: lda #1");
    asm("bne fx9");                 /* always: both ends fall into the epilogue, which drops the argument */
    asm("fxno: lda #0");
    asm("beq fx9");
    asm("fxlong: lda #2");
    asm("fx9: ldx #0");
}
#pragma warn (unused-param, pop)
#pragma optimize (pop)

/* A panel whose path named the volume: rewritten, reread from its start.
 * With an image open, img_len splits the path into the image file and the
 * path inside it: it moves by the change in the volume name's length. */
static void __fastcall__ fix_panel(struct Panel* pan)
{
    if (fix(pan->path)) {
        pan->first = 0;
        if (pan->fs && pan->img_len) pan->img_len += NEW[0] - n;
    }
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    struct Panel* pan;
    const char* p;

    A = api;
    PFX = api->copy_buf;
    pan = api->panels;
    if (*api->active) ++pan;

    /* "/OLD": the selected volume, or the first component of the path.
     * An image or a DOS 3.3 disk has no ProDOS volume to rename. */
    p = pan->path[0] ? pan->path : api->selected->name;
    if (pan->fs || *p != '/') { msg(m_sel); return; }
    scpy(TMP, p);
    for (n = 1; (c = TMP[n]) != 0 && c != '/'; ++n) ;
    TMP[n] = 0;
    scpy((char*)OLD + 1, TMP);
    OLD[0] = n;

    scpy(ask + ASK_NAME, (char*)OLD + 1);
    if (!prompt(ask, (char*)OLD + 2, 0)) return;
    NEW[1] = '/';
    scpy((char*)NEW + 2, api->input);
    NEW[0] = slen((char*)NEW + 1);

    /* Refuse before any prefix or disk change if even one path would stay
     * under the old name. In particular cfg_path must still find overlays.
     * Scratch TMP is separate from the saved prefix; no AUX is touched. */
    c = 0;
    if (fix(api->panels[0].path) == 2 || fix(api->panels[1].path) == 2 ||
        fix((char*)api->cfg_path) == 2) { msg("Path too long."); return; }
    c = 1;

    /* The prefix, kept in case of failure; then the rename, retried
     * without a prefix if ProDOS refuses. */
    pfx.path = PFX;
    /* Do not change the prefix or volume without a restorable prefix.
     * GET_PREFIX failure leaves copy_buf holding unrelated scratch data. */
    if (mli(0xC7, &pfx)) { report_error(m_fail); return; }
    /* Read after the question: a disk inserted while it was asked counts.
     * Nothing has changed yet, so a refusal leaves the prefix as it is. */
    switch (twins()) {
    case 1: msg(m_twin); return;
    case 2: report_error(m_fail); return;
    }
    /* ProDOS renames a volume to the name of another volume on line, and
     * two volumes then answer to one path. SET_PREFIX finds no volume
     * ($45) only when "/NEW" is free; anything else refuses, the prefix
     * put back. */
    if (set_prefix(NEW) != 0x45) { msg(m_used); goto restore; }
    if (rename_volume()) {
        if (set_prefix(&nopfx) || rename_volume()) {
            report_error(m_fail);
restore:
            if (set_prefix(PFX)) report_error(m_fail);
            return;
        }
    }

    /* Everything that named the volume follows it: the panels' paths, the
     * program's cfg_path (where it loads its overlays from), and the
     * prefix, set to the root of the renamed volume -- what it named
     * before, it would name under the old name. */
    fix_panel(api->panels);
    fix_panel(api->panels + 1);
    fix((char*)api->cfg_path);

    scpy(done + DONE_NAME, (char*)NEW + 1);
    /* The resident rereads both panels AFTER this big overlay returns.
     * Their entry tables start at $2000 and can overwrite this overlay's
     * DATA/BSS while it is still running. Do not call read_panel here.
     * The volume and its absolute paths already moved; never rename it
     * again or announce complete success on prefix failure. */
    if (set_prefix(NEW)) report_error(m_fail);
    else msg(done);
}
