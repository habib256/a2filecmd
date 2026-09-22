/* cpm.c -- an Apple II CP/M volume read out of a disk image, and its files
 * extracted into the ProDOS directory of the other panel.
 *
 * From the ! menu, with the image under the cursor and a ProDOS directory
 * opposite, exactly as PASCAL. Read only: nothing is ever written to the
 * image. What is written follows the one contract of the file services --
 * created only under a free name, written, closed, read back against the
 * image a second time, and removed if anything fails.
 *
 * A 5.25" CP/M disk, from its disk parameter block: blocks of 1,024 bytes,
 * 128 of them, the first three tracks kept for CP/M itself, and the first
 * two blocks of what follows given to a directory of 64 entries of 32
 * bytes. An entry is one extent, 16 KB: a user number, an eight-and-three
 * name whose high bits are attributes, the extent number in EX and S2, the
 * records used in RC, and sixteen block numbers. A longer file has several
 * entries, ordered by EX + 32 * S2, and its length is 128 bytes times
 * (128 * extent + RC) of the last one. tools/cpm_ref.py is the reference.
 *
 * **The skew.** CP/M reads the Apple's 256-byte sectors through an order of
 * its own, and which one is not settled: the published tables disagree and
 * there is no Apple CP/M disk in the sample corpus to read. So this does
 * not guess. It tries each candidate and keeps the one whose directory
 * explains itself -- user numbers and names in range, record counts of at
 * most 128, block numbers inside the disk and claimed once each. A wrong
 * skew turns the directory into noise and fails that test, so the cost of
 * not knowing is a refusal and never a wrong byte. If a disk is refused
 * that CP/M itself reads, its table is the one to add to SKEW below.
 *
 * A big overlay: the core rereads the panels on return.
 */
#define UTIL_STUBS
#define UTIL_CREATE
#define UTIL_DISCARD
#define UTIL_VOLUME

#include "util.h"
#include "imageio.h"
#include <string.h>

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0, 0, 0,
    "Apple CP/M volume: extract its files"
};
#pragma rodata-name (pop)

#pragma static-locals (on)

#include "cpm_fs.h"

static unsigned char done[ENTRIES / 8]; /* entries already extracted */
static char name[16], dest[PATH_LEN + 1];
static unsigned char made, skipped, kept, bad;
static unsigned long fsize;

/* A ProDOS name from a CP/M one: NAME.TYP, upper case, anything else a
 * period, a letter first, fifteen characters at most. */
static void set_name(const unsigned char* e)
{
    unsigned char k = 0, i, c;
    for (i = 1; i < 12; ++i) {
        c = e[i] & 127;
        if (i == 9) {
            if (k && (e[9] & 127) != ' ') name[k++] = '.';
            else if (!k) break;
        }
        if (c == ' ') continue;
        if (c >= 'a' && c <= 'z') c -= 32;
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.')) c = '.';
        if (!k && !(c >= 'A' && c <= 'Z')) c = 'X';
        if (k < 15) name[k++] = c;
    }
    name[k] = 0;
}

/* The entry of `ext` for the file entry `first` names, or 0. */
static unsigned char* extent_at(const unsigned char* first, unsigned int ext)
{
    unsigned char i, user = first[0], want[11], *e;
    memcpy(want, first + 1, 11);
    for (i = 0; i < ENTRIES; ++i) {
        e = entry_at(i);
        if (!e) return 0;
        if (!live(e) || e[0] != user || memcmp(e + 1, want, 11)) continue;
        if (extent_of(e) == ext) return e;
    }
    return 0;
}

/* Marks every entry of this file done, and answers its length in bytes. */
static unsigned long measure(const unsigned char* first)
{
    unsigned char i, user = first[0], want[11], *e;
    unsigned int ext, high = 0;
    unsigned char rc = 0;
    memcpy(want, first + 1, 11);
    for (i = 0; i < ENTRIES; ++i) {
        e = entry_at(i);
        if (!e) return 0;
        if (!live(e) || e[0] != user || memcmp(e + 1, want, 11)) continue;
        done[i >> 3] |= 1 << (i & 7);
        ext = extent_of(e);
        if (ext >= high) { high = ext; rc = e[15]; }
    }
    return ((unsigned long)high * 128 + rc) * 128;
}

