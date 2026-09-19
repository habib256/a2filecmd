/* cpm_fs.h -- the Apple II CP/M volume layer, shared by the overlay that
 * reads one (cpm.c) and the one that writes into it (cpmw.c).
 *
 * Blocks of 1,024 bytes, 128 of them, the first three tracks kept for CP/M
 * itself, and the first two blocks of what follows given to a directory of
 * 64 entries of 32 bytes. An entry is one extent of 16 KB: a user number,
 * an eight-and-three name whose high bits are attributes, the extent number
 * in EX and S2, the records used in RC, and sixteen block numbers.
 *
 * The skew is not guessed: plausible() answers whether the directory read
 * through the current one explains itself, and the caller keeps the table
 * that passes. A wrong order turns the directory into noise and fails that
 * test, so the cost of not knowing is a refusal and never a wrong byte.
 */
#define RESERVED 3              /* tracks CP/M keeps for itself */
#define DIR_SECTORS 8           /* two 1,024-byte blocks of directory */
#define ENTRIES 64
#define ENTRY 32
#define BLOCKS 128              /* DSM + 1 */
#define DIR_BLOCKS 2

/* The sector orders tried, sixteen logical to physical. The first was
 * measured on disks from Asimov (images/cpm) on 19 September 2026: the
 * eight sectors of a directory were found by looking for 32-byte entries
 * that read as entries, and they fell on 0, 6, 12 with the empty tail on
 * 3, 5, 9, 14 and 15 -- this table and no other. The second is for an
 * image some tool has already deblocked. */
static const unsigned char SKEW[][16] = {
    { 0, 6, 12, 3, 9, 15, 14, 5, 11, 2, 8, 7, 13, 4, 10, 1 },
    { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 },
};
#define SKEWS (sizeof SKEW / sizeof SKEW[0])

static struct Source src;
static unsigned char skew;              /* which of SKEW is in use */
static unsigned char sec[256];          /* one CP/M sector */
static unsigned char dsec[256];         /* the directory sector being read */
static int dsec_at;                     /* which one, or -1 */
static unsigned char claimed[BLOCKS / 8];

/* One 256-byte CP/M sector into `out`. A ProDOS block holds two physical
 * sectors, and their order is 0, 14, 13 ... 1, 15 -- which is its own
 * inverse but for the ends, so no table is needed to undo it. */
static unsigned char cpm_sector(unsigned int logical, unsigned char* out)
{
    unsigned char p = SKEW[skew][logical & 15], k;
    k = (p == 0 || p == 15) ? p : 15 - p;
    if (!source_read(&src, (RESERVED + (logical >> 4)) * 8 + (k >> 1), buf)) return 0;
    memcpy(out, buf + ((k & 1) ? 256 : 0), 256);
    return 1;
}

/* Directory entry i, kept in a one-sector cache: eight entries share one. */
static unsigned char* entry_at(unsigned char i)
{
    unsigned char s = i >> 3;
    if (dsec_at != s) {
        if (!cpm_sector(s, dsec)) return 0;
        dsec_at = s;
    }
    return dsec + (i & 7) * ENTRY;
}

static unsigned char live(const unsigned char* e) { return e[0] != 0xE5; }
static unsigned int extent_of(const unsigned char* e) { return e[12] + 32 * (unsigned int)e[14]; }

/* Does the directory read through the current skew explain itself? */
static unsigned char plausible(void)
{
    unsigned char i, j, c, n = 0, b;
    const unsigned char* e;
    a.memset(claimed, 0, sizeof claimed);
    dsec_at = -1;
    for (i = 0; i < ENTRIES; ++i) {
        e = entry_at(i);
        if (!e) return 0;
        if (!live(e)) continue;
        if (e[0] > 15 || e[15] > 128) return 0;
        for (j = 1; j < 9; ++j) if ((e[j] & 127) != ' ') break;
        if (j == 9) return 0;           /* a file with no name is not a file */
        for (j = 1; j < 12; ++j) {
            c = e[j] & 127;
            if (c < ' ' || c > '~' || c == '.' || c == ',' || c == ':' ||
                c == ';' || c == '=' || c == '?' || c == '*' || c == '[' ||
                c == ']' || c == '<' || c == '>' || c == '/' || c == '\\') return 0;
        }
        for (j = 16; j < 32; ++j) {
            b = e[j];
            if (!b) continue;
            if (b >= BLOCKS || b < DIR_BLOCKS || (claimed[b >> 3] & (1 << (b & 7)))) return 0;
            claimed[b >> 3] |= 1 << (b & 7);
        }
        ++n;
    }
    return n != 0;
}
