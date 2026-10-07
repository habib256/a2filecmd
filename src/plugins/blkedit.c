/* blkedit.c -- the block EDITOR, next to BLKVIEW's read-only explorer:
 * change bytes of a ProDOS block and write it back, on a device or inside a
 * .PO/.HDV/.DSK/.DO/.2MG image. From the ! menu, on the selected volume or
 * image, exactly as BLKVIEW is opened.
 *
 * Two overlays and not one because BLKVIEW is FULL: its code, strings and
 * BSS end at $3F8B, nineteen bytes below the service table it reads at
 * $3F9E. There was no room to grow an editor inside it -- and keeping the
 * explorer strictly read-only is worth something of its own: the tool one
 * reaches for to look at a suspect disk cannot write to it by a slip of the
 * finger. BLKVIEW reads, decodes directories and indexes, searches and
 * extracts; BLKEDIT navigates, edits and writes.
 *
 * Nothing reaches the disk until BOTH of these have happened: a byte was
 * changed with the cursor, and the word ERASE was typed in full at the W
 * prompt -- the guard DISKIMG and WIPE already use for what cannot be
 * undone. The block is then read back and compared byte for byte: a drive
 * that reports success and keeps its old contents (a driver that lies about
 * write protection, a failing sector) is a failure here, not a success.
 *
 * A raw write goes to whatever disk is in the drive when it happens. After
 * ERASE, block 2 is read again and its CRC-32 compared with the one taken
 * when the disk was opened (same_disk): a floppy changed while the block
 * was being edited, or during the prompt, is not written, and the edit
 * stays in the buffer until the right disk is back. An image of one or two
 * blocks has no block 2: its block 0 is the identity. A copy whose block 2
 * is identical byte for byte cannot be told apart, nor -- one chance in
 * 2^32 -- one whose block 2 differs and has the same CRC; and a swap between
 * that check and the write itself cannot be excluded on this hardware.
 *
 * The volume A2FC is running from is refused outright. ProDOS holds
 * directory blocks of an open volume in its own buffers, so a block written
 * underneath it is liable to be written back over from that cache; and the
 * program's own file lives there.
 *
 * Following a pointer: T reads the two bytes under the cursor as a block
 * number (low byte first, as ProDOS writes them everywhere except an index
 * block) and goes there; Y reads them the way an INDEX block stores them,
 * the low bytes in the first half of the block and the high bytes in the
 * second, 256 apart. Put the cursor on a directory entry's key pointer and
 * T follows the file; put it on an index slot and Y follows the data. That
 * is file following, without a second decoder to carry.
 *
 * A big overlay ($1B00-$3F9D, the service table at $3F9E): the graphics page
 * is its own, the core sets the tags aside and rereads the panels. The block
 * being edited lives in api->copy_buf; the readback needs a second 512
 * bytes, which is why `check` is in this overlay's BSS and borrows nothing
 * of the core's. */
#define UTIL_FIXED_API
#define UTIL_VOLUME
#define UTIL_TWIN
#define UTIL_WRITE
#define IMAGEIO_WRITE
#include "util.h"
#include "imageio.h"

#ifdef PLUGIN_HOST
#define v_cprintf (a.cprintf)
#define v_cputs (a.cputs)
#define v_cputc (a.cputc)
#define v_gotoxy (a.gotoxy)
#define v_revers (a.revers)
#define v_clrscr (a.clrscr)
#define v_cgetc (a.cgetc)
#define v_message (a.message)
#define v_confirm (a.confirm)
#define v_prompt (a.prompt)
#define v_strcpy (a.strcpy)
#define v_strcmp (a.strcmp)
#else
int __cdecl__ v_cprintf(const char*, ...);
void __fastcall__ v_cputs(const char*);
void __fastcall__ v_cputc(char);
void __fastcall__ v_gotoxy(unsigned char, unsigned char);
unsigned char __fastcall__ v_revers(unsigned char);
void __fastcall__ v_clrscr(void);
char __fastcall__ v_cgetc(void);
void __fastcall__ v_message(const char*);
unsigned char __fastcall__ v_confirm(const char*);
unsigned char __fastcall__ v_prompt(const char*, const char*, unsigned char);
char* __fastcall__ v_strcpy(char*, const char*);
int __fastcall__ v_strcmp(const char*, const char*);
#endif

void __fastcall__ plugin_entry(const struct A2fcApi* api);
struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char reserved[3]; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, {0,0,0},
    "Edit a disk block and write it back after ERASE"
};
#pragma rodata-name (pop)

