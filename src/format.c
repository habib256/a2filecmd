/* A2FILE/FORMAT.SYS -- formate un disque pour ProDOS, depuis A2 File
 * Cmd (touche F) ou Bitsy Bye, et revient a A2FC.
 *
 * Le formatage physique d'une disquette Disk II vient du ProDOS
 * Hyper-FORMAT de Jerry Hewett (1985, domaine public) et Gary Desrochers
 * (1989), tel qu'ADTPro (David Schmidt, GPL) l'a integre : voir
 * format_diskii.s. Les structures ProDOS (amorce, catalogue, table
 * d'allocation) sont ecrites ici par WRITE_BLOCK, en C, pour tout
 * peripherique de bloc : Disk II, SmartPort, disque dur, /RAM.
 *
 * La securite tient a trois choses : le disque d'ou tourne le programme
 * n'est jamais proposable ; la cible est decrite en clair (slot, lecteur,
 * type, nom actuel, taille) avec l'avertissement que tout sera perdu ; et
 * la confirmation exige de taper le mot ERASE en toutes lettres, Echap
 * annulant a chaque etape. Rien n'est ecrit avant ce mot. */
#include <stdio.h>
#include <string.h>
#include <conio.h>

#ifndef A2FC_VERSION
#define A2FC_VERSION "0.5"
#endif

unsigned char __fastcall__ mli_call(unsigned char cmd, void* parms);
unsigned char __fastcall__ driver_call(unsigned char unit, unsigned char cmd, unsigned char lc);
extern unsigned int driver_blocks;
extern unsigned int chain_addr;
void __fastcall__ chain_load(const char* path);
unsigned char __fastcall__ diskii_begin(unsigned char slotdrive);
unsigned char __fastcall__ diskii_track(unsigned char track);
void diskii_end(void);

#define DEVNUM (*(unsigned char*)0xBF30)
#define DEVCNT (*(unsigned char*)0xBF31)
#define DEVLST ((unsigned char*)0xBF32)
#define DEVADR ((unsigned int*)0xBF10)
#define BLOCK  ((unsigned char*)0x6800)   /* le tampon de bloc d'Hyper-FORMAT */

enum { KIND_DISKII, KIND_SMART, KIND_RAM, KIND_BLOCK };
static const char* const KIND_NAMES[] = { "Disk II 5.25\"", "SmartPort", "/RAM disk", "block device" };

struct Dev {
    unsigned char unit, kind, inuse, valid;
    char name[16];              /* le volume actuel, sans la barre */
    unsigned int blocks;
};
static struct Dev devs[9];
static unsigned char ndev;
static unsigned char boot_unit;
static char volname[16];
static struct Dev* target;

/* L'amorce ProDOS d'une disquette (bloc 0), celle d'Hyper-FORMAT ; le
 * bloc 1 reste a zero. */
