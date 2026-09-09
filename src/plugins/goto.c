/* goto.c -- favourite directories: jump to one in two keys, add the
 * current one, remove one. A service-table overlay.
 *
 * From the ! menu. The favourites live in a text file next to the program:
 * api->cfg_path is "/VOL/A2FILE/A2FILE.CFG", cut after its last slash and
 * followed by "GOTO.CFG" -- up to nine lines "PATH\r", type $04, the very
 * shape A2FILE.CFG has, so the file stays readable and editable by hand.
 * The overlay clears the screen, lists what it read, one numbered row each,
 * and reads one key:
 *
 *   1-9  the active panel jumps to that favourite;
 *   A    the active panel's path is appended and the file rewritten --
 *        unless it is the volume list, an image or a DOS 3.3 panel, a path
 *        already listed, or the list already holds nine;
 *   D    then a digit: that favourite is dropped and the file rewritten;
 *   ESC  nothing.
 *
 * One key, one action: the screen is shown once and the overlay returns to
 * the panels with its message; running it again shows the new list.
 *
 * A BIG overlay, and not by taste: the small window is 1,280 bytes all
 * told, and this -- reading, parsing and rewriting a file, a nine-row
 * screen, three commands with their guards and a dozen messages -- comes to
 * some 1,500 bytes of cc65 code and 280 of strings. The small overlays
 * around it (volname, fixtypes) do one thing each, with no screen and no
 * file. Being big has one consequence worth stating: the entry tables of
 * the two panels live at $2000-$3FDC, which a big overlay covers, so
 * api->read_panel MUST NOT be called from here -- it would write directory
 * entries straight into this code. The core rereads and redraws both panels
 * on its own when a big overlay returns, so a jump only has to set the
 * panel's path; to tell a favourite that has been deleted or unmounted from
 * a good one, the path is opened with api->dir_open first (it reads the
 * core's own buffer, not ours) and the panel is left where it is if that
 * fails. For the same reason the last word goes through api->note, which
 * the core writes on line 22 after its redraw, and not through
 * api->message, which the redraw would wipe.
 *
 * Memory: the file is under 5,376 bytes, so $3000-$3FFF is ours (README).
 * The nine paths sit at $3000 in slots of 65 bytes (PATH_LEN and the zero,
 * 585 bytes in all): a whole ProDOS path fits, where api->copy_buf's 512
 * bytes would have forced 55 characters. $3400 upward holds the file as
 * read, then as written. api->copy_buf is left to the core, which uses it
 * for the directory block dir_open reads.
 *
 * Every service is reached through a stub -- a fastcall function whose body
 * puts the service's offset in Y and jumps to one trampoline, which drops
 * the argument its prologue pushed, fetches the pointer from the table and
 * jumps there with A/X and the C stack as the service expects them (the
 * trick volname.c explains: cc65 spends some 35 bytes on a call through a
 * pointer held in a variable, three on a call to a stub). It keeps the file
 * near two kilobytes, which is what makes $3000 legal to use. Plain 6502,
 * compiled without the optimiser (which would drop the ldy as dead before a
 * jmp); the last parameter of each stub is 16 bits so that the prologue
 * always pushes two bytes. */
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
    "Favourite directories: jump in two keys, add, del"
};
#pragma rodata-name (pop)

#define MAXFAV  9
#define SLOT    (PATH_LEN + 1)          /* 65: a whole ProDOS path and its zero */
#define LIST    ((char*)0x3000)         /* 9 x 65 = 585: $3000-$3248 */
#define TEXT    ((char*)0x3400)         /* GOTO.CFG as read, then as written */
#define MAXTEXT 2000                    /* of the 3 KB there: nine lines need 594 */
#define NONE    0xFF                    /* save(): no slot left out */
#define TAIL(s) (sizeof (s) - 1)        /* where the path goes after a heading */

static const char f_name[] = "GOTO.CFG";
static const char f_rb[]   = "rb";
static const char f_wb[]   = "wb";
static const char m_title[] = "GOTO -- favourite directories";
static const char m_keys[]  = "1-9 Go,A Add this directory,D Delete,ESC Back";
static const char m_none[]  = "No favourites yet: A adds this directory";
static const char m_dir[]   = "Not a ProDOS directory: nothing to add.";
static const char m_room[]  = "The list is full: nine favourites.";
static const char m_dup[]   = "Already in the list.";
static const char m_gone[]  = "Gone: ";
static const char m_which[] = "Delete which one? 1-9";
static const char m_err[]   = "GOTO.CFG cannot be written.";
static const char m_jump[]  = "Jumped to ";
static const char m_add[]   = "Added ";
static const char m_del[]   = "Removed ";
static char num[] = "1 ";               /* DATA: the row number, rewritten in place */

