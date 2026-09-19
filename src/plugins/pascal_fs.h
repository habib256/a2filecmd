/* pascal_fs.h -- the Apple Pascal (UCSD) volume layer, shared by the
 * overlay that reads one (pascal.c) and the one that writes into it
 * (pascalw.c).
 *
 * Two boot blocks, a flat directory of four blocks at block 2, and every
 * file one contiguous run. The directory is 78 entries of 26 bytes: the
 * first describes the volume, each of the others gives a file's first
 * block, the block after its last, its kind, its name and how many bytes
 * of that last block it uses. Entries are kept in order of first block,
 * and read_dir() refuses a directory that is not.
 *
 * Whoever includes this defines nothing of its own by these names.
 */
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