static const unsigned char boot_code[] = {
    0x01,0x38,0xB0,0x03,0x4C,0x32,0xA1,0x86,0x43,0xC9,0x03,0x08,0x8A,0x29,0x70,0x4A,0x4A,0x4A,0x4A,0x09,0xC0,0x85,0x49,0xA0,
    0xFF,0x84,0x48,0x28,0xC8,0xB1,0x48,0xD0,0x3A,0xB0,0x0E,0xA9,0x03,0x8D,0x00,0x08,0xE6,0x3D,0xA5,0x49,0x48,0xA9,0x5B,0x48,
    0x60,0x85,0x40,0x85,0x48,0xA0,0x63,0xB1,0x48,0x99,0x94,0x09,0xC8,0xC0,0xEB,0xD0,0xF6,0xA2,0x06,0xBC,0x1D,0x09,0xBD,0x24,
    0x09,0x99,0xF2,0x09,0xBD,0x2B,0x09,0x9D,0x7F,0x0A,0xCA,0x10,0xEE,0xA9,0x09,0x85,0x49,0xA9,0x86,0xA0,0x00,0xC9,0xF9,0xB0,
    0x2F,0x85,0x48,0x84,0x60,0x84,0x4A,0x84,0x4C,0x84,0x4E,0x84,0x47,0xC8,0x84,0x42,0xC8,0x84,0x46,0xA9,0x0C,0x85,0x61,0x85,
    0x4B,0x20,0x12,0x09,0xB0,0x68,0xE6,0x61,0xE6,0x61,0xE6,0x46,0xA5,0x46,0xC9,0x06,0x90,0xEF,0xAD,0x00,0x0C,0x0D,0x01,0x0C,
    0xD0,0x6D,0xA9,0x04,0xD0,0x02,0xA5,0x4A,0x18,0x6D,0x23,0x0C,0xA8,0x90,0x0D,0xE6,0x4B,0xA5,0x4B,0x4A,0xB0,0x06,0xC9,0x0A,
    0xF0,0x55,0xA0,0x04,0x84,0x4A,0xAD,0x02,0x09,0x29,0x0F,0xA8,0xB1,0x4A,0xD9,0x02,0x09,0xD0,0xDB,0x88,0x10,0xF6,0x29,0xF0,
    0xC9,0x20,0xD0,0x3B,0xA0,0x10,0xB1,0x4A,0xC9,0xFF,0xD0,0x33,0xC8,0xB1,0x4A,0x85,0x46,0xC8,0xB1,0x4A,0x85,0x47,0xA9,0x00,
    0x85,0x4A,0xA0,0x1E,0x84,0x4B,0x84,0x61,0xC8,0x84,0x4D,0x20,0x12,0x09,0xB0,0x17,0xE6,0x61,0xE6,0x61,0xA4,0x4E,0xE6,0x4E,
    0xB1,0x4A,0x85,0x46,0xB1,0x4C,0x85,0x47,0x11,0x4A,0xD0,0xE7,0x4C,0x00,0x20,0x4C,0x3F,0x09,0x26,0x50,0x52,0x4F,0x44,0x4F,
    0x53,0x20,0x20,0x20,0x20,0x20,0x20,0x20,0x20,0x20,0xA5,0x60,0x85,0x44,0xA5,0x61,0x85,0x45,0x6C,0x48,0x00,0x08,0x1E,0x24,
    0x3F,0x45,0x47,0x76,0xF4,0xD7,0xD1,0xB6,0x4B,0xB4,0xAC,0xA6,0x2B,0x18,0x60,0x4C,0xBC,0x09,0xA9,0x9F,0x48,0xA9,0xFF,0x48,
    0xA9,0x01,0xA2,0x00,0x4C,0x79,0xF4,0x20,0x58,0xFC,0xA0,0x1C,0xB9,0x50,0x09,0x99,0xAE,0x05,0x88,0x10,0xF7,0x4C,0x4D,0x09,
    0xAA,0xAA,0xAA,0xA0,0xD5,0xCE,0xC1,0xC2,0xCC,0xC5,0xA0,0xD4,0xCF,0xA0,0xCC,0xCF,0xC1,0xC4,0xA0,0xD0,0xD2,0xCF,0xC4,0xCF,
    0xD3,0xA0,0xAA,0xAA,0xAA,0xA5,0x53,0x29,0x03,0x2A,0x05,0x2B,0xAA,0xBD,0x80,0xC0,0xA9,0x2C,0xA2,0x11,0xCA,0xD0,0xFD,0xE9,
    0x01,0xD0,0xF7,0xA6,0x2B,0x60,0xA5,0x46,0x29,0x07,0xC9,0x04,0x29,0x03,0x08,0x0A,0x28,0x2A,0x85,0x3D,0xA5,0x47,0x4A,0xA5,
    0x46,0x6A,0x4A,0x4A,0x85,0x41,0x0A,0x85,0x51,0xA5,0x45,0x85,0x27,0xA6,0x2B,0xBD,0x89,0xC0,0x20,0xBC,0x09,0xE6,0x27,0xE6,
    0x3D,0xE6,0x3D,0xB0,0x03,0x20,0xBC,0x09,0xBC,0x88,0xC0,0x60,0xA5,0x40,0x0A,0x85,0x53,0xA9,0x00,0x85,0x54,0xA5,0x53,0x85,
    0x50,0x38,0xE5,0x51,0xF0,0x14,0xB0,0x04,0xE6,0x53,0x90,0x02,0xC6,0x53,0x38,0x20,0x6D,0x09,0xA5,0x50,0x18,0x20,0x6F,0x09,
    0xD0,0xE3,0xA0,0x7F,0x84,0x52,0x08,0x28,0x38,0xC6,0x52,0xF0,0xCE,0x18,0x08,0x88,0xF0,0xF5,0xBD,0x8C,0xC0,0x10,0xFB,0x00,
    0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00 };

