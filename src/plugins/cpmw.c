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
 * The data stays unreferenced until the directory entry is published:
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
 * A reported write/verification failure restores the complete shared block
 * from its saved bytes, then verifies restoration. A failed restoration
 * asks the user to check the volume. Physical writes and restoration are
 * not atomic on a power cut: the neighbouring half can be damaged. There
 * is no bitmap in CP/M; only a live entry claims the new data blocks.
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
#define IMAGEIO_ONE
#define IMAGEIO_CHECK_CLOSE
#define IMAGEIO_CHECK_ACCESS

#include "util.h"
#include <string.h>
#include "imageio.h"
/* Check full-count errors before the next block clears them. Latch I/O
 * failures so skew selection never retries after an unreadable directory.
 * Restoration still uses the same checked reader/writer; MAIN only. */
static unsigned char image_error;
static unsigned char cpm_rw(unsigned int b,unsigned char* p)
{
    if (!source_rw(b,p) || ferror(src.file)) { image_error = 1; return 0; }
    return 1;
}
#define source_rw cpm_rw
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
/* Preserve both CP/M halves: a failed physical write can damage an entry
 * or allocated neighbour outside the sector being changed. MAIN only. */
static unsigned char undo[512], uncertain;
#define cname (newent + 1)
static unsigned char put, skipped, stopped;
static unsigned int nth;
static FILE* src_file;
static unsigned char slot;
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
    RF(memcpy)(undo, buf, 512);
    ours = buf + ((k & 1) ? 256 : 0);
    mate = buf + ((k & 1) ? 0 : 256);
    /* Publication rereads this shared block once more. The selected slot
     * must still be free in those actual bytes, before replacing them. */
    if (in == dsec) {
        k = (slot & 7) * ENTRY;
        if (ours[k] != 0xE5) return 0;
        /* The cache predates this read: keep every freshly read neighbour
         * and replace only our free slot. Writes stay in the confirmed
         * image; neither source files nor AUX are modified. */
        RF(memcpy)(dsec, ours, 256);
        RF(memcpy)(dsec + k, newent, ENTRY);
    }
    RF(memcpy)(twin, mate, 256);
    RF(memcpy)(ours, in, 256);
    /* ESC received by the preceding read must not start a physical write.
     * Only MAIN buffers changed; no restoration is needed before WRITE. */
    if (stop()) return 0;
    if (source_write(&src, blk, buf) && source_read(&src, blk, buf) &&
        !memcmp(ours, in, 256) && !memcmp(mate, twin, 256)) return 1;
    /* Keep the complete saved block until restoration is read back. A
     * failed restoration must never be reported as an intact volume. */
    if (!source_write(&src, blk, undo) || !source_read(&src, blk, buf) ||
        memcmp(buf, undo, 512)) uncertain = 1;
    return 0;
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

/* One pass over the directory: 2 on read error, 1 when the name is there, 0 with
 * `slot` on the first free entry (0xFF when the directory is full). Two
 * passes -- one for the name, one for the slot -- read the same sixty-four
 * entries twice and cost the window forty bytes it did not have. */
static unsigned char survey(void)
{
    unsigned char i, j;
    const unsigned char* e;
    slot = 0xFF;
    for (i = 0; i < ENTRIES; ++i) {
        e = entry_at(i);
        if (!e) return 2;                       /* neither free nor taken */
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
    i = survey();
    if (i == 2) { note("Cannot read the CP/M directory."); return 0; }
    if (i) { ++skipped; return 1; }
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
            if (n && (RF(fread)(sec, 1, n, src_file) != n || ferror(src_file))) {
                note("Cannot read a file opposite."); goto bad;
            }
            if (stop()) { note("Write failed; the volume is whole."); goto bad; }
            /* the directory cache is idle here: it is the twin buffer */
            if (!cpm_write((unsigned int)b * 4 + l, sec, dsec)) {
                note(uncertain ? "Write failed; check the volume."
                               : "Write failed; the volume is whole."); goto bad;
            }
            left -= n;
        }
        a.progress_bar(name, i + 1, blocks);
    }
    /* A stale panel size must not publish a prefix. Only clean EOF and a
     * successful close validate the source; tail data stays unreferenced. */
    if (RF(fread)(sec, 1, 1, src_file) || ferror(src_file)) {
        note("Cannot read a file opposite."); goto bad;
    }
    i = RF(fclose)(src_file) != 0; src_file = 0;
    if (i) { note("Cannot read a file opposite."); return 0; }
    if (stop()) { note("Stopped; the volume is whole."); return 0; }
    dsec_at = 0xFF;                             /* it was the twin buffer */

    /* Nothing above is visible: no entry names those blocks. The slot is
     * one write, and it is the instant the file exists. */
    { unsigned char* e = entry_at(slot);
      if (!e) { note("Cannot read the directory."); return 0; }
      /* The slot was chosen before data writes. A fresh live entry is
       * owned by someone else, even if our data copy succeeded. Refuse
       * before publishing; image data remains unreferenced, sources/AUX
       * untouched. ESC during this directory read also precedes WRITE. */
      if (live(e)) { note("Directory changed; stopped."); return 0; }
      if (stop()) { note("Stopped; the volume is whole."); return 0; }
        RF(memcpy)(e, newent, ENTRY);
      if (!cpm_write(slot >> 3, dsec, sec)) {
          dsec_at = 0xFF;
          note(uncertain ? "Entry write failed; check the volume."
                         : "Entry not written; the volume is whole.");
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
    unsigned char finished = 0;
    init(api);
    put = skipped = stopped = uncertain = image_error = 0; src_file = 0; src.file = 0;
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
    /* The 2MG header is read outside the checked block path. */
    if (ferror(src.file)) { note("Not a disk image this can open."); goto done; }
    if (image_readonly) { note("The image is read-only."); goto done; }
    if (src.blocks < (RESERVED + 32) * 8) { note("Not a CP/M volume this can read."); goto done; }
    for (skew = 0; skew < SKEWS; ++skew) {
        if (plausible()) break;
        if (image_error) { note("Cannot read the CP/M directory."); goto done; }
    }
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
        /* The resident returns dir_error even though the frozen API types
         * this service void (as FIND already handles). An unreadable or
         * unclosed listing is not EOF and cannot authorize this import. */
        if (((unsigned char (*)(void))a.dir_close)()) {
            note("Cannot read the other panel."); goto done;
        }
        if (k <= nth) break;
        if (a.dir_entry->type == 0x0F) continue;
        if (!join(source_path, other->path, a.dir_entry->name) ||
            !a.strcmp(source_path, a.full)) { ++skipped; continue; }
        if (!one(a.dir_entry->name, a.dir_entry->size)) { stopped = 1; break; }
    }
    if (stopped) goto done;
    finished = 1;
    a.sprintf(a.note, "%u put, %u skipped (name taken or unusable).", put, skipped);
done:
    if (src_file) RF(fclose)(src_file);
    /* Published files stay recoverable. A failed final close is uncertainty,
     * not permission to undo imports; report it and close exactly once. */
    if (RF(fclose)(src.file)) {
        src.file = 0;
        note("Image close failed; check the volume.");
        return;
    }
    src.file = 0;
    if (finished && stop()) note("Stopped; imported files kept.");
}
