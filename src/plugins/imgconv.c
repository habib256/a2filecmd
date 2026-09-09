/* imgconv.c -- convert a disk image from one container to another:
 * .PO/.HDV (ProDOS block order), .DSK/.DO (DOS 3.3 sector order) and .2MG
 * (a 64-byte 2IMG header over ProDOS order). The same blocks, laid out
 * differently: nothing of the file system inside is read or touched.
 *
 * From the ! menu, on the selected image of the active panel. One key
 * picks the target container (P, D, 2); the result is written into the
 * OTHER panel's directory, under the same base name (cut so the ProDOS
 * name stays within 15 characters) with the new suffix, as a $06 BIN of
 * auxtype $0000.
 *
 * A big overlay for two reasons: the thirty-odd calls through the service
 * table cost cc65 some 30 bytes each, and above all the file must stay
 * under 5,376 bytes so that the code stops before $3000 and leaves the
 * whole 4 KB page there free. That page holds one DOS 3.3 track (16
 * sectors of 256 bytes = 8 ProDOS blocks): a .DSK is produced a track at a
 * time and written sequentially, which spares the output file any fseek --
 * the halves of a block land on two sectors that are not adjacent, so a
 * block-by-block writer would have to seek backwards in a file it is
 * creating. Reading is sequential too, except from a .DSK, where each half
 * block is fetched by its sector.
 *
 * Being big, the core re-reads and redraws both panels on return (clrscr
 * included): the last word goes through api->note, never message(). */
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
    "Convert a disk image: .DSK/.DO, .PO, .2MG"
};
#pragma rodata-name (pop)

#pragma static-locals (on)

/* The scratch page: one DOS 3.3 track, 16 sectors of 256 bytes. Free only
 * because this file stops before $3000 (the Makefile checks the window,
 * not this; keep the file under 5,376 bytes). */
#define TRACK ((unsigned char*)0x3000)
#define KBD   ((unsigned char*)0xC000)
#define STROBE ((unsigned char*)0xC010)

/* The containers. 0 and 2 hold ProDOS blocks in order (2 behind a header),
 * 1 holds them in DOS 3.3 sector order. */
#define K_PO  0
#define K_DSK 1
#define K_2MG 2

/* ProDOS block b of a track occupies these two physical sectors (low half
 * then high half): the table of tools/po2dsk.py, flattened to
 * [(b & 7) * 2 + half], the IMG_SECT of the core. */
static const unsigned char SECT[16] = {
    0x0, 0xE, 0xD, 0xC, 0xB, 0xA, 0x9, 0x8, 0x7, 0x6, 0x5, 0x4, 0x3, 0x2, 0x1, 0xF
};
static const char s_po[]  = ".PO";
static const char s_dsk[] = ".DSK";
static const char s_2mg[] = ".2MG";
static const char s_do[]  = ".DO";
static const char s_hdv[] = ".HDV";
static const char* const SUF[3] = { s_po, s_dsk, s_2mg };

static const char m_pick[]   = "Select a .PO, .HDV, .DSK, .DO or .2MG image.";
static const char m_keys[]   = "Convert to P) .PO, D) .DSK, 2) .2MG, ESC to cancel";
static const char m_same[]   = "The image is already in that format.";
static const char m_other[]  = "Other panel: same directory, an image, or not ProDOS.";
static const char m_blocks[] = "Not a whole number of 512-byte blocks.";
static const char m_track[]  = "A .DSK needs whole tracks: a multiple of 8 blocks.";
static const char m_2mg[]    = "Not a ProDOS-order 2IMG file.";
static const char m_over[]   = "Overwrite it in the other panel?";
static const char m_stop[]   = "Aborted, %s removed.";
static const char m_done[]   = "%s -> %s, %u blocks";
static const char m_fail[]   = "%s failed.";
static const char f_path[]   = "%s/%s";