/* ---------------------------------------------------------------------- */
/* Ecran                                                                  */
/* ---------------------------------------------------------------------- */

static void title(const char* sub)
{
    clrscr();
    gotoxy(0, 0);
    revers(1);
    cprintf("%-79.79s", "  A2 FILE CMD " A2FC_VERSION "  -  FORMAT A DISK FOR PRODOS");
    revers(0);
    gotoxy(1, 1);
    cputs(sub);
}

static void bar(const char* text)
{
    gotoxy(0, 23);
    revers(1);
    cprintf("%-79.79s", text);
    revers(0);
}

static void error_line(unsigned char row, unsigned char code)
{
    const char* what = "ProDOS error";
    if (code == 0x2B) what = "the disk is write protected";
    else if (code == 0x27) what = "I/O error, the disk may be missing or damaged";
    else if (code == 0x28) what = "no device connected there";
    else if (code == 0x2E) what = "the disk was switched";
    gotoxy(1, row);
    cprintf("Failed: %s ($%02X).", what, code);
}

/* ---------------------------------------------------------------------- */
/* Les peripheriques                                                      */
/* ---------------------------------------------------------------------- */

static unsigned char slot_of(unsigned char unit) { return (unit >> 4) & 7; }
/* Blocs de la carte des blocs libres : 4096 blocs par bloc, sans debordement
 * 16 bits pour une partition de 65535 blocs (32 Mo). */
static unsigned char bitmap_size(unsigned int total) { return (unsigned char)((total >> 12) + ((total & 4095) != 0)); }
static unsigned char drive_of(unsigned char unit) { return (unit >> 7) + 1; }

/* Le type d'apres la signature de la ROM du slot ($Cs01/03/05/07 et
 * $CsFF), comme Hyper-FORMAT ; le pilote /RAM se reconnait a son adresse
 * $FF00 dans DEVADR. Tout le reste est un peripherique de bloc sans
 * formatage physique : on n'y ecrit que les structures ProDOS. */
/* La ROM de la carte qui pilote l'unite : celle du slot du pilote quand
 * ProDOS l'appelle en ROM ($C100-$C7FF), ce qui suit aussi un troisieme ou
 * quatrieme lecteur SmartPort renumerote en slot 2 ; sinon celle du slot de
 * l'unite (pilote interne de ProDOS : Disk II). */
static const unsigned char* rom_of(unsigned char unit)
{
    unsigned int drv = DEVADR[unit >> 4];
    if (drv >= 0xC100 && drv < 0xC800) return (const unsigned char*)(drv & 0xFF00);
    return (const unsigned char*)(0xC000 + slot_of(unit) * 256);
}

static unsigned char kind_of(unsigned char unit)
{
    const unsigned char* rom = rom_of(unit);
    if (DEVADR[unit >> 4] == 0xFF00) return KIND_RAM;
    if (rom[1] == 0x20 && rom[3] == 0x00 && rom[5] == 0x03) {
        if (rom[0xFF] == 0x00 && DEVADR[unit >> 4] >= 0xD000) return KIND_DISKII;
        if (rom[7] == 0x00) return KIND_SMART;      /* $Cn07 = 0 : interface SmartPort */
    }
    return KIND_BLOCK;
}

