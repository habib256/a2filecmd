/*
 * SCOSWAMP.SYSTEM - le lanceur ProDOS.
 *
 * Pourquoi il existe. Le jeu est lie a $4000 (pour laisser la page HGR 1 libre
 * en $2000-$3FFF) avec __HIMEM__ = $BF00 : son image fait 21 914 octets et
 * s'etend jusqu'a $9556, son BSS jusqu'a $A3D9. BASIC.SYSTEM, lui, vit en
 * $9600-$BEFF et place ses tampons de fichier juste sous lui. Un BRUN depuis
 * BASIC.SYSTEM ecraserait donc ses propres tampons : il refuse, avec un
 * "NO BUFFERS AVAILABLE" suivi d'un BREAK.
 *
 * D'ou ce lanceur. ProDOS charge les fichiers SYSTEM en $2000 et leur saute
 * dedans sans BASIC.SYSTEM ; celui-ci lit le binaire du jeu en $4000 et lui
 * passe la main. Il meurt a cet instant, et $2000 redevient la page HGR --
 * c'est exactement la memoire que le decodeur d'images va reutiliser.
 */

#include <stdio.h>
#include <conio.h>
#include <unistd.h>
#include <errno.h>

#define GAME_ADDR 0x4000
#define CHUNK     1024

int main(void)
{
    FILE* f;
    unsigned char* dst = (unsigned char*)GAME_ADDR;
    size_t n;

    videomode(VIDEOMODE_80COL);
    clrscr();

    if (chdir("/SCOSWAMP") != 0 || (f = fopen("SCOSWAMP", "rb")) == NULL) {
        cprintf("SCOSWAMP introuvable sur /SCOSWAMP (errno=%d).\r\n", errno);
        cprintf("Appuyez sur une touche...\r\n");
        cgetc();
        return 1;
    }
    while ((n = fread(dst, 1, CHUNK, f)) > 0) dst += n;
    fclose(f);

    /* Le jeu ne revient jamais : il sort par le QUIT ProDOS. */
    ((void (*)(void))GAME_ADDR)();
    return 0;
}
