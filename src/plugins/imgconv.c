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
 * Output is sequential in every format. To produce DOS sector order we
 * seek each sector in the ProDOS-order source, instead of reserving a 4 KB
 * track in main RAM. The resident's 512-byte copy buffer holds each sector
 * and the temporary 2IMG header. This leaves the overlay window available
 * for validation without touching auxiliary RAM or the ProDOS RAM disk.
 *
 * Being big, the core re-reads and redraws both panels on return (clrscr
 * included): the last word goes through api->note, never message(). */
#include "../a2fc_plugin.h"
#include <stdint.h>

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

/* Header construction/inspection borrows the resident copy buffer; no
 * fixed-address track buffer overlaps this overlay's code or BSS. */
#ifndef TRACK
#define TRACK buf
#endif
#ifndef KBD
#define KBD   ((unsigned char*)0xC000)
#define STROBE ((unsigned char*)0xC010)
#endif

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

static const char m_pick[]   = "Select a .PO/.HDV/.DSK/.DO/.2MG image.";
static const char m_keys[]   = "\1Convert to P) .PO, D) .DSK, 2) .2MG, ESC cancels";
static const char m_same[]   = "Image already in that format.";
static const char m_other[]  = "Other panel: same directory or not ProDOS.";
static const char m_blocks[] = "Partial 512-byte block.";
static const char m_track[]  = "DSK needs whole tracks (8-block multiples).";
static const char m_2mg[]    = "Not a ProDOS-order 2IMG file.";
static const char m_over[]   = "Overwrite destination?";
static const char m_stop[]   = "Aborted, %s removed.";
static const char m_done[]   = "%s -> %s, %u blocks";
static const char m_fail[]   = "%s failed.";
static const char f_path[]   = "%s/%s";

/* Nothing zeroes the BSS: each of these is written before it is read. */
static struct A2fcApi T;
#define SERVICE_API T
#include "service_stubs.h"
#define replace_backup ((char*)T.copy_buf + 256)
#include "replace.h"
#define final_path T.note /* idle until the final result is reported */
static unsigned char replacing;
static struct { unsigned char n; unsigned char* path; unsigned char access,type;
    unsigned int aux; unsigned char storage; unsigned int date,time; } create;
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
    unsigned char len = RF(strlen)(s);
    if (len > 4) {
        if (!RF(strcmp)(s + len - 4, s_dsk)) { skind = K_DSK; cut = 4; return 1; }
        if (!RF(strcmp)(s + len - 4, s_2mg)) { skind = K_2MG; cut = 4; return 1; }
        if (!RF(strcmp)(s + len - 4, s_hdv)) { skind = K_PO;  cut = 4; return 1; }
    }
    if (len > 3) {
        if (!RF(strcmp)(s + len - 3, s_po)) { skind = K_PO;  cut = 3; return 1; }
        if (!RF(strcmp)(s + len - 3, s_do)) { skind = K_DSK; cut = 3; return 1; }
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
        return RF(fread)(buf, 1, 512, in) == 512;
    i = (unsigned char)(n & 7) << 1;
    off = (long)(n >> 3) << 12;          /* raw DSK data always starts at zero */
    if (RF(fseek)(in, off + ((long)SECT[i] << 8), SEEK_SET)) return 0;
    if (RF(fread)(buf, 1, 256, in) != 256) return 0;
    if (RF(fseek)(in, off + ((long)SECT[i + 1] << 8), SEEK_SET)) return 0;
    return RF(fread)(buf + 256, 1, 256, in) == 256;
}

/* Write sequential destination bytes. PO/2MG consume the block already
 * read; DSK fetches its two physical sectors from the source first. DSK to
 * DSK is refused before opening the destination, so this source is always
 * PO or 2MG and its data offset is known. Every seek/read/write is checked. */
static unsigned char write_block(void)
{
    unsigned char half, sector, i;
    long off;
    if (dkind != K_DSK)
        return RF(fwrite)(buf, 1, 512, out) == 512;
    off = sbase + ((long)(n >> 3) << 12);
    sector = (unsigned char)(n & 7) << 1;
    for (half = 0; half < 2; ++half) {
        for (i = 0; SECT[i] != sector + half; ++i) {}
        if (RF(fseek)(in, off + ((long)i << 8), SEEK_SET) ||
            RF(fread)(buf, 1, 256, in) != 256 ||
            RF(fwrite)(buf, 1, 256, out) != 256) return 0;
    }
    return 1;
}