static void scan_devices(void)
{
    unsigned char i, n = DEVCNT + 1, len;
    static unsigned char parms[4], online[16], gfi[18];
    static char path[18];
    ndev = 0;
    for (i = 0; i < n && ndev < 9; ++i) {
        struct Dev* d = &devs[ndev];
        d->unit = DEVLST[i] & 0xF0;
        d->kind = kind_of(d->unit);
        d->inuse = d->unit == boot_unit;
        d->name[0] = 0;
        d->valid = 0;
        d->blocks = 0;
        /* ON_LINE : le nom du volume de l'unite, ou son erreur */
        parms[0] = 2; parms[1] = d->unit;
        parms[2] = (unsigned char)((unsigned)online & 0xFF);
        parms[3] = (unsigned char)((unsigned)online >> 8);
        len = mli_call(0xC5, parms) ? 0 : online[0] & 0x0F;
        if (len) {
            memcpy(d->name, online + 1, len);
            d->name[len] = 0;
            d->valid = 1;
            /* GET_FILE_INFO sur "/NOM" : aux_type = la taille du volume */
            path[0] = len + 1; path[1] = '/'; memcpy(path + 2, d->name, len);
            gfi[0] = 0x0A;
            gfi[1] = (unsigned char)((unsigned)path & 0xFF);
            gfi[2] = (unsigned char)((unsigned)path >> 8);
            if (!mli_call(0xC4, gfi)) d->blocks = gfi[5] | ((unsigned int)gfi[6] << 8);
        }
        /* STATUS du pilote : le nombre de blocs sans volume, et la taille
         * reelle quand un en-tete annonce plus que le disque. L'en-tete
         * l'emporte quand il annonce moins : le pilote /RAM de ProDOS rend
         * 255 blocs pour un volume de 127, et il n'y a bien que 128 blocs.
         * Un pilote loge au-dessus de $D000 (Disk II, /RAM) vit en banque 1
         * de la carte langage : l'appel direct doit la commuter. */
        if (d->kind == KIND_DISKII) d->blocks = 280;   /* son STATUS ne compte pas les blocs, et un en-tete peut mentir */
        else if (!driver_call(d->unit, 0, DEVADR[d->unit >> 4] >= 0xD000) && driver_blocks && (!d->blocks || driver_blocks < d->blocks)) d->blocks = driver_blocks;
        if (d->kind == KIND_RAM && d->blocks > 127) d->blocks = 127;   /* STATUS dit 255 : 128 blocs, dont ProDOS en garde un */
        ++ndev;
    }
}

static void list_devices(void)
{
    unsigned char i;
    title("This ERASES EVERYTHING on the disk you choose. Read the list carefully.");
    gotoxy(1, 3);
    cputs("     Where             Type            Current volume     Size");
    for (i = 0; i < ndev; ++i) {
        struct Dev* d = &devs[i];
        static char shown[20];
        if (d->valid) sprintf(shown, "/%s", d->name); else strcpy(shown, "(no ProDOS volume)");
        gotoxy(1, 4 + i);
        cprintf("  %c  Slot %u, drive %u  %-15s %-18s %5u blocks%s", '1' + i, slot_of(d->unit), drive_of(d->unit),
                KIND_NAMES[d->kind], shown, d->blocks, d->inuse ? "  IN USE" : "");
    }
    gotoxy(1, 6 + ndev);
    cputs("Press the number of the disk to format. Nothing is written before you confirm.");
    bar("1-9 Choose a disk    ESC Back to A2 File Cmd");
}

/* ---------------------------------------------------------------------- */
/* Les structures ProDOS                                                  */
/* ---------------------------------------------------------------------- */