/* BSS: nothing zeroes it; everything below is written before it is read. */
static struct Source source;
static unsigned int block;              /* the block being looked at */
static unsigned int shown;              /* the block copy_buf actually holds */
static unsigned char page;              /* 0 or 1: which half of it is on screen */
static unsigned char cur;               /* the cursor, 0-255 within that half */
static unsigned char dirty;             /* the buffer and the disk disagree */
static unsigned char loaded;            /* copy_buf holds a block at all */
static unsigned char check[512];        /* the readback; block 2 for the identity */
#define high (check + 256)               /* its second half, indexed by a byte */
static unsigned char idblk;             /* the identity block: 2, or 0 below 3 blocks */
static unsigned char ident[4];          /* the CRC-32 of that block on the disk opened */

static const char m_pick[]  = "Select a ProDOS volume or a .PO/.DSK/.2MG image.";
static const char m_open[]  = "Invalid or unreadable image.";
static const char m_vol[]   = "Cannot open that ProDOS volume.";
static const char m_read[]  = "Block read failed.";
static const char m_boot[]  = "That volume holds the running program: refused.";
static const char m_ro[]    = "The image is locked or read-only: nothing written.";
static const char m_none[]  = "Nothing changed yet. The hex digits edit a byte.";
static const char m_stop[]  = "Nothing was written.";
static const char m_wfail[] = "Write failed: the block is unchanged or half written.";
static const char m_rfail[] = "Written, but it cannot be read back to be checked.";
static const char m_diff[]  = "READBACK DIFFERS: the disk did not take the block.";
static const char m_done[]  = "Block %u written and read back identical. Any key.      ";
static const char m_warn[]  = " BLOCK %u OF %s WILL BE OVERWRITTEN. ";
static const char m_swap[]  = " BLOCK %u NOT WRITTEN: NOT %s AS OPENED, OR UNREADABLE. ";
static const char m_erase[] = "Type ERASE to write it";
static const char m_word[]  = "ERASE";
static const char m_lost[]  = "This block was changed and not written. Discard?";
static const char m_out[]   = "That pointer is zero or outside the disk.";
static const char m_bar[]   = "Arrows/0-9A-F Edit  TAB Half  N/P Blk  G Go  T/Y Follow  W Write  ESC";

/* Four hex digits of api->input as a number: the only text this overlay
 * reads besides the word ERASE. */
static unsigned int number(const char* text, unsigned char n)
{
    unsigned int v = 0;
    unsigned char c;
    while (n--) { c = *text++; v = (v << 4) | (c <= '9' ? c - '0' : c - 'A' + 10); }
    return v;
}

/* The byte at `i` of the half on screen, hex and ASCII, in inverse video
 * when it is the one under the cursor. Five columns of offset, three per
 * hex byte from column 5, the ASCII pane from column 54. */
static void draw_byte(unsigned char i, unsigned char inv)
{
    unsigned int off = (unsigned int)page * 256 + i;
    unsigned char c = i & 15, r = 3 + (i >> 4), ch = buf[off] & 127;
    if (inv) v_revers(1);
    v_gotoxy(5 + c * 3, r);
    v_cprintf("%02X", buf[off]);
    v_gotoxy(54 + c, r);
    v_cputc(ch >= 32 && ch < 127 ? ch : '.');
    if (inv) v_revers(0);
}

/* The whole screen: what disk, what block, whether it is dirty, then the
 * half on screen in hex and ASCII. */
static void draw(void)
{
    unsigned int off;
    unsigned char r, c;
    v_clrscr();
    v_cprintf("BLKEDIT - %s - %s\r\n",
              dirty ? "CHANGED, NOT WRITTEN" : "unchanged", source.path);
    v_cprintf("Block %u ($%04X) / %u blocks   Half %u   Offset $%03X\r\n",
              block, block, source.blocks, page + 1, (unsigned int)page * 256 + cur);
    for (r = 0; r < 16; ++r) {
        off = (unsigned int)page * 256 + (unsigned int)r * 16;
        v_gotoxy(0, r + 3);
        v_cprintf("%03X  ", off);
        for (c = 0; c < 16; ++c) v_cprintf("%02X ", buf[off + c]);
        v_cputs(" ");
        for (c = 0; c < 16; ++c) {
            unsigned char ch = buf[off + c] & 127;
            v_cputc(ch >= 32 && ch < 127 ? ch : '.');
        }
    }
    v_gotoxy(0, 22);
    v_cputs(m_bar);
}

/* Is this source the volume A2FC itself runs from? api->cfg_path is
 * "/VOL/A2FILE/A2FILE.CFG", so its first component is that volume; the
 * source path is the panel's, a subdirectory as often as a volume root, so
 * only its first component counts too. A source that is an image FILE is
 * never the running program, whatever it holds. */
static unsigned char boot_volume(void)
{
    unsigned char i;
    if (!source.unit) return 0;
    for (i = 1; source.path[i] && source.path[i] != '/' && source.path[i] == a.cfg_path[i]; ++i) ;
    return (!source.path[i] || source.path[i] == '/') && a.cfg_path[i] == '/';
}