/* The file's bytes: written to `out` (verify 0) or compared with what was
 * written (verify 1). The image is read again either way. */
static unsigned char copy_file(const unsigned char* first, FILE* out, unsigned char verify)
{
    unsigned int ext = 0, l;
    unsigned long left = fsize;
    unsigned char j, b, *e;
    while (left) {
        e = extent_at(first, ext);
        if (!e) return 0;
        for (j = 16; j < 32 && left; ++j) {
            b = e[j];
            if (!b) continue;
            /* Every kilobyte, from 0: a pass starts with a fresh bar, the
             * read-back included, whatever the file before this one. */
            a.progress_bar(name, fsize - left, fsize);
            for (l = 0; l < 4 && left; ++l) {
                unsigned int n = left > 256 ? 256 : (unsigned int)left;
                if (!cpm_sector((unsigned int)b * 4 + l, sec)) return 0;
                /* `buf` held the ProDOS block cpm_sector copied out of; it
                 * is free from here, and a sector's worth of read-back has
                 * to live somewhere. */
                if (verify) {
                    if (RF(fread)(buf, 1, n, out) != n || memcmp(buf, sec, n)) return 0;
                } else if (RF(fwrite)(sec, 1, n, out) != n || ferror(out)) return 0;
                left -= n;
            }
            if (stop()) return 0;
        }
        ++ext;
        if (ext > 256) return 0;         /* a file cannot have that many */
    }
    if (verify && RF(fread)(buf, 1, 1, out)) return 0;
    return 1;
}

/* One file created, filled, closed and read back. 0 stops the extraction. */
static unsigned char one(const unsigned char* first)
{
    FILE* out;
    unsigned char ok;
    set_name(first);
    if (!name[0] || !join(dest, other->path, name) || newfile(dest, 0, 0, 1)) {
        ++skipped;
        return 1;
    }
    out = RF(fopen)(dest, "wb");
    ok = out != 0 && copy_file(first, out, 0);
    if (out && RF(fclose)(out)) ok = 0;
    if (ok) {
        out = RF(fopen)(dest, "rb");
        ok = out != 0 && copy_file(first, out, 1);
        if (out && RF(fclose)(out)) ok = 0;
    }
    if (!ok) {
        bad = 1;
        kept = !discard(dest);
        return 0;
    }
    ++made;
    return 1;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char i, saved[ENTRY], *e;
    init(api);
    made = skipped = kept = bad = 0;
    a.memset(done, 0, sizeof done);
    if (pan->fs || !a.full[0] || !a.selected->name[0] || a.selected->type == 0x0F) {
        note("Select a disk image; ProDOS folder opposite.");
        return;
    }
    if (!other->path[0] || other->fs) {
        note("Other panel: open a ProDOS directory.");
        return;
    }
    RF(strcpy)(src.path, a.full);
    if (!image_open(&src)) { note("Not a disk image this can open."); return; }
    if (src.blocks < (RESERVED + 32) * 8) {
        source_close(&src);
        note("Too small to be a CP/M disk.");
        return;
    }
    for (skew = 0; skew < SKEWS; ++skew)
        if (plausible()) break;
    if (skew == SKEWS) {
        source_close(&src);
        note("Not a CP/M volume this can read.");
        return;
    }
    for (i = 0; i < ENTRIES; ++i) {
        e = entry_at(i);
        if (!e) { bad = 1; break; }
        if (!live(e) || (done[i >> 3] & (1 << (i & 7)))) continue;
        /* entry_at's cache moves under the scans below: keep our own copy. */
        memcpy(saved, e, ENTRY);
        fsize = measure(saved);
        if (!fsize) { ++skipped; continue; }   /* an extent with no records */
        if (!one(saved)) break;
    }
    source_close(&src);
    if (kept) return;
    a.sprintf(a.note, "%u extracted, %u skipped (name taken)%s", made, skipped,
              bad ? (cancelled ? "; stopped." : "; failed, stopped.") : ".");
}
