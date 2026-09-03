/* music.h -- la Mockingboard joue les musiques du disque, six voix en
 * stereo (puce 1 a gauche, puce 2 a droite). Voir music.s.
 *
 * Chaque musique est un fichier MUSIC/<NOM>.MB au format MB1. La page qui la
 * veut le nomme par une ligne MU : "MU NOM.MB" pose le theme de la zone,
 * "MU +NOM.MB" une surcouche pour cette page (combat, mort, victoire),
 * "MU -" le silence, et une page sans MU laisse la musique continuer -- ou
 * revient au theme de zone si une surcouche jouait. Le disque n'est lu que
 * quand le nom change : deux pages d'une meme clairiere ne relancent rien.
 *
 * Deux demi-tampons, chacun avec son curseur : le nouveau flux se lit dans
 * celui qui ne joue pas, l'autre continue pendant la lecture, et la zone
 * reprend ou elle en etait apres une surcouche. La musique ne s'arrete
 * jamais pour un chargement. Sans carte, music_detect rend 0 et rien n'est
 * lu ni ecrit. */
#ifndef MUSIC_H
#define MUSIC_H

#define MUSIC_BUF_SIZE 2560         /* = .res de _music_buf dans music.s */
#define MUSIC_HALF     1280         /* un demi-tampon : la plus grosse piece fait 1 058 o */
extern unsigned char music_buf[MUSIC_BUF_SIZE];

unsigned char music_detect(void);   /* balaye les slots 7..1 ; 0 = absente */
void __fastcall__ music_select(unsigned char half);  /* 0 zone, 1 surcouche ; a l'arret ou en pause */
void music_play(void);              /* (re)demarre le demi-tampon selectionne, a 50 Hz */
void music_pause(void);             /* mixeur ferme, timer desarme, curseur intact */
void music_resume(void);            /* apres music_pause */
void music_continue(void);          /* reprend le demi-tampon selectionne ou il en etait */
void music_stop(void);              /* silence net, timer desarme */

#endif /* MUSIC_H */
