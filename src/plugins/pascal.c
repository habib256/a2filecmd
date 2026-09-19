/* pascal.c -- an Apple Pascal (UCSD) volume read out of a disk image, and
 * its files extracted into the ProDOS directory of the other panel.
 *
 * From the ! menu, with the image under the cursor and a ProDOS directory
 * opposite. A Pascal volume is the one foreign filesystem that fits in an
 * overlay's window without a second thought: two boot blocks, a flat
 * directory of four blocks at block 2, and every file one contiguous run of
 * blocks. No extents, no allocation bitmap, no subdirectories.
 *
 * The directory is 78 entries of 26 bytes. The first describes the volume
 * (its name, its size in blocks, how many files follow); each of the others
 * gives a file's first block, the block after its last, its kind, its name
 * and how many bytes of that last block it uses -- so its length is
 * (last - first - 1) * 512 + used. tools/pascal_ref.py is the reference,
 * and it says what each field holds.
 *
 * Read only: nothing is written to the image, ever. What is written is the
 * extracted file, under the one contract of the file services -- created
 * only under a free name (a taken one is skipped and counted), written,
 * closed, read back against the image a second time, and removed if
 * anything fails.
 *
 * What it does not do, and does not pretend to: a .TEXT file comes out as
 * it lies on the disk, its 1,024-byte header and its page padding
 * included. Turning that format into plain text (a run of leading spaces is
 * $10 then 32 plus the count) is a conversion, not a reading, and it
 * belongs with the other converters.
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
    "Apple Pascal volume: list and extract its files"
};
#pragma rodata-name (pop)

#pragma static-locals (on)

#define DIR_BLOCK 2
#define DIR_BLOCKS 4
#define ENTRY 26
#define MAX_FILES 77

static struct Source src;
/* One directory entry at a time, not the whole directory: four blocks would
 * have left this overlay eighteen bytes of room, and the next change to it
 * would not have linked. An entry is twenty-six bytes and the blocks are
 * five hundred and twelve, so one entry in nineteen straddles two of them;
 * entry_at() reads the second when it has to. */
static unsigned char ent[ENTRY];
static unsigned char count;             /* files in the directory */
static unsigned int vblocks;            /* blocks the volume claims */
static char name[16], dest[PATH_LEN + 1];
/* The file read back, half a block at a time. Not `dest`: that one is a
 * path of sixty-five bytes, and a block is five hundred and twelve. */
static unsigned char back[256];
static unsigned char made, skipped, kept, bad;

/* The ProDOS type each UCSD kind becomes. ProDOS has one for code, text and
 * data; the rest arrive untyped, which is what they are to it. */
static unsigned char prodos_type(unsigned char kind)
{
    if (kind == 2) return 0x02;         /* PCD */
    if (kind == 3) return 0x03;         /* PTX */
    if (kind == 5) return 0x05;         /* PDA */
    return 0;
}

/* A ProDOS name from n bytes of a Pascal name: upper case, anything but a
 * letter, a digit or a period becomes a period, a name must start on a
 * letter, fifteen characters at most. */
static void set_name(const unsigned char* s, unsigned char n)
{
    unsigned char k = 0, c;
    if (n > 15) n = 15;
    while (n--) {
        c = *s++;
        if (c >= 'a' && c <= 'z') c -= 32;
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.')) c = '.';
        if (!k && !(c >= 'A' && c <= 'Z')) c = 'X';
        name[k++] = c;
    }
    name[k] = 0;
}

static unsigned int word(const unsigned char* p) { return p[0] | ((unsigned int)p[1] << 8); }

/* Entry i of the directory into `ent`, the second block read when the entry
 * straddles two. `buf` is free between files: it holds a data block only
 * while one is being copied. */
static unsigned char entry_at(unsigned char i)
{
    unsigned int off = (unsigned int)i * ENTRY, k = off & 511, part;
    if (!source_read(&src, DIR_BLOCK + (off >> 9), buf)) return 0;
    part = 512 - k;
    if (part > ENTRY) part = ENTRY;
    memcpy(ent, buf + k, part);
    if (part < ENTRY) {
        if (!source_read(&src, DIR_BLOCK + (off >> 9) + 1, buf)) return 0;
        memcpy(ent + part, buf, ENTRY - part);
    }
    return 1;
}