/* Nothing zeroes the BSS: each of these is written before it is read. */
static struct A2fcApi T;
static FILE* in;
static FILE* out;
static unsigned char* buf;              /* api->copy_buf: one ProDOS block */
static unsigned long sbase;             /* offset of the data in the source (.2MG) */
static unsigned int blocks, n;
static unsigned char skind, dkind, cut;
static char nname[NAME_LEN];            /* the name of the result */

/* Recognises the container by the suffix; sets skind and cut (how many
 * characters of the name the suffix takes). 0: not an image we know. */
static unsigned char __fastcall__ classify(const char* s)
{
    unsigned char len = T.strlen(s);
    if (len > 4) {
        if (!T.strcmp(s + len - 4, s_dsk)) { skind = K_DSK; cut = 4; return 1; }
        if (!T.strcmp(s + len - 4, s_2mg)) { skind = K_2MG; cut = 4; return 1; }
        if (!T.strcmp(s + len - 4, s_hdv)) { skind = K_PO;  cut = 4; return 1; }
    }
    if (len > 3) {
        if (!T.strcmp(s + len - 3, s_po)) { skind = K_PO;  cut = 3; return 1; }
        if (!T.strcmp(s + len - 3, s_do)) { skind = K_DSK; cut = 3; return 1; }
    }
    return 0;
}

/* Reads ProDOS block `n` of the source into buf. A .PO, a .HDV and the
 * data of a .2MG are read straight through (the loop walks them in order);
 * a .DSK is seeked sector by sector. */
static unsigned char read_block(void)
{
    unsigned char i;
    long off;
    if (skind != K_DSK)
        return T.fread(buf, 1, 512, in) == 512;
    i = (unsigned char)(n & 7) << 1;
    off = sbase + ((long)(n >> 3) << 12);
    T.fseek(in, off + ((long)SECT[i] << 8), SEEK_SET);
    if (T.fread(buf, 1, 256, in) != 256) return 0;
    T.fseek(in, off + ((long)SECT[i + 1] << 8), SEEK_SET);
    return T.fread(buf + 256, 1, 256, in) == 256;
}

/* Writes what read_block brought: straight out, or into the track page,
 * flushed whole every eighth block. */
static unsigned char write_block(void)
{
    unsigned char i;
    if (dkind != K_DSK)
        return T.fwrite(buf, 1, 512, out) == 512;
    i = (unsigned char)(n & 7) << 1;
    T.memcpy(TRACK + ((unsigned int)SECT[i] << 8), buf, 256);
    T.memcpy(TRACK + ((unsigned int)SECT[i + 1] << 8), buf + 256, 256);
    if ((n & 7) != 7) return 1;
    return T.fwrite(TRACK, 1, 4096, out) == 4096;
}

/* The 64-byte 2IMG header of tools/po22mg.py, byte for byte: creator
 * "A2FC", header 64, version 1, format 1 (ProDOS order), no flag, the
 * block count, the data at 64 and its length, nothing else. */