/* 1 when `check` holds the 512 bytes of `buf`. A byte index on both
 * halves: cc65 miscompiles a 16-bit index into a page-aligned array. */
static unsigned char same_block(void)
{
    unsigned char i = 0;
    do {
        if (buf[i] != check[i]) return 0;
        if (buf[i + 256] != high[i]) return 0;
        ++i;
    } while (i);
    return 1;
}

/* The identity of the disk. Raw writes go to whatever disk the drive
 * holds at the moment, and the ERASE prompt left all the time needed to
 * change it. Block 2 (the volume header: name, dates, size, file count,
 * and the first directory entries) is read into `check` and its CRC-32
 * (reflected, polynomial $EDB88320, no final inversion) left in `crc`.
 * Every error of 32 bits or fewer, every byte swap and every pair of flipped
 * bits in the block changes it; it replaced two pairs of 8-bit running sums
 * that bit 7 flipped in two bytes an even distance apart, two bytes 128
 * apart swapped, or two directory entries of equal byte sums swapped all
 * left unchanged. The whole block, kept, would be exact, but 512 more bytes
 * do not fit beside `check`. crc512 is assembly in blkedit.s (a C loop over
 * a 32-bit value is a library call per bit in cc65). 1: read. */
#ifdef PLUGIN_HOST
static unsigned char crc[4];
static void crc512(const unsigned char* p)
{
    unsigned long c = 0xFFFFFFFFUL;
    unsigned int i;
    unsigned char k;
    for (i = 0; i < 512; ++i) {
        c ^= p[i];
        for (k = 0; k < 8; ++k) c = c & 1 ? (c >> 1) ^ 0xEDB88320UL : c >> 1;
    }
    for (k = 0; k < 4; ++k) crc[k] = (unsigned char)(c >> (8 * k));
}
#else
extern unsigned char crc[4];
void __fastcall__ crc512(const unsigned char* p);
#endif
static unsigned char sign(void)
{
    if (!source_read(&source, idblk, check)) return 0;
    crc512(check);
    return 1;
}

/* The identity block of the disk in the drive becomes the identity: block
 * 2, or block 0 of an image of one or two blocks, which has no block 2 (it
 * was read all the same, and such an image no longer opened). 1: read. */
static unsigned char remember(void)
{
    idblk = source.blocks > 2 ? 2 : 0;
    if (!sign()) return 0;
    ident[0] = crc[0]; ident[1] = crc[1]; ident[2] = crc[2]; ident[3] = crc[3];
    return 1;
}

/* Is the disk in the drive the one opened? An unreadable identity block is
 * a refusal, not a pass. When that block itself is being written, finding
 * it already equal to the edit (a previous W got that far) also passes:
 * writing the same bytes again changes nothing on any disk. */
static unsigned char same_disk(void)
{
    if (!sign()) return 0;
    if (block == idblk && same_block()) return 1;
    if (crc[0] != ident[0]) return 0;
    if (crc[1] != ident[1]) return 0;
    if (crc[2] != ident[2]) return 0;
    if (crc[3] != ident[3]) return 0;
    return 1;
}

/* Row 20, in inverse: the warning, or why nothing was written. */
static void banner(const char* f)
{
    v_gotoxy(0, 20);
    v_revers(1);
    v_cprintf(f, block, source.path);
    v_revers(0);
}

/* W: the block back to the disk, once, with everything that guards it. */
static void write_block(void)
{
    if (!dirty) { v_message(m_none); v_cgetc(); return; }
    if (boot_volume()) { v_message(m_boot); v_cgetc(); return; }
    if (!source.unit && image_readonly) { v_message(m_ro); v_cgetc(); return; }
    banner(m_warn);
    if (!v_prompt(m_erase, NULL, 0) || v_strcmp(a.input, m_word)) {
        v_message(m_stop); v_cgetc(); return;
    }
    /* The last look before the write; the edit stays in `buf`, dirty, for
     * a W once the right disk is back. */
    if (!same_disk()) { banner(m_swap); v_cgetc(); return; }
    if (!source_write(&source, block, buf)) { v_message(m_wfail); v_cgetc(); return; }
    /* Read back into `check`, never over the buffer we just wrote: if the
     * readback fails the edit is still there to try again. */
    if (!source_read(&source, block, check)) {
        v_message(m_rfail); v_cgetc(); return;
    }
    if (!same_block()) { v_message(m_diff); v_cgetc(); return; }
    /* The identity block now holds the edit: the identity from here on. */
    if (block == idblk) remember();
    dirty = 0;
    v_gotoxy(0, 22);                    /* over the key bar; draw() puts it back */
    v_cprintf(m_done, block);
    v_cgetc();
}

