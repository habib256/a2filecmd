/*
 * MEMORY SWAP - Bascules video (texte 80 col / HGR plein / HGR mixte)
 *
 * Aucune copie d'ecran ici, et c'est le point important : le texte ne quitte
 * jamais $400-$7FF pendant qu'on est en graphique. Le decodeur RLE ecrit dans
 * $2000-$3FFF, le tampon d'E/S ProDOS vit en $800-$BFF (page texte 2), et rien
 * ne tourne entre deux appuis de touche. Revenir au texte, c'est donc juste
 * rallumer TXTSET.
 *
 * L'ancienne version sauvegardait et restaurait 2 Ko a chaque bascule -- deux
 * copies de 1 Ko, une par banque, l'ecran 80 colonnes etant a cheval sur les
 * deux -- soit ~4000 iterations de boucle C pour reecrire l'ecran avec ce
 * qu'il contenait deja. C'etait la lenteur des transitions, et les 2 Ko de BSS
 * partent avec (la memoire est LA contrainte du projet, cf. TODO.md).
 */

#include <stdint.h>

/* Soft switches Apple II */
#define TXTCLR  (*(volatile uint8_t*)0xC050)  /* Mode graphique */
#define TXTSET  (*(volatile uint8_t*)0xC051)  /* Mode texte */
#define MIXCLR  (*(volatile uint8_t*)0xC052)  /* Mode mixte OFF */
#define MIXSET  (*(volatile uint8_t*)0xC053)  /* Mode mixte ON */
#define LOWSCR  (*(volatile uint8_t*)0xC054)  /* Page 1 visible */
#define HISCR   (*(volatile uint8_t*)0xC055)  /* Page 2 visible */
#define LORES   (*(volatile uint8_t*)0xC056)  /* Low-res */
#define HIRES   (*(volatile uint8_t*)0xC057)  /* Hi-res */
#define STORE80ON  (*(volatile uint8_t*)0xC001)
#define STORE80OFF (*(volatile uint8_t*)0xC000)
#define RAMRDOFF   (*(volatile uint8_t*)0xC002)
#define RAMWRTOFF  (*(volatile uint8_t*)0xC004)
#define COL80OFF   (*(volatile uint8_t*)0xC00C)
#define COL80ON    (*(volatile uint8_t*)0xC00D)
#define DHIRESON   (*(volatile uint8_t*)0xC05E)
#define DHIRESOFF  (*(volatile uint8_t*)0xC05F)

static uint8_t current_mode = 0;               /* 0=texte, 1=HGR, 2=mixte */

/*
 * Entree en graphique : routage memoire, puis page HGR 1 visible.
 *
 * Les quatre impulsions AN3 programment la FIFO de l'observateur Le Chat
 * Mauve / Video-7 en COL140 : 80COL est sa ligne de donnee, le front d'AN3 son
 * horloge. Elles ne se jouent qu'ICI, a l'entree en graphique. Les rejouer a
 * chaque bascule plein <-> mixte ferait clignoter l'ecran pour rien, alors que
 * l'image est deja a l'antenne.
 *
 * Le mode double resolution reste eteint (DHIRESOFF en dernier) : c'est lui,
 * pas 80COL, qui decide du DHGR. On peut donc rallumer 80COL en mixte pour
 * avoir les 4 lignes du bas en 80 colonnes sans toucher a l'image.
 */
static void enter_graphics(void) {
    /* Le texte 80 colonnes route $400-$7FF (et $2000-$3FFF) par la RAM
     * auxiliaire. Retablir la RAM principale avant de montrer HGR page 1,
     * c'est la ou le decodeur a ecrit. */
    STORE80OFF = 1;
    RAMRDOFF = 1;
    RAMWRTOFF = 1;

    COL80ON = 1;
    DHIRESON = 1; DHIRESOFF = 1;
    DHIRESON = 1; DHIRESOFF = 1;
    COL80OFF = 1;

    TXTCLR = 1;   /* Mode graphique */
    HIRES = 1;    /* Hi-res */
    LOWSCR = 1;   /* Page 1 */
}

/*
 * HGR plein ecran
 */
void switch_to_hgr(void) {
    if (current_mode == 2) {
        /* Deja en graphique : une seule bascule suffit. */
        MIXCLR = 1;
        COL80OFF = 1;
    } else if (current_mode != 1) {
        enter_graphics();
        MIXCLR = 1;
    }
    current_mode = 1;
}

/*
 * HGR + 4 lignes de texte 80 colonnes en bas
 */
void switch_to_mixed(void) {
    if (current_mode != 1 && current_mode != 2) {
        enter_graphics();
    }
    /* Les 4 lignes du bas lisent la page texte entrelacee : sans 80COL elles
     * s'afficheraient en 40 colonnes, c'est-a-dire une colonne sur deux.
     *
     * Et il faut REMETTRE 80STORE, que enter_graphics venait de couper : le
     * mixte est le seul mode graphique ou l'on ECRIT du texte, et le firmware
     * 80 colonnes atteint la banque auxiliaire par 80STORE + PAGE2. Sans lui,
     * la moitie des caracteres part dans le vide et l'ecran affiche deux
     * textes entrelaces -- l'ancien dans les colonnes paires, le nouveau dans
     * les impaires. L'image ne bouge pas pour autant : sous 80STORE l'ecran
     * hi-res reste force sur la page 1 en banque principale. */
    STORE80ON = 1;
    COL80ON = 1;
    MIXSET = 1;
    current_mode = 2;
}

/*
 * Texte 80 colonnes
 */
void switch_to_text(void) {
    /* Rien a repeindre : $400-$7FF n'a pas bouge. On remet le routage que le
     * firmware 80 colonnes attend pour ses prochaines ecritures, on rallume
     * l'affichage 80 colonnes, et on rend le texte visible en dernier. */
    STORE80ON = 1;
    COL80ON = 1;
    TXTSET = 1;
    current_mode = 0;
}

/*
 * Fonction utilitaire : état actuel
 */
uint8_t get_current_mode(void) {
    return current_mode;
}
