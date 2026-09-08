/* A2FILE.SYSTEM : le lanceur ProDOS d'A2 File Cmd.
 *
 * ProDOS charge tout programme SYS en $2000 et lui donne la main. Or A2 File
 * Cmd tourne en $4000 et occupe presque tout jusqu'a $BEFF : il ne PEUT pas
 * etre un SYS. Ce petit lanceur en est un, et lit le vrai programme a sa
 * place.
 *
 * A2FILE.CODE n'est pas un binaire plat : c'est une image a charge separee.
 * Ses 3 premiers kilo-octets vont en $1000 -- du code destine a la carte
 * langage, que crt0.s recopie en $D400 avant que main() n'efface la RAM
 * basse. Le reste va en $4000, ou commence l'execution. Un BLOAD ne saurait
 * pas faire cela : le fichier n'est pas BRUNable, il se lance par ici. (Les
 * surcouches, A2FILE/IMAGE.PLG, c'est A2FC lui-meme qui les charge en
 * $1B00 quand il en a besoin.)
 *
 * Le prefixe ProDOS est celui du volume amorce : le lanceur ouvre
 * "A2FILE/A2FILE.CODE" en relatif, sans avoir a connaitre le nom du volume.
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
#define A2FC_VERSION "0.6.7"
#endif

/* src/loader_mli.s : poser le prefixe ProDOS sur le volume amorce avant de
 * sauter dans A2FC (voir la note dans ce fichier et devant l'appel plus bas). */
extern void set_boot_prefix(void);

#define CODE_ADDR   0x4000
#define CHUNK       1024
#define LC_STAGE    0x1000
#define LC_BYTES    0x0C00      /* l'image de la carte langage */
#define STAGE_BYTES 0x0C00      /* rien d'autre : la RAM au-dessus est aux surcouches */

/* Une ligne centree sur les 80 colonnes. */
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
        /* Un cadre, le titre en inverse, ce que le programme sait faire en
         * deux colonnes, ce qu'il demande, la licence, la date, et le
         * chargement en bas : la page qu'on lit le temps que la disquette
         * tourne. */
        chlinexy(0, 0, 80);
        chlinexy(0, 4, 80);
        for (n = 1; n < 4; ++n) { cputcxy(0, n, '|'); cputcxy(79, n, '|'); }
        revers(1);
        centre(2, "  A2 FILE CMD " A2FC_VERSION "  ");
        revers(0);
        centre(3, "Two panels. One Apple II.");
        centre(6, "A two-pane ProDOS file manager running natively on Apple IIe.");
        cputsxy(4, 8,  "Copy, move, rename, delete, tag, sort.");
        cputsxy(44, 8, "Text viewer, hex dump, text editor.");
        cputsxy(4, 9,  "HGR and DHGR pictures, full screen.");
        cputsxy(44, 9, "Mockingboard music player.");
        cputsxy(4, 10,  "Disk formatter, program launcher.");
        cputsxy(44, 10, "Mouse or keyboard: press ? for help.");
        cputsxy(4, 12, "Needs an enhanced Apple IIe, 128 KB, 80 columns, ProDOS 8.");
        cputsxy(4, 13, "Optional: a Mockingboard and an AppleMouse II, in any slot.");
        cputsxy(4, 15, "Free software under the GNU GPL v3, by Arnaud VERHILLE.");
        cputsxy(4, 16, "https://github.com/habib256/a2filecmd");
        gotoxy(4, 18);
        /* ProDOS : annee sur 7 bits (0-39 = 2000-2039), mois 1-12, jour 1-31,
         * heure 0-23 -- deja en 24 heures. Une date hors bornes vaut absence. */
        if ((machid & 1) && month >= 1 && month <= 12 && day >= 1 && day <= 31 && hour < 24 && minute < 60)
            cprintf("%u %s %u, %02u:%02u", day, months[month - 1],
                    year < 40 ? 2000 + year : 1900 + year, hour, minute);
        else
            cputs("No clock: new files will carry no date.");
        chlinexy(0, 20, 80);
        gotoxy(4, 22);
        cputs("PLEASE WAIT, loading A2FILE.CODE ...");
    }

    /* Le prefixe d'abord : A2FILE/A2FILE.CODE se lit en relatif. Au
     * demarrage a froid ProDOS l'a pose, Bitsy Bye aussi (le dossier du
     * .SYSTEM), mais la relance par "-A2FILE.SYSTEM" depuis BASIC.SYSTEM le
     * laisse VIDE : set_boot_prefix le refait alors du chemin complet que
     * BASIC.SYSTEM laisse en $0280, ou du volume amorce. Sans lui A2FC
     * s'ouvrirait sur la liste des volumes, sans A2FILE.CFG -- ou ne se
     * chargerait pas du tout, installe ailleurs qu'a la racine. */
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
    /* Jamais au-dela de $BEFF : la page globale ProDOS est a $BF00. */
    while (dst < (unsigned char*)0xBF00 && (n = fread(dst, 1, (unsigned char*)0xBF00 - dst < CHUNK ? (unsigned char*)0xBF00 - dst : CHUNK, f)) > 0) dst += n;
    fclose(f);

    /* A2 File Cmd ne revient jamais ici : il sort par le QUIT ProDOS. */
#ifdef A2FC_TRACE
    *(unsigned char*)0x03A2 = 1; *(unsigned char*)0x03A0 = 0; *(unsigned char*)0x03A1 = 0;
#endif
    ((void (*)(void))CODE_ADDR)();
    return 0;
}
