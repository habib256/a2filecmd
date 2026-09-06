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

    if (chdir("/SCOSWAMP") != 0 || (f = fopen(GAME_FILE, "rb")) == NULL) {
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