static unsigned char write_block(unsigned char unit, unsigned int block)
{
    static unsigned char parms[6];
    parms[0] = 3; parms[1] = unit;
    parms[2] = 0x00; parms[3] = 0x68;
    parms[4] = (unsigned char)(block & 0xFF); parms[5] = (unsigned char)(block >> 8);
    return mli_call(0x81, parms);
}

static unsigned char read_block(unsigned char unit, unsigned int block)
{
    static unsigned char parms[6];
    parms[0] = 3; parms[1] = unit;
    parms[2] = 0x00; parms[3] = 0x68;
    parms[4] = (unsigned char)(block & 0xFF); parms[5] = (unsigned char)(block >> 8);
    return mli_call(0x80, parms);
}

/* Amorce, catalogue racine (blocs 2-5), table d'allocation (des le bloc 6).
 * Rend 0 ou le code d'erreur. */
static unsigned char write_structures(struct Dev* d)
{
    unsigned char r, len = strlen(volname), i;
    unsigned int total = d->blocks, bitmap_blocks = bitmap_size(total), used = 6 + bitmap_blocks, b;
    static const unsigned char timep[1] = { 0 };
    memset(BLOCK, 0, 512);
    memcpy(BLOCK, boot_code, sizeof boot_code);
    if ((r = write_block(d->unit, 0))) return r;
    memset(BLOCK, 0, 512);
    if ((r = write_block(d->unit, 1))) return r;
    /* les blocs 3, 4, 5 : chainage seulement */
    for (b = 3; b <= 5; ++b) {
        memset(BLOCK, 0, 512);
        BLOCK[0] = (unsigned char)(b - 1);
        BLOCK[2] = b < 5 ? (unsigned char)(b + 1) : 0;
        if ((r = write_block(d->unit, b))) return r;
    }
    /* le bloc 2 : l'en-tete du volume */
    mli_call(0x82, (void*)timep);           /* GET_TIME : $BF90-$BF93 a jour */
    memset(BLOCK, 0, 512);
    BLOCK[2] = 3;
    BLOCK[4] = 0xF0 | len;
    memcpy(BLOCK + 5, volname, len);
    memcpy(BLOCK + 0x1C, (void*)0xBF90, 4);   /* date et heure de creation */
    BLOCK[0x20] = 0;                          /* version ProDOS 1.0 */
    BLOCK[0x21] = 0;
    BLOCK[0x22] = 0xC3;                       /* acces : tout permis */
    BLOCK[0x23] = 0x27;                       /* 39 octets par entree */
    BLOCK[0x24] = 0x0D;                       /* 13 entrees par bloc */
    BLOCK[0x25] = 0; BLOCK[0x26] = 0;         /* aucun fichier */
    BLOCK[0x27] = 6; BLOCK[0x28] = 0;         /* la table commence au bloc 6 */
    BLOCK[0x29] = (unsigned char)(total & 0xFF);
    BLOCK[0x2A] = (unsigned char)(total >> 8);
    if ((r = write_block(d->unit, 2))) return r;
    /* la table d'allocation : un bit par bloc, 1 = libre */
    for (i = 0; i < bitmap_blocks; ++i) {
        memset(BLOCK, 0, 512);
        for (b = 0; b < 4096; ++b) {
            unsigned int block = ((unsigned int)i << 12) + b;
            if (block >= used && block < total) BLOCK[b >> 3] |= 0x80 >> (b & 7);
        }
        if ((r = write_block(d->unit, 6 + i))) return r;
    }
    /* relecture de l'amorce et de l'en-tete : la preuve que le disque
     * repond et que ses deux premiers secteurs sont bons */
    if (d->kind != KIND_RAM) {              /* le /RAM ne garde pas ses blocs d'amorce */
        memset(BLOCK, 0, 512);
        if ((r = read_block(d->unit, 0))) return r;
        if (memcmp(BLOCK, boot_code, sizeof boot_code)) return 0x27;
    }
    memset(BLOCK, 0, 512);
    if ((r = read_block(d->unit, 2))) return r;
    if (BLOCK[4] != (0xF0 | len) || memcmp(BLOCK + 5, volname, len)) return 0x27;
    return 0;
}