/* The volume directory, read and explained, or 0. Everything the entries
 * claim is checked against the image before a single byte is extracted: a
 * directory we cannot explain is not a directory we read files from. */
static unsigned char read_dir(void)
{
    unsigned char i, n;
    unsigned int first, last, prev = DIR_BLOCK + DIR_BLOCKS, used;
    if (!entry_at(0)) return 0;
    if (word(ent) || word(ent + 2) != DIR_BLOCK + DIR_BLOCKS || word(ent + 4)) return 0;
    n = ent[6];
    if (!n || n > 7) return 0;
    for (i = 0; i < n; ++i) {
        unsigned char c = ent[7 + i];
        if (c <= 32 || c >= 127 || c == '$' || c == '=' || c == '?' || c == ',') return 0;
    }
    vblocks = word(ent + 14);
    if (word(ent + 16) > MAX_FILES || !vblocks || vblocks > src.blocks) return 0;
    count = (unsigned char)word(ent + 16);
    for (i = 1; i <= count; ++i) {
        if (!entry_at(i)) return 0;
        first = word(ent);
        last = word(ent + 2);
        used = word(ent + 22);
        n = ent[6];
        if (!n || n > 15) return 0;
        if (last <= first || last > vblocks || first < prev) return 0;
        if (!used || used > 512) return 0;
        prev = last;
    }
    return 1;
}

/* One file's bytes: written to `out` (verify 0) or compared with the file
 * read back (verify 1). The image is read a second time either way, so what
 * is compared is the disk against the disk, not a buffer against itself. */
static unsigned char copy_file(unsigned int first, unsigned int last,
                               unsigned int used, FILE* out, unsigned char verify)
{
    unsigned int b, n, k, part;
    for (b = first; b < last; ++b) {
        n = (b + 1 == last) ? used : 512;
        if (!source_read(&src, b, buf)) return 0;
        if (verify) {
            for (k = 0; k < n; k += part) {
                part = n - k > 256 ? 256 : n - k;
                if (RF(fread)(back, 1, part, out) != part ||
                    memcmp(back, buf + k, part)) return 0;
            }
        } else if (RF(fwrite)(buf, 1, n, out) != n || ferror(out)) return 0;
        a.progress_bar(name, b - first, last - first);
        if (stop()) return 0;
    }
    if (verify && RF(fread)(back, 1, 1, out)) return 0;   /* it must end there */
    return 1;
}

/* One file created, filled, closed and read back. 0 stops the extraction. */
static unsigned char one(unsigned char i)
{
    FILE* out;
    unsigned char ok;
    unsigned int first, last, used;
    if (!entry_at(i)) { bad = 1; return 0; }
    first = word(ent); last = word(ent + 2); used = word(ent + 22);
    set_name(ent + 7, ent[6]);
    if (!name[0] || !join(dest, other->path, name) ||
        newfile(dest, prodos_type(ent[4] & 15), 0, 1)) {
        ++skipped;
        return 1;
    }
    out = RF(fopen)(dest, "wb");
    ok = out != 0 && copy_file(first, last, used, out, 0);
    if (out && RF(fclose)(out)) ok = 0;
    if (ok) {
        out = RF(fopen)(dest, "rb");
        ok = out != 0 && copy_file(first, last, used, out, 1);
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
    unsigned char i;
    init(api);
    made = skipped = kept = bad = 0;
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
    if (!read_dir()) {
        source_close(&src);
        note("Not an Apple Pascal volume.");
        return;
    }
    for (i = 1; i <= count; ++i)
        if (!one(i)) break;
    source_close(&src);
    if (kept) return;                    /* discard()'s note is the last word */
    a.sprintf(a.note, "%u extracted, %u skipped (name taken)%s", made, skipped,
              bad ? (cancelled ? "; stopped." : "; failed, stopped.") : ".");
}
