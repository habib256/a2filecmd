/* music.h -- la Mockingboard joue le theme d'accueil. Voir music.s.
 *
 * Sans carte, music_detect rend 0 et les deux autres ne font rien : le jeu
 * est identique, les bruitages de sfx.s continuent seuls sur le haut-parleur. */
#ifndef MUSIC_H
#define MUSIC_H

unsigned char music_detect(void);   /* balaye les slots 7..1 ; 0 = absente */
void music_play(void);              /* le theme d'accueil, en boucle, a 50 Hz */
void music_stop(void);              /* silence net, timer desarme */

#endif /* MUSIC_H */
