/* A2RETRO.SYSTEM : le lanceur ProDOS d'A2 Retro Cmd.
 *
 * ProDOS charge tout programme SYS en $2000 et lui donne la main. Or A2 Retro
 * Cmd tourne en $4000 et occupe presque tout jusqu'a $BEFF : il ne PEUT pas
 * etre un SYS. Ce petit lanceur en est un, et lit le vrai programme a sa
 * place.
 *
 * A2RETRO.CODE n'est pas un binaire plat : c'est une image a charge separee.
 * Ses 4 premiers kilo-octets vont en $1000 -- 3 Ko de code destines a la carte
 * langage, que crt0.s recopie en $D400 avant que main() n'efface la RAM basse,
 * puis 1 Ko de code qui reste sur place en $1C00 (segment LOWEXE). Le reste va
 * en $4000, ou commence l'execution. Un BLOAD ne saurait pas faire cela : le
 * fichier n'est pas BRUNable, il se lance par ici.
 *
 * Le prefixe ProDOS est celui du volume amorce : le lanceur ouvre
 * "A2RETRO/A2RETRO.CODE" en relatif, sans avoir a connaitre le nom du volume.
 */

#include <stdio.h>
#include <conio.h>
#include <unistd.h>
#include <errno.h>

#ifndef CODE_FILE
#define CODE_FILE "A2RETRO/A2RETRO.CODE"
#endif
#ifndef A2RC_VERSION
#define A2RC_VERSION "1.0"
#endif

#define CODE_ADDR   0x4000
#define CHUNK       1024
#define LC_STAGE    0x1000
#define LC_BYTES    0x0C00      /* l'image de la carte langage */
#define STAGE_BYTES 0x1000      /* elle, plus le kilo-octet LOWEXE de $1C00 */

int main(void)
{
    FILE* f;
    unsigned char* dst = (unsigned char*)CODE_ADDR;
    size_t n;

    videomode(VIDEOMODE_80COL);
    clrscr();
    /* L'ecran d'attente : le titre, la condition ProDOS, la date si une
     * horloge est la (bit 0 de MACHID, $BF98 ; ProDOS tient alors
     * $BF90-$BF93 a jour), puis le chargement. */
    {
        static const char* const months[] = { "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December" };
        unsigned char machid = *(unsigned char*)0xBF98;
        unsigned int date = *(unsigned int*)0xBF90;
        unsigned char minute = *(unsigned char*)0xBF92, hour = *(unsigned char*)0xBF93;
        unsigned char year = date >> 9, month = (date >> 5) & 15, day = date & 31;
        gotoxy(26, 2);
        revers(1);
        cputs("  A2 RETRO CMD " A2RC_VERSION "  ");
        revers(0);
        gotoxy(28, 3);
        cputs("Two panels. One Apple II.");
        gotoxy(14, 5);
        cputs("A two-pane ProDOS file manager for the Apple IIe with 128 KB.");
        gotoxy(14, 6);
        cputs("It runs under ProDOS 8 only, at boot or from a selector.");
        gotoxy(14, 7);
        cputs("Free software under the GNU GPL v3, by Arnaud VERHILLE.");
        gotoxy(14, 9);
        /* ProDOS : annee sur 7 bits (0-39 = 2000-2039), mois 1-12, jour 1-31,
         * heure 0-23 -- deja en 24 heures. Une date hors bornes vaut absence. */
        if ((machid & 1) && month >= 1 && month <= 12 && day >= 1 && day <= 31 && hour < 24 && minute < 60)
            cprintf("%u %s %u, %02u:%02u", day, months[month - 1],
                    year < 40 ? 2000 + year : 1900 + year, hour, minute);
        else
            cputs("No clock: new files will carry no date.");
        gotoxy(14, 12);
        cputs("PLEASE WAIT, loading A2RETRO.CODE ...");
    }

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
    /* Jamais au-dela de $BEFF : la page globale ProDOS est a $BF00. */
    while (dst < (unsigned char*)0xBF00 && (n = fread(dst, 1, (unsigned char*)0xBF00 - dst < CHUNK ? (unsigned char*)0xBF00 - dst : CHUNK, f)) > 0) dst += n;
    fclose(f);

    /* A2 Retro Cmd ne revient jamais ici : il sort par le QUIT ProDOS. */
    ((void (*)(void))CODE_ADDR)();
    return 0;
}
