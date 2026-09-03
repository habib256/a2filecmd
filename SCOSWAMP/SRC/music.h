/* music.h -- la Mockingboard joue les musiques du disque. Voir music.s.
 *
 * Chaque musique est un fichier MUSIC/<NOM>.MB au format MB1 ; la page qui la
 * veut le nomme par une ligne "MU <NOM>.MB", et load_scene la charge dans
 * music_buf une fois ses propres lectures finies. Sans carte, music_detect
 * rend 0 et rien n'est lu ni ecrit : le jeu est identique, les bruitages de
 * sfx.s continuent seuls sur le haut-parleur. */
#ifndef MUSIC_H
#define MUSIC_H

#define MUSIC_BUF_SIZE 2560         /* = .res de _music_buf dans music.s */
extern unsigned char music_buf[MUSIC_BUF_SIZE];

unsigned char music_detect(void);   /* balaye les slots 7..1 ; 0 = absente */
void music_play(void);              /* joue music_buf en boucle, a 50 Hz */
void music_stop(void);              /* silence net, timer desarme */

#endif /* MUSIC_H */