static unsigned char write_2mg_header(void)
{
    unsigned long len = (unsigned long)blocks << 9;
    T.memset(TRACK, 0, 64);
    T.memcpy(TRACK, "2IMG", 4);
    T.memcpy(TRACK + 4, "A2FC", 4);
    TRACK[0x08] = 64;                   /* size of the header */
    TRACK[0x0A] = 1;                    /* version */
    TRACK[0x0C] = 1;                    /* format: ProDOS block order */
    TRACK[0x14] = (unsigned char)blocks;
    TRACK[0x15] = (unsigned char)(blocks >> 8);
    TRACK[0x18] = 64;                   /* offset of the data */
    TRACK[0x1C] = (unsigned char)len;
    TRACK[0x1D] = (unsigned char)(len >> 8);
    TRACK[0x1E] = (unsigned char)(len >> 16);
    TRACK[0x1F] = (unsigned char)(len >> 24);
    return T.fwrite(TRACK, 1, 64, out) == 64;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Panel* pan;
    const struct Panel* oth;
    const struct Entry* e;
    const char* what;
    const char* suf;
    char* target;
    unsigned char k;

    api->memcpy(&T, api, sizeof T);
    buf = T.copy_buf;
    pan = T.panels;
    oth = pan + 1;
    if (*T.active) { pan = oth; oth = T.panels; }
    e = T.selected;
    target = T.other_full;

    if (!e->name[0] || e->type == 0x0F || !pan->path[0] || pan->fs || !classify(e->name)) {
        T.strcpy(T.note, m_pick);
        return;
    }

    /* The target container, one key. */
    T.message(m_keys);
    for (;;) {
        k = T.cgetc();
        if (k == KEY_ESC) return;
        if (k >= 'a') k -= 32;
        if (k == 'P') { dkind = K_PO;  break; }
        if (k == 'D') { dkind = K_DSK; break; }
        if (k == '2') { dkind = K_2MG; break; }
    }
    if (dkind == skind) { T.strcpy(T.note, m_same); return; }
    if (!oth->path[0] || oth->fs || !T.strcmp(oth->path, pan->path)) {
        T.strcpy(T.note, m_other);
        return;
    }

    /* The source, and how many blocks it holds. */
    what = "Open";
    in = T.fopen(T.full, "rb");
    if (!in) goto err;
    if (skind == K_2MG) {
        if (T.fread(buf, 1, 64, in) != 64 || buf[0] != '2' || buf[1] != 'I'
            || buf[2] != 'M' || buf[3] != 'G' || buf[0x0C] != 1) {
            T.fclose(in);
            T.strcpy(T.note, m_2mg);
            return;
        }
        blocks = buf[0x14] | ((unsigned int)buf[0x15] << 8);
        sbase = *(unsigned long*)(buf + 0x18);
        T.fseek(in, sbase, SEEK_SET);
    } else {
        if (e->size & 511) { T.fclose(in); T.strcpy(T.note, m_blocks); return; }
        blocks = (unsigned int)(e->size >> 9);
        sbase = 0;
    }
    if (!blocks || ((blocks & 7) && (dkind == K_DSK || skind == K_DSK))) {
        T.fclose(in);
        T.strcpy(T.note, blocks ? m_track : m_blocks);
        return;
    }

    /* The name of the result: the base, cut so that name + suffix stays
     * within the 15 characters of a ProDOS name. */
    suf = SUF[dkind];
    n = dkind ? 11 : 12;                /* 15 less the suffix: ".PO" 3, the others 4 */
    k = T.strlen(e->name) - cut;
    if (k > (unsigned char)n) k = (unsigned char)n;
    T.memcpy(nname, e->name, k);
    T.strcpy(nname + k, suf);
    T.sprintf(target, f_path, oth->path, nname);

    out = T.fopen(target, "rb");
    if (out) {
        T.fclose(out);
        if (!T.confirm(m_over)) { T.fclose(in); return; }
    }
    T.remove(target);
    *T.filetype = 0x06;
    *T.auxtype = 0;
    what = "Create";
    out = T.fopen(target, "wb");
    if (!out) { T.fclose(in); goto err; }

    what = "Write";
    if (dkind == K_2MG && !write_2mg_header()) goto errrm;
    what = "Read";
    for (n = 0; n < blocks; ++n) {
        if (!(n & 7)) {
            T.progress_bar(nname, n, blocks);
            if (*KBD == (KEY_ESC | 0x80)) {
                *STROBE = 0;
                T.fclose(in);
                T.fclose(out);
                T.remove(target);
                T.sprintf(T.note, m_stop, nname);
                return;
            }
        }
        if (!read_block()) goto errrm;
        if (!write_block()) { what = "Write"; goto errrm; }
    }
    T.fclose(in);
    what = "Write";
    if (T.fclose(out)) goto errrm2;

    T.strcpy(T.reselect, e->name);
    T.sprintf(T.note, m_done, e->name, nname, blocks);
    return;

errrm:
    T.fclose(in);
    T.fclose(out);
errrm2:
    T.remove(target);
err:
    T.sprintf(T.note, m_fail, what);    /* report_error would not survive the redraw */
}
