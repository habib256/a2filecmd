/* music.h -- la Mockingboard joue les musiques du disque, six voix en
 * stereo (puce 1 a gauche, puce 2 a droite). Voir music.s.
 *
 * Chaque musique est un fichier MUSIC/<NOM>.MB au format MB1. La page qui la
 * veut le nomme par une ligne MU : "MU NOM.MB" pose le theme de la zone,
 * "MU +NOM.MB" une surcouche pour cette page (combat, mort, victoire),
 * "MU -" le silence. Dans le Marais, le moteur ne consulte cette directive
 * qu'à l'entrée dans une nouvelle clairière ; hors clairières, elle lance les
 * morceaux scénarisés (accueil, village, prologue, fins). Chaque flux est joué
 * une fois puis s'arrête : aucune page interne à une clairière ne le relance
 * et aucun flux ne boucle.
 *
 * Deux tampons, 2 304 et 1 280 octets, chacun avec son curseur : le nouveau flux se lit dans
 * celui qui ne joue pas, l'autre continue pendant la lecture, et la zone
 * reprend ou elle en etait apres une surcouche. La musique ne s'arrete
 * jamais pour un chargement. Sans carte, music_detect rend 0 et rien n'est
 * lu ni ecrit. */
#ifndef MUSIC_H
#define MUSIC_H

#define MUSIC_ZONE     2304         /* moitie 0 : les themes de zone (max 2 285 o) */
/* 1 280 et non 1 216. Le menu MAP avait pris ces 64 octets, la plus grosse
 * surcouche faisant alors 1 216 octets a l'octet pres ; la reprise des
 * partitions « d'un cran, avec la batterie » a porte VICTOIRE.MB a 1 265 et
 * COMBAT.MB a 1 228. Le levier est rendu a la musique : il ne restait que
 * quinze octets de marge, et une surcouche refusee a la fabrication aurait
 * coute plus cher que 64 octets de moteur. */
#define MUSIC_OVER     1280         /* moitie 1 : combat, mort, victoire */
#define MUSIC_BUF_SIZE (MUSIC_ZONE + MUSIC_OVER)   /* = .res de _music_buf dans music.s */
extern unsigned char music_buf[MUSIC_BUF_SIZE];

unsigned char music_detect(void);   /* balaye les slots 7..1 ; 0 = absente */
void __fastcall__ music_select(unsigned char half);  /* 0 zone, 1 surcouche ; a l'arret ou en pause */
void music_play(void);              /* demarre le demi-tampon une fois, a 50 Hz */
void music_pause(void);             /* mixeur ferme, timer desarme, curseur intact */
void music_resume(void);            /* apres music_pause */
void music_continue(void);          /* reprend le demi-tampon selectionne ou il en etait */
void music_stop(void);              /* silence net, timer desarme */
void music_fade_out(void);          /* s'efface en 0,9 s, le flux continue d'avancer */
void music_fade_in(void);           /* remonte depuis l'attenuation courante */
unsigned char music_fading(void);   /* 0 quand le fondu est fini */

#endif /* MUSIC_H */
