/* extasie.c -- the pictures Extasie writes, ProDOS type $F2. From the ! menu,
 * on the selected entry.
 *
 * Extasie is Purplesoft's drawing program for the Le Chat Mauve RGB card, and
 * its own title screen says what the format is for: "Aucun autre programme ne
 * peut melanger librement les 16 couleurs et le Noir et Blanc 560". So a
 * picture is DOUBLE hi-res shown in the card's MIXED mode, 560 dots in black
 * and white and 140 cells of sixteen colours chosen byte by byte -- not the
 * plain hi-res page this overlay used to draw.
 *
 * The file: two bytes of its own length, then a run-length stream --
 *
 *   [count]          bit 7 set: the next byte repeated, count times;
 *                    bit 7 clear: the next `count` bytes as they are.
 *                    The low seven bits are the count, and 0 means 128.
 *
 * It decodes to 15,360 bytes read COLUMN BY COLUMN -- the leftmost byte
 * column first, rows 0 to 191 down it -- forty columns for the AUXILIARY
 * plane and then forty for the MAIN one. The 1,024 bytes of screen holes are
 * not in the stream: they are not on the screen either, so nothing writes
 * them. Read off the ten pictures on the original disks, every one of which
 * decodes to exactly 15,360 bytes and to a coherent image; the count of 0
 * is 128 and not 256, which is what makes them come out exact.
 *
 * A BIG overlay, and its code stops before $2000 (the Makefile links it with
 * a $0500 window so ld65 enforces that) because the picture is about to own
 * $2000-$3FFF. Writing the auxiliary bank costs the ProDOS /RAM volume that
 * lives there; api->ram_format rebuilds it, as the core does after a raw
 * DHGR, and the note says so. */
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);
void ex_aux_move(void);                 /* extasie.s */
void ex_show(void);
void ex_main_bank(void);
void ex_top(void);                      /* the top of a fresh plane */
void __fastcall__ ex_put(unsigned char v);   /* one byte, and one row down */
extern unsigned char ex_col;            /* 0 to 39, then 40: the plane is full */

struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[52]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = { MEDIA_PLUGIN_MAGIC, OVERLAY_BIG | OVERLAY_AUX, plugin_entry,
    {0,0,0}, "Extasie $F2 pictures (Chat Mauve 560/140)" };
#pragma rodata-name (pop)

/* BSS: nothing zeroes it; every one of these is written before it is read. */
static const struct A2fcApi* A;
static FILE* in;
static unsigned char have, at;

/* The next byte of the stream, or 0 once it has run out. `have` is the
 * length of the last read and only a read that came back empty leaves it at
 * zero, so it is also the end-of-file flag and no second one is kept.
 *
 * 255 bytes at a time, not 256: `have` and `at` are bytes, the cheapest
 * arithmetic a 6502 has, and 256 does not fit in one. Cast down, a full read
 * came back as ZERO -- an end of file at the very first byte, so the viewer
 * shipped in 0.7.6 answered "truncated" for every picture and never showed
 * one at all. */
static unsigned char getb(void)
{
    if (at == have) {
        have = (unsigned char)A->fread(A->copy_buf, 1, 255, in);
        at = 0;
        if (!have) return 0;            /* `at` stays 0, so the next call retries */
    }
    return A->copy_buf[at++];
}

/* The whole picture: records until all eighty columns are in, forty to a
 * plane. Returns 0 when the stream ran out first -- the picture is then
 * incomplete and the caller says so rather than showing half of it as if it
 * were whole. ex_put hands the auxiliary plane over on its own (extasie.s),
 * so a record that crosses the boundary is not cut in two here.
 *
 * Separate from plugin_entry so that the host harness runs THIS and not a
 * copy of it. */
static unsigned char picture(void)
{
    unsigned char c, n;

    have = at = 0;
    A->fseek(in, 2, SEEK_SET);          /* past the file's own length */
    ex_main_bank();
    ex_top();
    /* The screen stays where it is while the page is decoded, so a picture
     * lights up only once complete and never column by column. */
    while (ex_col < 40) {
        c = getb();
        if (!have) return 0;
        n = c & 0x7F;
        if (!n) n = 128;
        if (c & 0x80) {
            c = getb();
            while (n--) ex_put(c);
        } else {
            while (n--) ex_put(getb());
        }
    }
    return have != 0;
}

static const char m_bad[]  = "Not an Extasie $F2 picture.";
static const char m_cut[]  = "Picture truncated.";
static const char m_ram[]  = "/RAM rebuilt.";

void __fastcall__ plugin_entry(const struct A2fcApi* a)
{
    unsigned char k;

    A = a;
    /* A directory shown from inside a disk image has no ProDOS path, and
     * a->full is then the image's: fopen fails on it and falls into the same
     * refusal, which saves a guard here. */
    if (a->selected->type != 0xF2) { a->strcpy(a->note, m_bad); return; }
    in = a->fopen(a->full, "rb");
    if (!in) { a->strcpy(a->note, m_bad); return; }
    k = picture();
    a->fclose(in);
    if (!k) { a->ram_format(); a->strcpy(a->note, m_cut); return; }
    ex_show();
    a->media_wait();
    a->strcpy(a->reselect, a->selected->name);
    /* The auxiliary plane is memory the ProDOS /RAM volume uses: once written
     * to, the volume is inconsistent and the next write to it would return
     * anything at all. Rebuilt from scratch through its own driver, as the
     * core does on return from a raw DHGR, and said so. */
    if (a->ram_format()) a->strcpy(a->note, m_ram);
}
