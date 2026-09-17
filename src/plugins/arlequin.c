/* arlequin.c -- the pictures ARLEQUIN writes, ProDOS type $F8. From Return
 * or the ! menu, on the selected entry.
 *
 * ARLEQUIN 1.1 is Le Chat Mauve's double hi-res interpreter for its Feline
 * RGB card (1985, GLI16.2); `& LOAD` draws these pictures. They are read
 * here as that loader reads them -- the format, and how it was checked
 * against the loader itself under POM2, are in tools/arlequin_ref.py:
 *
 *   +0 width in groups of seven cells (1-20), +1 height in rows (1-192),
 *   +2 "gs", then a stream of literals, rotating runs and mask toggles,
 *   row by row, an auxiliary byte and a main byte per column.
 *
 * A picture smaller than the screen (the demonstration disk's windows) is
 * centred on black. The Chat Mauve's MIXED mode shows it: bit 7 of each
 * byte chooses sixteen colours or black and white, as in Extasie.
 *
 * The stream is decoded once without storing anything: the auxiliary plane
 * is the bank where /RAM lives, so a picture found incomplete costs nothing.
 * Only a whole one is decoded again for real, and /RAM is rebuilt after it.
 * Each pass opens the file afresh: a rewind would pull cc65's 32-bit
 * arguments into a window with no room for them.
 *
 * A BIG overlay whose code stops before $2000 (the Makefile links it with a
 * $0500 window): the picture owns $2000-$3FFF. The services are reached
 * through stubs, as in volname.c: a call through the table costs cc65 some
 * thirty-five bytes at every site. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);
unsigned char ar_decode(void);          /* arlequin.s */
void ar_show(void);
void ar_main_bank(void);
void ar_aux_move(void);
extern unsigned char ar_dry, ar_win;

struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[52]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = { MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUX, plugin_entry,
    {0,0,0}, "Arlequin $F8 pictures (Chat Mauve)" };
#pragma rodata-name (pop)

/* BSS: nothing zeroes it; every one of these is written before it is read. */
static const struct A2fcApi* A;
static FILE* in;
unsigned char* ar_buf;                  /* api->copy_buf, read by ar_decode */

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
/* The last parameter of each is 16 bits, so that the prologue always pushes
 * two bytes for tramp to drop. */
static FILE* __fastcall__ s_fopen(const char* path, const char* mode) STUB(fopen)
static unsigned int __fastcall__ s_fread(void* p, unsigned int sz, unsigned int n, FILE* f) STUB(fread)
static int __fastcall__ s_fclose(FILE* f) STUB(fclose)
static char* __fastcall__ s_strcpy(char* d, const char* s) STUB(strcpy)
static void* __fastcall__ s_memset(void* p, int c, unsigned int n) STUB(memset)
static char __fastcall__ s_wait(unsigned int unused) STUB(media_wait)
static unsigned char __fastcall__ s_ramfmt(unsigned int unused) STUB(ram_format)
#pragma optimize (pop)
#else
#define s_fopen A->fopen
#define s_fread A->fread
#define s_fclose A->fclose
#define s_strcpy A->strcpy
#define s_memset A->memset
#define s_wait(u) A->media_wait()
#define s_ramfmt(u) A->ram_format()
#endif

/* The refill ar_decode calls: up to 255 bytes into copy_buf, 0 at the end
 * of the file or on an error -- either way the stream is over. */
unsigned char ar_read(void)
{
    return (unsigned char)s_fread(ar_buf, 1, 255, in);
}

/* One pass over the file: 1 a whole picture, 0 a stream cut short or a
 * file that cannot be read to its end, 2 no Arlequin picture at all. */
static unsigned char pass(void)
{
    unsigned char k;
    in = s_fopen(A->full, "rb");
    if (!in) return 2;
    k = ar_decode();
    if (s_fclose(in) && k == 1) k = 0;
    return k;
}

static void note(const char* s) { s_strcpy(A->note, s); }

static const char m_bad[] = "Not an Arlequin $F8 picture.";
static const char m_cut[] = "Picture truncated.";
static const char m_ram[] = "/RAM rebuilt.";

void __fastcall__ plugin_entry(const struct A2fcApi* a)
{
    unsigned char k;

    A = a;
    ar_buf = a->copy_buf;
    k = 2;
    if (a->selected->type == 0xF8) {
        ar_dry = 1;
        k = pass();
    }
    if (k == 1) {
        ar_dry = 0;
        ar_main_bank();
        if (ar_win) {                   /* black around a window */
            s_memset((void*)0x2000, 0, 0x2000);
            ar_aux_move();
        }
        /* From here on the auxiliary bank is written: /RAM is rebuilt,
         * whatever the second pass finds. */
        k = pass();
    }
    if (k != 1) {
        if (!ar_dry) s_ramfmt(0);
        note(k == 2 ? m_bad : m_cut);
        return;
    }
    ar_show();
    s_wait(0);
    s_strcpy(a->reselect, a->selected->name);
    if (s_ramfmt(0)) note(m_ram);
}
