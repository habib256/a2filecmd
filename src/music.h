/* music.h -- the Mockingboard plays the music from the disk, six voices in
 * stereo (chip 1 on the left, chip 2 on the right). See music.s.
 *
 * Each piece of music is a file MUSIC/<NAME>.MB in MB1 format. The page that
 * wants it names it with an MU line: "MU NAME.MB" sets the zone theme,
 * "MU +NAME.MB" an overlay for that page (battle, death, victory),
 * "MU -" silence. In the Swamp, the engine consults this directive only
 * on entering a new clearing; outside clearings, it starts the scripted
 * pieces (welcome, village, prologue, endings). Each stream is played once
 * and then stops: no page inside a clearing restarts it and no stream
 * loops, except BATTLE.MB while the battle is active.
 *
 * Two AUX buffers, 2,304 and 1,280 bytes, each with its own cursor: the new
 * stream is read into the one that is not playing, the other keeps going
 * during the read, and the zone resumes where it was after an overlay. The
 * music never stops for a load. A 256-byte MAIN buffer serves the disk.
 * Without a card, music_detect returns 0 and no piece is loaded. */
#ifndef MUSIC_H
#define MUSIC_H

#define MUSIC_ZONE     2304         /* half 0: the zone themes (current max 2,277 bytes) */
/* 1,280 and not 1,216. The MAP menu had taken those 64 bytes, the biggest
 * overlay then being 1,216 bytes to the byte; reworking the scores "one
 * notch up, with the drums" brought VICTORY.MB to 1,265 and BATTLE.MB to
 * 1,228. The lever is given back to the music: only fifteen bytes of margin
 * were left, and an overlay refused at build time would have cost more
 * than 64 bytes of engine. */
#define MUSIC_OVER     1280         /* half 1: battle, death, victory */
#define MUSIC_BUF_SIZE (MUSIC_ZONE + MUSIC_OVER)   /* total AUX capacity */
/* Resident bytes live in AUX $1000-$1DFF; only this staging page is MAIN. */
#define MUSIC_STAGE 256
extern unsigned char music_buf[MUSIC_STAGE];
extern unsigned char music_active;  /* 1 while a stream plays (or is paused) */
void __fastcall__ music_store(unsigned int offset, unsigned int count);
void __fastcall__ music_set_loop(unsigned char loop);

unsigned char music_detect(void);   /* scans slots 7..1; 0 = absent */
void __fastcall__ music_select(unsigned char half);  /* 0 zone, 1 overlay; when stopped or paused */
void music_play(void);              /* starts the half-buffer once, at 50 Hz */
void music_pause(void);             /* mixer closed, timer disarmed, cursor intact */
void music_resume(void);            /* after music_pause */
void music_continue(void);          /* resumes the selected half-buffer where it was */
void music_stop(void);              /* clean silence, timer disarmed */
void music_fade_out(void);          /* fades out in 0.9 s, the stream keeps advancing */
void music_fade_in(void);           /* comes back up from the current attenuation */
unsigned char music_fading(void);   /* 0 when the fade is finished */

#endif /* MUSIC_H */
