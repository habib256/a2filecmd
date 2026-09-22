/* cpmw.c -- ProDOS files written INTO an Apple II CP/M volume.
 *
 * The mirror of cpm.c, and it wants the same two panels: the image under
 * the cursor of the active panel, a ProDOS directory in the other. That one
 * extracts every file of the volume into the directory; this one puts every
 * file of the directory into the volume, under the same contract -- a name
 * already in the volume is skipped and counted, never overwritten.
 *
 * The skew is still not guessed. plausible() is what says a directory read
 * through a candidate order explains itself, and this refuses to write
 * until one of them does -- which also means it refuses an **empty**
 * volume, and that is not a lapse: with every entry free there is nothing
 * to tell one order from another, and writing through the wrong one would
 * put the file where CP/M will never look for it.
 *
 * The order per file is the one whose interruption costs nothing:
 *
 *   1. The data blocks, written into blocks no live entry claims. Nothing
 *      in the directory names them, so the volume does not know they
 *      exist. Each 256-byte sector is read back, and so is the other half
 *      of the ProDOS block it shares -- a CP/M sector is half a block, and
 *      a read-modify-write that lost the twin would eat a neighbouring
 *      file.
 *   2. The directory entry, one 32-byte slot in one sector, one write.
 *      That write is the instant the file exists.
 *
 * A cut before 2 leaves the volume exactly as it was: the blocks written to
 * were free and stay free. There is no bitmap in CP/M -- what is in use is
 * whatever the live entries claim -- so an entry is the only thing that
 * makes a block belong to anyone.
 *
 * **One extent, so 16 KB at most, and the reason is the window.** A longer
 * file needs one directory entry per 16 KB. The danger is not the order:
 * CP/M puts no ordering requirement on extents, so writing them from 0
 * upwards would leave, after a cut, a run of extents 0..k and a file that
 * reads as a clean truncation. What does not fit is the code -- finding a
 * free slot per extent and looping the data across them -- in an overlay
 * that has a hundred-odd bytes left. So a bigger file is skipped, and the
 * roadmap carries the measurement rather than a story about safety.
 *
 * There is no date here and there is nothing to write: a CP/M 2.2
 * directory entry has no date field at all (stamps came later, with CP/M 3
 * and DateStamper), so unlike a UCSD entry there is nothing to carry over
 * from the ProDOS one.
 *
 * A name is the CP/M eight-and-three: the ProDOS name up to the last
 * period is the name, what follows is the type, both upper case. A name
 * that does not fit, or carries a character CP/M keeps for itself, is
 * skipped and counted rather than mangled into something else.
 */
#define UTIL_STUBS
#define UTIL_VOLUME
#define UTIL_WRITE
#define IMAGEIO_WRITE
#define IMAGEIO_NODEVICE

#include "util.h"
#include <string.h>
#include "imageio.h"
#include "cpm_fs.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};
#ifndef PLUGIN_HOST
#pragma rodata-name(push, "OVLHDR")
#endif
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0, 0, 0,
    "Apple CP/M volume: put the files opposite into it"
};
#ifndef PLUGIN_HOST
#pragma rodata-name(pop)
#endif

#define MAX_BYTES 16384U                /* one extent */

/* The entry being built; its name field IS the CP/M name, written there
 * and compared from there. A buffer of its own cost eleven bytes and a
 * copy, and the window had none to spare. */
static unsigned char newent[ENTRY];
#define cname (newent + 1)
static unsigned char put, skipped, stopped;
static unsigned int nth;
static FILE* src_file;
#define source_path a.other_full

/* One 256-byte CP/M sector written back where cpm_sector would read it,
 * and read back with the twin it shares its ProDOS block with. */
/* `twin` is 256 bytes of scratch the caller is not using at that instant:
 * the data loop lends the directory cache, the directory write lends the
 * sector buffer. A buffer of its own overflowed the window. */
