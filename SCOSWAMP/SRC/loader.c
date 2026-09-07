/* SCOSWAMP.SYSTEM: ProDOS loads this launcher at $2000.
 * The game file starts with a fixed $0C00-byte LC image staged at $1000.
 * The remainder is loaded at $4000; entry remains $4000. Local crt0.s
 * copies the prefix to LC bank 2 before main clears LOWBSS at $1000.
 * Thus LC does not occupy the top of MAIN during startup. This file is
 * a split-load image, not a flat binary suitable for BASIC.SYSTEM BRUN.
 */

#include <stdio.h>
#include <conio.h>
#include <unistd.h>
#include <errno.h>

#ifndef GAME_FILE
#define GAME_FILE "SCOSWAMP"
#endif

#define GAME_ADDR 0x4000
#define CHUNK     1024
#define LC_STAGE  0x1000
#define LC_BYTES  0x0C00

int main(void)
{
    FILE* f;
    unsigned char* dst = (unsigned char*)GAME_ADDR;
    size_t n;

    videomode(VIDEOMODE_80COL);
    clrscr();
#ifdef DIAPO_LOADER
    cputs("PLEASE WAIT");
#endif
#ifdef TOTAL_LOADER
    /* L'ecran d'attente d'Apple Total Commander : le titre, la condition
     * ProDOS, la date si une horloge est la (bit 0 de MACHID, $BF98 ; ProDOS
     * tient alors $BF90-$BF93 a jour), puis le chargement. */
    {
        unsigned char machid = *(unsigned char*)0xBF98;
        unsigned int date = *(unsigned int*)0xBF90;
        unsigned char minute = *(unsigned char*)0xBF92, hour = *(unsigned char*)0xBF93;
        unsigned char year = date >> 9;
        gotoxy(26, 2);
        revers(1);
        cputs("  APPLE TOTAL COMMANDER " TOTAL_VERSION "  ");
        revers(0);
        gotoxy(14, 4);
        cputs("A two-panel file manager for the Apple IIe with 128 KB.");
        gotoxy(14, 5);
        cputs("It runs under ProDOS 8 only, launched from Bitsy Bye or at boot.");
        gotoxy(14, 8);
        if (machid & 1)
            cprintf("Date: %02u/%02u/%u  %02u:%02u", date & 31, (date >> 5) & 15,
                    year < 40 ? 2000 + year : 1900 + year, hour, minute);
        else
            cputs("No clock: new files will carry no date.");
        gotoxy(14, 11);
        cputs("PLEASE WAIT, loading TOTAL.CODE ...");
    }
#endif

    /* Sur la disquette Apple Total Commander (NO_CHDIR), le prefixe est deja
     * la racine du volume amorce : pas de nom de volume a connaitre. */
#ifdef NO_CHDIR
    if ((f = fopen(GAME_FILE, "rb")) == NULL) {
#else
    if (chdir("/SCOSWAMP") != 0 || (f = fopen(GAME_FILE, "rb")) == NULL) {
#endif
        cprintf("SCOSWAMP introuvable sur /SCOSWAMP (errno=%d).\r\n", errno);
        cprintf("Appuyez sur une touche...\r\n");
        cgetc();
        return 1;
    }
    /* The first 3 KiB are transient LC code, consumed by crt0 before
     * main() initializes LOWBSS at the same address. */
    if (fread((void*)LC_STAGE, 1, LC_BYTES, f) != LC_BYTES) {
        fclose(f);
        cputs("Image LC incomplete.\r\n");
        cgetc();
        return 1;
    }
    while ((n = fread(dst, 1, CHUNK, f)) > 0) dst += n;
    fclose(f);

    /* Le jeu ne revient jamais : il sort par le QUIT ProDOS. */
    ((void (*)(void))GAME_ADDR)();
    return 0;
}