/* The 64-byte 2IMG header of tools/po22mg.py, byte for byte: creator
 * "A2FC", header 64, version 1, format 1 (ProDOS order), no flag, the
 * block count, the data at 64 and its length, nothing else. */
static void make_2mg_header(void)
{
    unsigned long len = (unsigned long)blocks << 9;
    T.memset(TRACK, 0, 64);
    RF(memcpy)(TRACK, "2IMG", 4);
    RF(memcpy)(TRACK + 4, "A2FC", 4);
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
}

/* Compare complete logical blocks after closing the output, including its
 * generated header and exact EOF. The original destination is still named
 * normally here. Only a successful verification may install its replacement. */
static unsigned char check[512];
static unsigned char verify_output(const char* path)
{
    unsigned char bad = 0, half, sector;
    unsigned int i;
    long off;
    in = RF(fopen)(T.full, "rb");
    out = RF(fopen)(path, "rb");
    if (!in || !out) bad = 1;
    if (!bad && RF(fseek)(in, sbase, SEEK_SET)) bad = 1;
    if (!bad && dkind == K_2MG) {
        make_2mg_header();
        if (RF(fread)(check, 1, 64, out) != 64) bad = 1;
        else for (i = 0; i < 64; ++i) if (check[i] != TRACK[i]) bad = 1;
    }
    for (n = 0; n < blocks && !bad; ++n) {
        if (*KBD == (KEY_ESC | 0x80)) { *STROBE = 0; bad = 1; break; }
        if (!read_block()) { bad = 1; break; }
        if (dkind == K_DSK) {
            sector = (unsigned char)(n & 7) << 1;
            off = (long)(n >> 3) << 12;
            for (half = 0; half < 2; ++half) {
                if (RF(fseek)(out, off + ((long)SECT[sector + half] << 8), SEEK_SET) ||
                    RF(fread)(check + (unsigned int)half * 256, 1, 256, out) != 256) {
                    bad = 1; break;
                }
            }
        } else if (RF(fread)(check, 1, 512, out) != 512) bad = 1;
        if (!bad) for (i = 0; i < 512; ++i) if (check[i] != buf[i]) { bad = 1; break; }
    }
    /* 2MG source trailers are permitted; raw source tails are not. The
     * final logical block also ends at the final physical DSK sector. */
    if (!bad && ((skind != K_2MG && RF(fread)(buf, 1, 1, in)) ||
                 RF(fread)(check, 1, 1, out))) bad = 1;
    if (in) { if (ferror(in)) bad = 1; if (RF(fclose)(in)) bad = 1; }
    if (out) { if (ferror(out)) bad = 1; if (RF(fclose)(out)) bad = 1; }
    return !bad;
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
        what = m_pick;
        goto note;
    }

    /* The target container, one key. */
    RF(message)(m_keys);
    for (;;) {
        k = T.cgetc();
        if (k == KEY_ESC) return;
        if (k >= 'a') k -= 32;
        if (k == 'P') { dkind = K_PO;  break; }
        if (k == 'D') { dkind = K_DSK; break; }
        if (k == '2') { dkind = K_2MG; break; }
    }
    if (dkind == skind) { what = m_same; goto note; }
    if (!oth->path[0] || oth->fs || !RF(strcmp)(oth->path, pan->path)) {
        what = m_other;
        goto note;
    }

    /* The source, and how many blocks it holds. */
    what = "Open";
    sbase = 0;
    in = RF(fopen)(T.full, "rb");
    if (!in) goto err;
    if (skind == K_2MG) {
        /* The track page is idle while reading the header. Its fixed
         * address also keeps these field checks small on the 6502. */
        if (RF(fread)(TRACK, 1, 64, in) != 64 || TRACK[0] != '2' || TRACK[1] != 'I'
            || TRACK[2] != 'M' || TRACK[3] != 'G' || TRACK[0x0C] != 1
            /* Both fields are 32-bit. Only format 1 and a block count
             * representable by our 16-bit loop are supported. */
            || (TRACK[0x0D] | TRACK[0x0E] | TRACK[0x0F] | TRACK[0x16] | TRACK[0x17]))
            goto bad2mg;
        blocks = TRACK[0x14] | ((unsigned int)TRACK[0x15] << 8);
        sbase = *(uint32_t*)(TRACK + 0x18);
        /* Subtract only after bounding the offset, so a malicious range
         * cannot wrap. Refuse before opening or removing the destination. */
        if (sbase < 64 || sbase > e->size
            || (unsigned long)blocks > ((e->size - sbase) >> 9)) goto bad2mg;
        if (RF(fseek)(in, sbase, SEEK_SET)) {
            RF(fclose)(in);
            what = "Read";
            goto err;
        }
    } else {
        if (e->size & 511) { what = m_blocks; goto badsource; }
        blocks = (unsigned int)(e->size >> 9);
    }
    if (!blocks || ((blocks & 7) && (dkind == K_DSK || skind == K_DSK))) {
        what = blocks ? m_track : m_blocks;
        goto badsource;
    }

    /* The name of the result: the base, cut so that name + suffix stays
     * within the 15 characters of a ProDOS name. */
    suf = SUF[dkind];
    n = dkind ? 11 : 12;                /* 15 less the suffix: ".PO" 3, the others 4 */
    k = RF(strlen)(e->name) - cut;
    if (k > (unsigned char)n) k = (unsigned char)n;
    RF(memcpy)(nname, e->name, k);
    RF(strcpy)(nname + k, suf);
    if (RF(strlen)(oth->path) + RF(strlen)(nname) + 1 >= PATH_LEN) { what = "Path too long"; goto badsource; }
    T.sprintf(target, f_path, oth->path, nname);

    k = replace_info(target);
    replacing = !k;
    if (k && k != 0x46) { what = "Destination check"; goto badsource; }
    if (replacing) {
        if (!RF(confirm)(m_over)) { RF(fclose)(in); return; }
        RF(strcpy)(final_path, target);
        if (RF(strlen)(oth->path) + 13 >= PATH_LEN) { what = "Path too long"; goto badsource; }
        T.sprintf(target, f_path, oth->path, "IMGCONV.TMP");
    }
    *T.filetype = 0x06; *T.auxtype = 0;
    what = "Create";
    T.copy_buf[0] = RF(strlen)(target); RF(strcpy)((char*)T.copy_buf + 1, target);
    create.n = 7; create.path = T.copy_buf; create.access = 0xC3;
    create.type = 6; create.aux = 0; create.storage = 1; create.date = create.time = 0;
    if (RF(mli)(0xC0, &create)) { RF(fclose)(in); goto err; }
    out = RF(fopen)(target, "wb");
    if (!out) { RF(fclose)(in); goto errrm2; }

    what = "Write";
    if (dkind == K_2MG) {
        make_2mg_header();
        if (RF(fwrite)(TRACK, 1, 64, out) != 64) goto errrm;
    }
    what = "Read";
    for (n = 0; n < blocks; ++n) {
        if (!(n & 7)) {
            T.progress_bar(nname, n, blocks);
            if (*KBD == (KEY_ESC | 0x80)) {
                *STROBE = 0;
                RF(fclose)(in);
                RF(fclose)(out);
                RF(remove)(target);
                T.sprintf(T.note, m_stop, nname);
                return;
            }
        }
        if (dkind != K_DSK && !read_block()) goto errrm;
        if (!write_block()) { what = "Write"; goto errrm; }
    }
    k = ferror(in) || ferror(out);
    if (RF(fclose)(in)) k = 1;
    what = "Close";
    if (RF(fclose)(out)) k = 1;
    if (k) goto errrm2;

    what = "Verify";
    if (!verify_output(target)) goto errrm2;

    if (replacing) {
        k = replace_commit(target, final_path);
        if (!k) { RF(strcpy)(T.note, "Recover IMGCONV.TMP / A2FC.BAK."); return; }
        if (k == 2) { RF(strcpy)(T.note, "Converted; A2FC.BAK retained."); return; }
    }
    RF(strcpy)(T.reselect, e->name);
    T.sprintf(T.note, m_done, e->name, nname, blocks);
    return;

errrm:
    RF(fclose)(in);
    RF(fclose)(out);
errrm2:
    RF(remove)(target);
err:
    T.sprintf(T.note, m_fail, what);    /* report_error would not survive the redraw */
    return;
bad2mg:
    what = m_2mg;
badsource:
    RF(fclose)(in);
note:
    RF(strcpy)(T.note, what);
}