static unsigned char cpm_write(unsigned int logical, const unsigned char* in,
                               unsigned char* twin)
{
    unsigned char p = SKEW[skew][logical & 15], k;
    unsigned char *ours, *mate;
    unsigned int blk;
    k = (p == 0 || p == 15) ? p : 15 - p;
    blk = (RESERVED + (logical >> 4)) * 8 + (k >> 1);
    if (!source_read(&src, blk, buf)) return 0;
    ours = buf + ((k & 1) ? 256 : 0);
    mate = buf + ((k & 1) ? 0 : 256);
    RF(memcpy)(twin, mate, 256);
    RF(memcpy)(ours, in, 256);
    if (!source_write(&src, blk, buf) || !source_read(&src, blk, buf)) return 0;
    return !memcmp(ours, in, 256) && !memcmp(mate, twin, 256);
}

/* A CP/M name into `cname`: what precedes the last period is the name
 * (eight at most), what follows is the type (three at most), both upper
 * case and space padded. 0 when the ProDOS name cannot be one -- a second
 * period, a character CP/M keeps for itself, or simply too long. */
static unsigned char cpm_name(const char* s)
{
    unsigned char i, n, k, c;
    unsigned char dot = 0xFF, len = (unsigned char)RF(strlen)(s);
    a.memset(cname, ' ', 11);
    for (i = 0; i < len; ++i) if (s[i] == '.') dot = i;
    n = (dot == 0xFF) ? len : dot;
    if (!n || n > 8) return 0;
    if (dot != 0xFF && (unsigned char)(len - dot - 1) > 3) return 0;
    for (i = 0; i < len; ++i) {
        if (i == dot) continue;
        c = (unsigned char)s[i];
        if (c >= 'a' && c <= 'z') c -= 32;
        if (c <= ' ' || c > '~' || c == '.' || c == ',' || c == ':' || c == ';' ||
            c == '=' || c == '?' || c == '*' || c == '[' || c == ']' ||
            c == '<' || c == '>' || c == '/' || c == '\\') return 0;
        k = (i < n) ? i : (unsigned char)(8 + i - dot - 1);
        cname[k] = c;
    }
    return 1;
}

/* One pass over the directory: 1 when the name is already there, 0 with
 * `slot` on the first free entry (0xFF when the directory is full). Two
 * passes -- one for the name, one for the slot -- read the same sixty-four
 * entries twice and cost the window forty bytes it did not have. */
static unsigned char slot;
static unsigned char survey(void)
{
    unsigned char i, j;
    const unsigned char* e;
    slot = 0xFF;
    for (i = 0; i < ENTRIES; ++i) {
        e = entry_at(i);
        if (!e) return 1;                       /* unreadable: treat as taken */
        if (!live(e)) { if (slot == 0xFF) slot = i; continue; }
        for (j = 0; j < 11; ++j) if ((e[1 + j] & 127) != cname[j]) break;
        if (j == 11) return 1;
    }
    return 0;
}

/* The first block no live entry claims, past the directory, or 0. */
static unsigned char free_block(void)
{
    unsigned char b;
    for (b = DIR_BLOCKS; b < BLOCKS; ++b)
        if (!(claimed[b >> 3] & (1 << (b & 7)))) return b;
    return 0;
}