/* ---------------------------------------------------------------------- */
/* Les etapes                                                             */
/* ---------------------------------------------------------------------- */

/* Rend 0 si Echap. */
static unsigned char ask_name(void)
{
    unsigned char len = 0;
    char key;
    title("Step 2 of 3: the name of the new volume.");
    gotoxy(1, 3);
    cprintf("Disk: slot %u, drive %u, %s, %u blocks.", slot_of(target->unit), drive_of(target->unit), KIND_NAMES[target->kind], target->blocks);
    gotoxy(1, 5);
    cputs("A ProDOS volume name: a letter, then letters, digits or periods, 15 at most.");
    gotoxy(1, 6);
    cputs("RETURN alone names it BLANK.");
    bar("RETURN Accept    DEL Erase    ESC Back to A2 File Cmd");
    volname[0] = 0;
    for (;;) {
        gotoxy(1, 8);
        cprintf("New volume name: /%s_   ", volname);
        key = cgetc();
        if (key == 27) return 0;
        if (key == 13) { if (!len) strcpy(volname, "BLANK"); return 1; }
        if (key == 8 || key == 127) { if (len) volname[--len] = 0; continue; }
        if (key >= 'a' && key <= 'z') key -= 32;
        if (len >= 15) continue;
        if ((key >= 'A' && key <= 'Z') || (len && ((key >= '0' && key <= '9') || key == '.'))) {
            volname[len++] = key;
            volname[len] = 0;
        }
    }
}

/* Rend 1 seulement si l'utilisateur a tape ERASE puis RETURN. */
static unsigned char confirm(void)
{
    char typed[8];
    unsigned char len = 0;
    char key;
    title("Step 3 of 3: the final confirmation.");
    gotoxy(1, 3);
    revers(1);
    cputs("  WARNING  ");
    revers(0);
    gotoxy(1, 5);
    cprintf("You are about to FORMAT the disk in slot %u, drive %u (%s),", slot_of(target->unit), drive_of(target->unit), KIND_NAMES[target->kind]);
    gotoxy(1, 6);
    if (target->valid) cprintf("currently the volume /%s, %u blocks.", target->name, target->blocks);
    else cprintf("which holds no ProDOS volume, %u blocks.", target->blocks);
    gotoxy(1, 8);
    revers(1);
    cputs(" EVERYTHING ON THAT DISK WILL BE LOST FOREVER. ");
    revers(0);
    gotoxy(1, 10);
    cprintf("The new, empty volume will be named /%s.", volname);
    gotoxy(1, 12);
    cputs("To confirm, type the word ERASE in capital letters, then press RETURN.");
    gotoxy(1, 13);
    cputs("Anything else, or ESC, cancels without touching the disk.");
    bar("Type ERASE then RETURN to format    ESC Cancel");
    typed[0] = 0;
    for (;;) {
        gotoxy(1, 15);
        cprintf("> %s_   ", typed);
        key = cgetc();
        if (key == 27) return 0;
        if (key == 13) return strcmp(typed, "ERASE") == 0;
        if (key == 8 || key == 127) { if (len) typed[--len] = 0; continue; }
        if (len < 7 && key >= 32 && key < 127) { typed[len++] = key; typed[len] = 0; }
    }
}

