/* volname.c -- rename a ProDOS volume. A small service-table overlay.
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
 * Written for size (1,280 bytes). A call through the table costs cc65
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
    unsigned char r0, r1, r2; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, 0, plugin_entry, 0, 0, 0,
    "Rename a volume"
};
#pragma rodata-name (pop)

/* MLI parameter blocks (cc65 packs them): RENAME $C2 {2, old, new},
 * GET_PREFIX $C7 and SET_PREFIX $C6 {1, path}. */
struct Rn  { unsigned char n; unsigned char* old; unsigned char* new; };
struct Pfx { unsigned char n; unsigned char* path; };

static const char m_ro[]   = "Not a ProDOS volume.";
static const char m_sel[]  = "Select a volume.";
static const char m_to[]   = " to";
static const char m_fail[] = "Rename volume";
static const unsigned char nopfx = 0;       /* a zero-length Pascal path: no prefix */
/* The two lines built in place (DATA, loaded with the file): the prompt's
 * label "Rename volume /OLD to", the last message "Volume renamed to /NEW"
 * -- kept here, not in copy_buf, which rereading the panels overwrites. */
static char ask[]  = "Rename volume /...............   ";
static char done[] = "Volume renamed to /...............";
#define ASK_NAME  14
#define DONE_NAME 18

/* Nothing here is read before being written at entry. */
static const struct A2fcApi* A;
static unsigned char OLD[NAME_LEN + 1];     /* Pascal "/OLD", zero-terminated too */
static unsigned char NEW[NAME_LEN + 1];     /* Pascal "/NEW", zero-terminated too */
static unsigned char n;                     /* OLD[0] */
static unsigned char c;
static unsigned char* PFX;                  /* api->copy_buf: the prefix as it was, Pascal (64 at most) */
static char TMP[PATH_LEN];                  /* the tail of a path being rewritten; the name being cut */
static struct Rn rn = { 2, OLD, NEW };      /* DATA: set once, loaded with the file */
static struct Pfx pfx = { 1, 0 };

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
static void __fastcall__ report_error(const char* what) STUB(report_error)
static void __fastcall__ draw_all(unsigned int unused) STUB(draw_all)
static unsigned char __fastcall__ read_panel(unsigned int i) STUB(read_panel)
static unsigned char __fastcall__ mli(unsigned char cmd, void* block) STUB(mli)
static char* __fastcall__ scpy(char* d, const char* s) STUB(strcpy)
static unsigned char __fastcall__ slen(const char* s) STUB(strlen)
#pragma optimize (pop)

static void __fastcall__ set_prefix(const unsigned char* p) { pfx.path = (unsigned char*)p; mli(0xC6, &pfx); }
static unsigned char rename_volume(void) { return mli(0xC2, &rn); }

/* If `path` starts with "/OLD" (whole component), rewrites it in place with
 * "/NEW" (if the result fits PATH_LEN); returns 1 if it did. Plain 6502:
 * the tail goes through TMP, then "/NEW" and the tail are laid down. */
#pragma optimize (push, off)
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
    asm("bcs fxno");
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
    asm("fx9: ldx #0");
}
#pragma optimize (pop)

/* A panel whose path named the volume: rewritten, reread from its start. */
static void __fastcall__ fix_panel(struct Panel* pan)
{
    if (fix(pan->path)) pan->first = 0;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    struct Panel* pan;
    const char* p;

    A = api;
    PFX = api->copy_buf;
    pan = api->panels;
    if (*api->active) ++pan;
    if (pan->fs) { msg(m_ro); return; }

    /* "/OLD": the selected volume, or the first component of the path. */
    p = pan->path[0] ? pan->path : api->selected->name;
    if (*p != '/') { msg(m_sel); return; }     /* nothing, or a DOS 3.3 disk */
    scpy(TMP, p);
    for (n = 1; (c = TMP[n]) != 0 && c != '/'; ++n) ;
    TMP[n] = 0;
    scpy((char*)OLD + 1, TMP);
    OLD[0] = n;

    scpy(ask + ASK_NAME, (char*)OLD + 1);
    scpy(ask + ASK_NAME + n, m_to);
    if (!prompt(ask, (char*)OLD + 2, 0)) return;
    NEW[1] = '/';
    scpy((char*)NEW + 2, api->input);
    NEW[0] = slen((char*)NEW + 1);

    /* The prefix, kept in case of failure; then the rename, retried
     * without a prefix if ProDOS refuses. */
    pfx.path = PFX;
    mli(0xC7, &pfx);
    if (rename_volume()) {
        set_prefix(&nopfx);
        if (rename_volume()) {
            report_error(m_fail);
            set_prefix(PFX);
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
    set_prefix(NEW);

    scpy(done + DONE_NAME, (char*)NEW + 1);
    read_panel(0);
    read_panel(1);
    draw_all(0);
    msg(done);
}