/* One ProDOS file into the volume. 1 done (or skipped), 0 stopped. */
static unsigned char one(const char* name, unsigned long size)
{
    unsigned int records, left, n;
    unsigned char blocks, b, i, l;

    a.memset(newent, 0, ENTRY);
    /* 0 redraws: the name shows while the directory is searched for it,
     * skipped files included -- `name` is the same buffer for every one */
    a.progress_bar(name, 0, 1);
    if (!size || size > MAX_BYTES || !cpm_name(name)) { ++skipped; return 1; }
    if (survey()) { ++skipped; return 1; }
    if (slot == 0xFF) { note("No room left in the volume."); return 0; }
    blocks = (unsigned char)((size + 1023) >> 10);
    records = (unsigned int)((size + 127) >> 7);
    newent[15] = (unsigned char)records;        /* RC; EX, S1 and S2 stay 0 */

    if (!join(source_path, other->path, name)) { ++skipped; return 1; }
    src_file = RF(fopen)(source_path, "rb");
    if (!src_file) { note("Cannot read a file opposite."); return 0; }
    left = (unsigned int)size;
    for (i = 0; i < blocks; ++i) {
        b = free_block();
        if (!b) { note("No room left in the volume."); goto bad; }
        claimed[b >> 3] |= 1 << (b & 7);        /* ours from here, in memory */
        newent[16 + i] = b;
        for (l = 0; l < 4; ++l) {
            n = left > 256 ? 256 : left;
            a.memset(sec, 0x1A, 256);           /* CP/M pads with EOF */
            if (n && RF(fread)(sec, 1, n, src_file) != n) {
                note("Cannot read a file opposite."); goto bad;
            }
            if (stop()) { note("Write failed; the volume is whole."); goto bad; }
            /* the directory cache is idle here: it is the twin buffer */
            if (!cpm_write((unsigned int)b * 4 + l, sec, dsec)) {
                note("Write failed; the volume is whole."); goto bad;
            }
            left -= n;
        }
        a.progress_bar(name, i + 1, blocks);
    }
    RF(fclose)(src_file); src_file = 0;
    dsec_at = 0xFF;                             /* it was the twin buffer */

    /* Nothing above is visible: no entry names those blocks. The slot is
     * one write, and it is the instant the file exists. */
    { unsigned char* e = entry_at(slot);
      if (!e) { note("Cannot read the directory."); return 0; }
        RF(memcpy)(e, newent, ENTRY);
      if (!cpm_write(slot >> 3, dsec, sec)) {
          dsec_at = 0xFF;
          note("Entry not written; the volume is whole.");
          return 0;
      }
    }
    ++put;
    return 1;
bad:
    if (src_file) { RF(fclose)(src_file); src_file = 0; }
    return 0;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    init(api);
    put = skipped = stopped = 0; src_file = 0; src.file = 0;
    if (pan->fs || !a.full[0] || !a.selected->name[0] || a.selected->type == 0x0F) {
        note("Disk image here, ProDOS folder opposite.");
        return;
    }
    if (!other->path[0] || other->fs) {
        note("Disk image here, ProDOS folder opposite.");
        return;
    }
    RF(strcpy)(src.path, a.full);
    if (!image_open(&src)) { note("Not a disk image this can open."); return; }
    if (image_readonly) { note("The image is read-only."); goto done; }
    if (src.blocks < (RESERVED + 32) * 8) { note("Not a CP/M volume this can read."); goto done; }
    for (skew = 0; skew < SKEWS; ++skew)
        if (plausible()) break;
    if (skew == SKEWS) { note("Not a CP/M volume this can read."); goto done; }

    a.sprintf(a.note, "Put the files opposite into %s?", a.selected->name);
    if (!RF(confirm)(a.note)) goto done;
    /* The image may have been swapped while the question waited: read the
     * directory again, and with it the blocks in use. */
    if (!plausible()) { note("Image changed; nothing done."); goto done; }

    /* One entry per pass, the directory closed before a source is opened:
     * the image, a directory and a source make three files at once, and
     * ProDOS runs out of buffers. */
    for (nth = 0; ; ++nth) {
        unsigned int k;
        if (!a.dir_open(other->path)) { note("Cannot read the other panel."); goto done; }
        for (k = 0; k <= nth; ++k) if (!a.dir_next()) break;
        a.dir_close();
        if (k <= nth) break;
        if (a.dir_entry->type == 0x0F) continue;
        if (!join(source_path, other->path, a.dir_entry->name) ||
            !a.strcmp(source_path, a.full)) { ++skipped; continue; }
        if (!one(a.dir_entry->name, a.dir_entry->size)) { stopped = 1; break; }
    }
    if (stopped) goto done;
    a.sprintf(a.note, "%u put, %u skipped (name taken or unusable).", put, skipped);
done:
    if (src_file) RF(fclose)(src_file);
    source_close(&src);
}