/* Rend 0 ou le code d'erreur. */
static unsigned char do_format(void)
{
    unsigned char r = 0, t;
    title("Formatting. Do not open the drive door or switch off the computer.");
    gotoxy(1, 3);
    cprintf("Slot %u, drive %u, %s -> /%s", slot_of(target->unit), drive_of(target->unit), KIND_NAMES[target->kind], volname);
    bar("Please wait ...");
    if (target->kind == KIND_DISKII) {
        r = diskii_begin((unsigned char)((slot_of(target->unit) << 4) | (drive_of(target->unit) == 2 ? 0x80 : 0)));
        for (t = 0; t < 35 && !r; ++t) {
            gotoxy(1, 5);
            cprintf("Track %2u of 35 ", t + 1);
            r = diskii_track(t);
        }
        diskii_end();
        if (r) return r;
    } else if (target->kind == KIND_RAM) {
        r = driver_call(target->unit, 3, DEVADR[target->unit >> 4] >= 0xD000);
        if (r) return r;
    } else if (target->kind == KIND_SMART && (rom_of(target->unit)[0xFE] & 0x08)) {   /* SmartPort : FORMAT vise l'unite ; une autre carte pourrait formater tout le disque */
        r = driver_call(target->unit, 3, DEVADR[target->unit >> 4] >= 0xD000);
        if (r) return r;
    }
    gotoxy(1, 5);
    cputs("Writing the ProDOS boot blocks, directory and bitmap ...");
    r = write_structures(target);
    if (r) return r;
    gotoxy(1, 6);
    cputs("Read back and verified.");
    return 0;
}

int main(void)
{
    char key;
    unsigned char r;
    videomode(VIDEOMODE_80COL);
    boot_unit = DEVNUM & 0xF0;
    for (;;) {
        scan_devices();
        list_devices();
        for (;;) {
            key = cgetc();
            if (key == 27) goto back;
            if (key >= '1' && key < '1' + ndev) break;
        }
        target = &devs[key - '1'];
        if (target->inuse) {
            gotoxy(1, 8 + ndev);
            revers(1);
            cputs(" That disk holds the running program: it cannot be formatted from here. ");
            revers(0);
            cgetc();
            continue;
        }
        if (target->blocks < 7 + bitmap_size(target->blocks)) {
            gotoxy(1, 8 + ndev);
            revers(1);
            cputs(" No disk, or its size is unknown: nothing to format. ");
            revers(0);
            cgetc();
            continue;
        }
        if (!ask_name()) continue;
        if (!confirm()) continue;
        r = do_format();
        if (r) {
            error_line(8, r);
            gotoxy(1, 9);
            cputs("The disk may be unusable until formatted again.");
        } else {
            gotoxy(1, 8);
            cprintf("Done: /%s, %u blocks, %u free.", volname, target->blocks, target->blocks - 6 - bitmap_size(target->blocks));
        }
        bar("Any key: back to the list    ESC: A2 File Cmd");
        key = cgetc();
        if (key == 27) break;
    }
back:
    clrscr();
    cputs("Loading A2 File Cmd ...");
    /* Le prefixe ProDOS est ramene a la racine du volume : lance depuis
     * Bitsy Bye, FORMAT.SYSTEM herite du dossier A2FILE, et A2FILE.SYSTEM
     * cherche A2FILE/A2FILE.CODE depuis la racine. */
    {
        static unsigned char parms[3], prefix[65];
        unsigned char i;
        parms[0] = 1;
        parms[1] = (unsigned char)((unsigned)prefix & 0xFF);
        parms[2] = (unsigned char)((unsigned)prefix >> 8);
        if (!mli_call(0xC7, parms) && prefix[0] > 1) {
            for (i = 2; i <= prefix[0] && prefix[i] != '/'; ++i) {}
            prefix[0] = i;                 /* "/VOL/" : la racine, barre finale comprise */
            prefix[i] = '/';
            mli_call(0xC6, parms);
        }
    }
    chain_addr = 0x2000;
    {
        static unsigned char gfi[18];
        static const char in_dir[] = "\x14" "A2FILE/A2FILE.SYSTEM";
        gfi[0] = 0x0A;
        gfi[1] = (unsigned char)((unsigned)in_dir & 0xFF);
        gfi[2] = (unsigned char)((unsigned)in_dir >> 8);
        chain_load(mli_call(0xC4, gfi) ? "A2FILE.SYSTEM" : "A2FILE/A2FILE.SYSTEM");
    }
    return 0;
}