/* Nothing here is read before being written at entry. */
static const struct A2fcApi* A;
static struct Panel* P;                 /* the active panel */
static char* N;                         /* api->note: what line 22 will say */
static FILE* fh;
static unsigned char count;
static char cfg[PATH_LEN];              /* "/VOL/A2FILE/GOTO.CFG" */

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
static void __fastcall__ cls(unsigned int unused) STUB(clrscr)
static void __fastcall__ at(unsigned char x, unsigned int y) STUB(gotoxy)
static void __fastcall__ put(const char* s) STUB(cputs)
static void __fastcall__ kbar(unsigned char x, const char* spec) STUB(keys_bar)
static char __fastcall__ getkey(unsigned int unused) STUB(cgetc)
static unsigned char __fastcall__ dopen(const char* path) STUB(dir_open)
static void __fastcall__ dclose(unsigned int unused) STUB(dir_close)
static char* __fastcall__ scpy(char* d, const char* s) STUB(strcpy)
static int __fastcall__ scmp(const char* a, const char* b) STUB(strcmp)
static unsigned char __fastcall__ slen(const char* s) STUB(strlen)
static FILE* __fastcall__ fopn(const char* path, const char* mode) STUB(fopen)
static unsigned int __fastcall__ frd(void* p, unsigned int sz, unsigned int n, FILE* f) STUB(fread)
static unsigned int __fastcall__ fwr(const void* p, unsigned int sz, unsigned int n, FILE* f) STUB(fwrite)
static void __fastcall__ fcls(FILE* f) STUB(fclose)
#pragma optimize (pop)

/* Slot `i` of the list, without a multiplication. */
static char* __fastcall__ slot(unsigned char i)
{
    char* p = LIST;
    while (i--) p += SLOT;
    return p;
}

/* GOTO.CFG into the slots: its CR-terminated lines, nine at most, cut at
 * PATH_LEN, empty ones dropped. A missing file simply means no favourites. */
static void load(void)
{
    unsigned int n;
    unsigned char j;
    char* p = TEXT;
    char* d;
    count = 0;
    fh = fopn(cfg, f_rb);
    if (!fh) return;
    n = frd(p, 1, MAXTEXT, fh);
    fcls(fh);
    p[n] = 0;
    while (*p && count < MAXFAV) {
        d = slot(count);
        j = 0;
        while (*p && *p != '\r') {
            if (j < PATH_LEN - 1) d[j++] = *p;
            ++p;
        }
        d[j] = 0;
        if (j) ++count;
        if (*p) ++p;                    /* the CR */
    }
}

/* The slots back to GOTO.CFG, one "PATH\r" line each, type $04, in one
 * write; slot `dead` is left out, which is how a favourite is removed. */
static void save(unsigned char dead)
{
    unsigned char i;
    char* p = TEXT;
    char* q;
    for (i = 0; i < count; ++i) {
        if (i == dead) continue;
        q = slot(i);
        while (*q) *p++ = *q++;
        *p++ = '\r';
    }
    *A->filetype = 0x04;
    *A->auxtype = 0;
    fh = fopn(cfg, f_wb);
    if (!fh) { scpy(N, m_err); return; }
    fwr(TEXT, 1, p - TEXT, fh);
    fcls(fh);
}

/* The whole screen: the title, one numbered row per favourite, the keys. */
static void draw(void)
{
    unsigned char i;
    cls(0);
    at(2, 1);
    put(m_title);
    if (!count) { at(2, 3); put(m_none); }
    for (i = 0; i < count; ++i) {
        at(2, 3 + i);
        num[0] = '1' + i;
        put(num);
        put(slot(i));
    }
    kbar(0, m_keys);
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char i, k, del = 0;
    char* p;

    A = api;
    N = api->note;
    P = api->panels;
    if (*api->active) ++P;

    /* "/VOL/A2FILE/A2FILE.CFG" -> "/VOL/A2FILE/GOTO.CFG" */
    scpy(cfg, api->cfg_path);
    i = slen(cfg);
    while (i && cfg[i] != '/') --i;
    scpy(cfg + i + 1, f_name);

    load();
    draw();
    /* One key. Bit 5 is set on every digit, so `| 0x20` lower-cases the
     * letters and leaves 1-9 alone; and since count <= 9, i < count can
     * only be true for a digit key. */
    k = getkey(0) | 0x20;
    if (count && k == 'd') {
        msg(m_which);
        k = getkey(0) | 0x20;
        del = 1;
    }
    i = k - '1';

    if (i < count) {
        p = slot(i);
        if (del) {                      /* dropped, and the file rewritten */
            scpy(scpy(N, m_del) + TAIL(m_del), p);
            save(i);
        } else if (!dopen(p)) {         /* read_panel is out of reach: see the head */
            scpy(scpy(N, m_gone) + TAIL(m_gone), p);
        } else {
            dclose(0);
            scpy(P->path, p);
            P->first = 0;
            P->cursor = 0;              /* read_panel's top follows the cursor */
            P->fs = FS_PRODOS;
            scpy(scpy(N, m_jump) + TAIL(m_jump), p);
        }
    } else if (!del && k == 'a') {
        p = P->path;
        if (!*p || P->fs) scpy(N, m_dir);
        else if (count == MAXFAV) scpy(N, m_room);
        else {
            for (i = 0; i < count; ++i)
                if (!scmp(slot(i), p)) { scpy(N, m_dup); break; }
            if (i == count) {
                scpy(slot(count), p);
                ++count;
                scpy(scpy(N, m_add) + TAIL(m_add), p);
                save(NONE);             /* which says so if it fails */
            }
        }
    } else if (!count) {
        scpy(N, m_none);                /* an empty list: how to fill it */
    }
}
