/* A2FILE.SYSTEM: the ProDOS launcher of A2 File Cmd.
 *
 * ProDOS loads every SYS program at $2000 and hands it control. But A2 File
 * Cmd runs at $4000 and fills almost everything up to $BEFF: it CANNOT be
 * a SYS. This small launcher is one, and reads the real program in its
 * place.
 *
 * A2FILE.CODE is not a flat binary: it is a split-load image. Its first
 * 3 kilobytes go to $1000 -- code meant for the language card, which
 * crt0.s copies to $D400 before main() clears low RAM. The rest goes to
 * $4000, where execution starts. A BLOAD could not do this: the file is
 * not BRUNable, it is started from here. (The overlays, A2FILE/IMAGE.PLG,
 * are loaded by A2FC itself at $1B00 when it needs them.)
 *
 * The ProDOS prefix is that of the boot volume: the launcher opens
 * "A2FILE/A2FILE.CODE" relatively, without having to know the volume name.
 */

#include <stdio.h>
#include <conio.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

#ifndef CODE_FILE
#define CODE_FILE "A2FILE/A2FILE.CODE"
#endif
#ifndef A2FC_VERSION
#define A2FC_VERSION "0.6.8"
#endif

/* src/loader_mli.s: set the ProDOS prefix to the boot volume before
 * jumping into A2FC (see the note in that file and before the call below). */
extern void set_boot_prefix(void);

#define CODE_ADDR   0x4000
#define CHUNK       1024
#define LC_STAGE    0x1000
#define LC_BYTES    0x0C00      /* the language card image */
#define STAGE_BYTES 0x0C00      /* nothing else: the RAM above belongs to the overlays */

/* A line centred on the 80 columns. */
static void centre(unsigned char y, const char* text)
{
    gotoxy((80 - strlen(text)) / 2, y);
    cputs(text);
}

int main(void)
{
    FILE* f;
    unsigned char* dst = (unsigned char*)CODE_ADDR;
    size_t n;

    videomode(VIDEOMODE_80COL);
    clrscr();
    /* The waiting screen: the title, the ProDOS requirement, the date if a
     * clock is present (bit 0 of MACHID, $BF98; ProDOS then keeps
     * $BF90-$BF93 up to date), then the loading. */
    {
        static const char* const months[] = { "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December" };
        unsigned char machid = *(unsigned char*)0xBF98;
        unsigned int date = *(unsigned int*)0xBF90;
        unsigned char minute = *(unsigned char*)0xBF92, hour = *(unsigned char*)0xBF93;
        unsigned char year = date >> 9, month = (date >> 5) & 15, day = date & 31;
        /* A frame, the title in inverse, what the program can do in two
         * columns, what it requires, the licence, the date, and the loading
         * at the bottom: the page one reads while the floppy spins. */
        chlinexy(0, 0, 80);
        chlinexy(0, 4, 80);
        for (n = 1; n < 4; ++n) { cputcxy(0, n, '|'); cputcxy(79, n, '|'); }
        revers(1);
#ifdef A2FC_6502
        centre(2, "  A2 FILE CMD " A2FC_VERSION " - 6502 FLOPPY EDITION  ");
#else
        centre(2, "  A2 FILE CMD " A2FC_VERSION " - 65C02 COMPLETE EDITION  ");
#endif
        revers(0);
        centre(3, "Two panels. One Apple II.");
        centre(6, "A two-pane ProDOS file manager running natively on Apple IIe.");
        cputsxy(4, 8,  "Copy, move, rename, delete, tag, sort.");
#ifdef A2FC_6502
        /* The floppy edition, the 6502 build: the file manager and the disk
         * tools, on any Apple II with 128 KB and 80 columns -- the page says
         * so, and where the rest is. */
        cputsxy(44, 8, "Text viewer, hex dump, attributes.");
        cputsxy(4, 9,  "Copy, write and read floppy images.");
        cputsxy(44, 9, "DOS 3.3 disks, images as folders.");
        cputsxy(4, 10,  "Disk formatter, program launcher.");
        cputsxy(44, 10, "Keyboard: press ? for help.");
        cputsxy(4, 12, "FLOPPY EDITION, 6502 BUILD: any Apple II with 128 KB and 80 columns.");
        cputsxy(4, 13, "Editor, pictures, music, archives, readers: see A2FILECMDXL-65C02.2mg.");
#else
        cputsxy(44, 8, "Text viewer, hex dump, text editor.");
        cputsxy(4, 9,  "HGR and DHGR pictures, full screen.");
        cputsxy(44, 9, "Mockingboard music player.");
        cputsxy(4, 10,  "Disk formatter, program launcher.");
        cputsxy(44, 10, "Mouse or keyboard: press ? for help.");
        cputsxy(4, 12, "COMPLETE EDITION, 65C02 BUILD: enhanced IIe, //c, IIgs; 128 KB, 80 cols.");
        cputsxy(4, 13, "Optional: a Mockingboard and an AppleMouse II, in any slot.");
#endif
        cputsxy(4, 15, "Free software under the GNU GPL v3, by Arnaud VERHILLE.");
        cputsxy(4, 16, "https://github.com/habib256/a2filecmd");
        gotoxy(4, 18);
        /* ProDOS: 7-bit year (0-39 = 2000-2039), month 1-12, day 1-31,
         * hour 0-23 -- already in 24-hour form. An out-of-range date means none. */
        if ((machid & 1) && month >= 1 && month <= 12 && day >= 1 && day <= 31 && hour < 24 && minute < 60)
            cprintf("%u %s %u, %02u:%02u", day, months[month - 1],
                    year < 40 ? 2000 + year : 1900 + year, hour, minute);
        else
            cputs("No clock: new files will carry no date.");
        chlinexy(0, 20, 80);
        gotoxy(4, 22);
        cputs("PLEASE WAIT, loading A2FILE.CODE ...");
    }

    /* The prefix first: A2FILE/A2FILE.CODE is read relatively. On a cold
     * boot ProDOS has set it, Bitsy Bye too (the directory of the .SYSTEM),
     * but relaunching by "-A2FILE.SYSTEM" from BASIC.SYSTEM leaves it EMPTY:
     * set_boot_prefix then rebuilds it from the full path that BASIC.SYSTEM
     * leaves at $0280, or from the boot volume. Without it A2FC would open
     * on the volume list, without A2FILE.CFG -- or would not load at all,
     * when installed elsewhere than at the root. */
    set_boot_prefix();
    if ((f = fopen(CODE_FILE, "rb")) == NULL) {
        cprintf("\r\n%s not found (errno=%d).\r\n", CODE_FILE, errno);
        cputs("Press a key ...\r\n");
        cgetc();
        return 1;
    }
    if (fread((void*)LC_STAGE, 1, STAGE_BYTES, f) != STAGE_BYTES) {
        fclose(f);
        cputs("\r\nTruncated image.\r\n");
        cgetc();
        return 1;
    }
    /* Never beyond $BEFF: the ProDOS global page is at $BF00. */
    while (dst < (unsigned char*)0xBF00 && (n = fread(dst, 1, (unsigned char*)0xBF00 - dst < CHUNK ? (unsigned char*)0xBF00 - dst : CHUNK, f)) > 0) dst += n;
    fclose(f);

    /* A2 File Cmd never comes back here: it leaves through the ProDOS QUIT. */
#ifdef A2FC_TRACE
    *(unsigned char*)0x03A2 = 1; *(unsigned char*)0x03A0 = 0; *(unsigned char*)0x03A1 = 0;
#endif
    ((void (*)(void))CODE_ADDR)();
    return 0;
}