/* Leaving the block on screen with changes that never reached the disk. */
static unsigned char may_leave(void)
{
    if (!dirty) return 1;
    if (!v_confirm(m_lost)) return 0;
    dirty = 0;
    return 1;
}

/* G: another block, by number. */
static void jump(void)
{
    unsigned int b;
    if (!v_prompt("Block number (4 hex digits)", NULL, 4)) return;
    b = number(a.input, 4);
    if (b >= source.blocks) { v_message(m_out); v_cgetc(); return; }
    block = b;
}

/* T and Y: the block the two bytes under the cursor name. `split` reads
 * them an INDEX block's way, the low byte here and the high one 256 bytes
 * further on; otherwise they are the consecutive pair ProDOS writes
 * everywhere else. */
static void follow(unsigned char split)
{
    unsigned int off = (unsigned int)page * 256 + cur, b;
    if (split) b = buf[off & 255] | ((unsigned int)buf[(off & 255) + 256] << 8);
    else b = buf[off] | ((unsigned int)buf[off + 1 > 511 ? 511 : off + 1] << 8);
    if (!b || b >= source.blocks) { v_message(m_out); v_cgetc(); return; }
    block = b;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char key, unit, hi = 0x10;   /* $10: no half-typed hex digit */

    init(api);
    block = 0; page = 0; cur = 0; dirty = 0; loaded = 0; shown = 0;
    if (pan->fs) { note(m_pick); return; }
    if (pan->path[0] && image_kind(a.selected->name)) {
        if (!a.full[0]) { note(m_pick); return; }
        v_strcpy(source.path, a.full);
        if (!image_open(&source)) { note(m_open); return; }
        /* ProDOS OPENs a locked file for update and refuses only the WRITE:
         * say so before the ERASE prompt, from the entry's write bit. */
        if (!(a.selected->access & 0x02)) image_readonly = 1;
    } else {
        v_strcpy(source.path, pan->path[0] ? pan->path : a.selected->name);
        unit = pan->path[0] ? 0 : (unsigned char)(a.selected->mdate << 4);
        /* unit_of's own note stays: two volumes of that name on line. */
        if (source.path[0] != '/' || !volume_open(&source, unit)) { if (!*a.note) note(m_vol); return; }
    }

    for (;;) {
        /* Reread ONLY when the block changes: rereading every time round
         * would throw away what the cursor has just changed. */
        if (!loaded || block != shown) {
            /* The first time round, block 2 too (block 0 below three
             * blocks): the identity W checks before it writes, read the
             * same way whatever the disk holds (a DOS 3.3 image has a block
             * 2, only not a volume header). */
            if ((!loaded && !remember()) || !source_read(&source, block, buf)) { note(m_read); break; }
            shown = block; loaded = 1; dirty = 0; cur = 0; hi = 0x10;
        }
        draw();
        for (;;) {                        /* the cursor keys, until one leaves */
            draw_byte(cur, 1);
            key = v_cgetc();
            draw_byte(cur, 0);
            if (key == KEY_LEFT)  { --cur; hi = 0x10; continue; }
            if (key == KEY_RIGHT) { ++cur; hi = 0x10; continue; }
            if (key == KEY_UP)    { cur -= 16; hi = 0x10; continue; }
            if (key == KEY_DOWN)  { cur += 16; hi = 0x10; continue; }
            if (key >= 'a' && key <= 'z') key -= 32;
            if (key >= '0' && key <= '9') {
                if (hi == 0x10) { hi = key - '0'; continue; }
                buf[(unsigned int)page * 256 + cur] = (hi << 4) | (key - '0');
            } else if (key >= 'A' && key <= 'F') {
                if (hi == 0x10) { hi = key - 'A' + 10; continue; }
                buf[(unsigned int)page * 256 + cur] = (hi << 4) | (key - 'A' + 10);
            } else break;                 /* not a digit: a command */
            dirty = 1; hi = 0x10;
            draw_byte(cur, 0);
            ++cur;
            v_gotoxy(0, 0);               /* the header says CHANGED from now on */
            v_cprintf("BLKEDIT - CHANGED, NOT WRITTEN - %s ", source.path);
        }
        if (key == KEY_ESC) { if (may_leave()) break; else continue; }
        if (key == KEY_TAB) { page ^= 1; continue; }
        key &= 0xDF;
        if (key == 'W') { write_block(); continue; }
        if (key == 'T' || key == 'Y') { if (may_leave()) follow(key == 'Y'); continue; }
        if (key == 'G') { if (may_leave()) jump(); continue; }
        if (key == 'N' && block + 1 < source.blocks) { if (may_leave()) ++block; continue; }
        if (key == 'P' && block) { if (may_leave()) --block; continue; }
    }
    source_close(&source);
}
