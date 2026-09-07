; music.s -- la Mockingboard joue les musiques du disque, sur six voix.
;
; Un lecteur de flux MB1 (DOCS/MUSIQUE.md § 5.2) en interruption : le Timer 1
; du premier 6522 de la carte bat a 50 Hz, et chaque tick decode les paquets
; du flux jusqu'au prochain DELAY. Tout est en assembleur et en segment CODE :
; jamais en LC, ProDOS commute l'autre banque sous IRQ.
;
; Six voix : les Mockingboard A et C portent deux AY-3-8910, l'un derriere le
; VIA #1 en $Cn00, l'autre derriere le VIA #2 en $Cn80. Les voix 0-2 du flux
; vont a la premiere puce (a gauche sur POM2), les voix 3-5 a la seconde (a
; droite) : la voix v >= 3 s'ecrit dans la puce 2 sous le numero v-3.
;
; Trois regles apprises a la lecture de POM2 (DOCS/MUSIQUE.md § 1) :
;  - acquitter l'IRQ en ECRIVANT $7F dans l'IFR ($Cn0D), jamais en lisant un
;    registre : l'entree IRQ du Moniteur //e route $C100-$CFFF vers la ROM ;
;  - balayer les slots de $C7 a $C1 en sautant le 3 : POM2 met la carte en
;    slot 2 par defaut, et un //e muet en slot 3 y a son firmware 80 colonnes ;
;  - sans carte, aucune ecriture ne part : mb_slot = 0 et chaque entree le
;    teste d'abord. Le jeu reste identique, sfx.s continue seul.
;
; cc65 fait la plomberie ProDOS : `.interruptor` entre dans la table que
; scoswamp.cfg declare, le runtime fait ALLOC_INTERRUPT au lancement et
; DEALLOC a la sortie, et appelle music_irq avec la retenue a zero ; on la
; met a un si l'IRQ est la notre. ProDOS sauve A, X, Y et $FA-$FF autour du
; gestionnaire : ces six octets de page zero sont donc a nous, ici et hors
; IRQ (cc65 n'occupe que $80-$99).
;
; API C (music.h) :
;   unsigned char music_detect(void);   slot trouve (1-7) ou 0 ; initialise
;   void music_play(void);              joue le flux une seule fois
;   void music_stop(void);              silence net, timer desarme

        .setcpu "65C02"
        .export _music_detect, _music_play, _music_stop, _music_buf
        .export _music_store, _music_set_loop, aux_read_cur, aux_mirror_end
        .import popax
        .export _music_select, _music_pause, _music_resume, _music_continue
        .export _music_fade_out, _music_fade_in, _music_fading
        .interruptor music_irq
        .destructor  music_done         ; exit() coupe le timer avant DEALLOC

via     = $FA           ; pointeur vers $Cn00 (VIA #1) ou $Cn80 (VIA #2)
cur     = $FC           ; curseur de flux (copie de travail sous IRQ)
tmp     = $FE
tmp2    = $FF

; registres du 6522, offsets depuis $Cn00
VIA_ORB = $00
VIA_ORA = $01
DDRB    = $02
DDRA    = $03
T1CL    = $04
T1CH    = $05
ACR     = $0B
IFR     = $0D
IER     = $0E

; 50 Hz : 1 022 727 / 50 = 20 454,5 cycles ; periode effective = latch + 2
T1_50HZ = 20452
FADE_STEP = 3           ; ticks entre deux pas de fondu

.segment "BSS"
; Deux tampons AUX : 2304 octets (moitie 0, les themes de zone) et 1280 octets
; (moitie 1, les surcouches : combat, mort, victoire), lus depuis
; MUSIC/<NOM>.MB par music_load (scoswamp.c). MUSIC_ZONE et MUSIC_OVER de
; music.h disent les memes tailles. Chaque moitie garde son curseur : revenir
; a la zone apres un combat la reprend ou elle en etait, sans rien relire.
; Seule la page de transit ci-dessous est reservee en MAIN -- ou en RAM
; basse (LOWBSS) pour TOTAL, assemble avec -D LOWBUF : sa BSS
; principale est pleine, le jeu garde la sienne telle quelle.
.ifdef LOWBUF
.segment "LOWBSS"
.endif
_music_buf:     .res 256         ; staging disque, flux residents en AUX
.ifdef LOWBUF
.segment "BSS"
.endif
AUX_MUSIC = $1000
mb_slot:        .res 1
playing:        .res 1
_music_active   = playing       ; lu par TOTAL : 0 quand le flux est fini
        .export _music_active
paused:         .res 1
half:           .res 1          ; la moitie selectionnee, 0 ou 1
delay:          .res 1
cur_lo:         .res 1
cur_hi:         .res 1
saved:          .res 6          ; cur_lo, cur_hi, delay de chaque moitie
vols:           .res 6
; Le fondu : `atten` (0-15) se retranche de toute amplitude ecrite ; `fade`
; vaut 1 pour un fondu sortant (atten monte), 2 pour un entrant (atten
; descend), 0 sinon ; un pas tous les FADE_STEP ticks, soit 45 ticks = 0,9 s
; d'un bout a l'autre. `amps` garde la derniere amplitude brute de chaque
; voix pour pouvoir la reecrire attenuee.
atten:          .res 1
fade:           .res 1
fstep:          .res 1
amps:           .res 6
mix:            .res 2          ; R7 de chaque puce : tons et bruit par voix

.segment "RODATA"
        .include "ay_notes.inc"
; bits du mixeur R7 pour la voix 0-2 d'une puce : ton (bit v) et bruit (bit 3+v),
; actifs a ZERO ; les masques les eteignent.
tbit:   .byte $01, $02, $04
nbit:   .byte $08, $10, $20
tmask:  .byte $FE, $FD, $FB
nmask:  .byte $F7, $EF, $DF

.segment "CODE"

.macro  NEXT                    ; cur++
        inc cur
        bne :+
        inc cur+1
:
.endmacro

; via := $Cn00 d'apres mb_slot (VIA #1)
set_via:
        stz via
        lda mb_slot
        ora #$C0
        sta via+1
        rts

; via := la puce de la voix A (0-5) ; rend dans A le numero de voix dans la
; puce (0-2).
chip_of:
        cmp #3
        bcc :+
        sbc #3                  ; retenue deja a 1
        ldy #$80
        sty via
        rts
:       stz via
        rts

; Ecrit A dans le registre X de l'AY #1. Preserve X, detruit Y.
; Sequence BDIR/BC1 sur le port B : LATCH ($07), INACTIVE ($04), WRITE ($06),
; INACTIVE. PB2 (/RESET) reste haut.
ay_write:
        pha
        txa
        ldy #VIA_ORA
        sta (via),y
        ldy #VIA_ORB
        lda #$07
        sta (via),y
        lda #$04
        sta (via),y
        pla
        ldy #VIA_ORA
        sta (via),y
        ldy #VIA_ORB
        lda #$06
        sta (via),y
        lda #$04
        sta (via),y
        rts

; Mixeur ferme, trois volumes a zero -- sur la puce que `via` designe.
silence1:
        ldx #7
        lda #$3F
        jsr ay_write
        ldx #8
        lda #0
        jsr ay_write
        inx
        jsr ay_write
        inx
        jmp ay_write

; Les deux puces.
silence:
        stz via
        jsr silence1
        lda #$80
        sta via
        jsr silence1
        stz via
        rts

; Ports en sortie et /RESET bas puis haut -- sur la puce que `via` designe.
init1:
        lda #$FF
        ldy #DDRA
        sta (via),y
        ldy #DDRB
        sta (via),y
        ldy #VIA_ORB
        lda #$00
        sta (via),y
        lda #$04
        sta (via),y
        rts

; R7 := A sur les deux puces. $38 ouvre les tons A, B, C (bruit ferme),
; $3F ferme tout sans toucher aux amplitudes : c'est la pause.
mixer_set:
        sta tmp2
        stz via
        jsr mix1
        lda #$80
        sta via
        jsr mix1
        stz via
        rts
mix1:   ldx #7
        lda tmp2
        jmp ay_write

; R7 := mix[] sur les deux puces : la reouverture apres une pause, et le
; depart d'un flux (tons ouverts, bruit ferme).
mixer_restore:
        stz via
        ldx #7
        lda mix
        jsr ay_write
        lda #$80
        sta via
        ldx #7
        lda mix+1
        jsr ay_write
        stz via
        rts

; Le mixeur de la voix `tmp` (0-5) : entree C=1 -> bruit ouvert, ton coupe
; (percussion) ; C=0 -> ton ouvert, bruit coupe (note). Pose via sur sa puce.
mix_voice:
        php
        lda tmp
        cmp #3
        lda #0
        adc #0
        tax                     ; X = puce 0/1
        lda tmp
        jsr chip_of
        tay                     ; Y = voix 0-2 dans la puce
        lda mix,x
        plp
        bcs @noise
        and tmask,y
        ora nbit,y
        bra @w
@noise: ora tbit,y
        and nmask,y
@w:     sta mix,x
        ldx #7
        jmp ay_write

; tmp/tmp2 := adresse du demi-tampon selectionne.
set_base:
        lda #<AUX_MUSIC
        sta tmp
        lda #>AUX_MUSIC
        sta tmp2
        lda half
        beq :+
        lda #<2304
        clc
        adc tmp
        sta tmp
        lda #>2304
        adc tmp2
        sta tmp2
:       rts

; Z=1 si le compteur T1 a recule de 8 entre deux lectures a 8 cycles
; d'ecart : la sonde de 4am, reprise par Total Replay et par les tests de POM2.
t1_probe:
        ldy #T1CL
        lda (via),y
        sta tmp
        lda (via),y
        sec
        sbc tmp
        cmp #$F8
        rts

; ── unsigned char music_detect(void) ────────────────────────────────────
_music_detect:
        jsr init_aux_reader
        ldx #7
@slot:  cpx #3
        beq @next
        stx mb_slot
        jsr set_via
        jsr t1_probe
        bne @next
        jsr t1_probe
        bne @next
        ; trouvee : les deux VIA en sortie, les deux AY remis a zero
        jsr init1
        lda #$80
        sta via
        jsr init1
        stz via
        txa
        ldx #0
        rts
@next:  dex
        bne @slot
        stz mb_slot
        txa                     ; 0
        rts

; ── void music_play(void) ───────────────────────────────────────────────
_music_play:
        lda mb_slot
        beq @rts
        jsr set_via
        jsr silence
        lda #$38                ; tons ouverts, bruit ferme, sur les deux puces
        sta mix
        sta mix+1
        jsr mixer_restore
        jsr set_base            ; le flux commence apres l'en-tete de 8 octets
        lda tmp
        clc
        adc #8
        sta cur_lo
        lda tmp2
        adc #0
        sta cur_hi
        lda #1
        sta delay
        sta playing
        stz paused
        lda #12
        ldx #5
:       sta vols,x
        stz amps,x
        dex
        bpl :-
        jsr fade_in_setup
        ldy #ACR                ; T1 continu
        lda #$40
        sta (via),y
        ldy #T1CL
        lda #<T1_50HZ
        sta (via),y
        ldy #T1CH
        lda #>T1_50HZ
        sta (via),y             ; charge et demarre
        ldy #IFR
        lda #$7F
        sta (via),y
        ldy #IER                ; autoriser T1
        lda #$C0
        sta (via),y
@rts:   rts

; ── void music_stop(void) ───────────────────────────────────────────────
_music_stop:
music_done:
        lda mb_slot
        beq @rts
        stz playing
        stz paused
        stz fade
        stz atten
        jsr set_via
        ldy #IER                ; interdire T1
        lda #$40
        sta (via),y
        ldy #IFR
        lda #$7F
        sta (via),y
        jmp silence
@rts:   rts

; ── void __fastcall__ music_select(unsigned char half) ──────────────────
; Change de demi-tampon en gardant le curseur de chacun. A appeler arrete
; ou en pause : le tick ne doit pas courir pendant l'echange.
_music_select:
        cmp half
        beq @rts
        pha
        lda half                ; x = 3 * moitie courante
        asl a
        adc half
        tax
        lda cur_lo
        sta saved,x
        lda cur_hi
        sta saved+1,x
        lda delay
        sta saved+2,x
        pla
        sta half
        asl a
        adc half
        tax
        lda saved,x
        sta cur_lo
        lda saved+1,x
        sta cur_hi
        lda saved+2,x
        sta delay
@rts:   rts

; ── void music_pause(void) ──────────────────────────────────────────────
; Mixeur ferme, timer desarme, curseur et amplitudes intacts : pour les
; lectures disque, pendant lesquelles ProDOS masque les IRQ.
_music_pause:
        lda mb_slot
        beq @rts
        lda playing
        beq @rts
        lda #1
        sta paused
        jsr set_via
        ldy #IER
        lda #$40
        sta (via),y
        ldy #IFR
        lda #$7F
        sta (via),y
        lda #$3F
        jmp mixer_set
@rts:   rts

; ── void music_resume(void) ─────────────────────────────────────────────
; Apres music_pause seulement : rouvre le mixeur et rearme le timer.
_music_resume:
        lda paused
        beq @rts
        stz paused
        bra rearm
@rts:   rts

; ── void music_continue(void) ───────────────────────────────────────────
; Reprend le demi-tampon selectionne la ou son curseur en est -- apres un
; music_stop et un music_select. L'appelant garantit que cette moitie a
; deja ete lancee par music_play.
_music_continue:
        lda mb_slot
        beq rearm_rts
        lda #1
        sta playing
        stz paused
        jsr fade_in_setup
rearm:  jsr set_via
        jsr mixer_restore
        ldy #IFR
        lda #$7F
        sta (via),y
        ldy #IER
        lda #$C0
        sta (via),y
rearm_rts:
        rts

; ── Le fondu ────────────────────────────────────────────────────────────
fade_in_setup:
        lda #15
        sta atten
        lda #2
        sta fade
        lda #1
        sta fstep
        rts

; void music_fade_out(void) : la musique en cours s'efface en 0,9 s ; le
; tick continue de la faire avancer, on ne fait que baisser le son.
_music_fade_out:
        lda playing
        beq @rts
        lda #1
        sta fade
        sta fstep
@rts:   rts

; void music_fade_in(void) : depuis l'attenuation courante, remonte.
_music_fade_in:
        lda playing
        beq @rts
        lda #2
        sta fade
        lda #1
        sta fstep
@rts:   rts

; unsigned char music_fading(void) : 0 quand le fondu en cours est fini.
_music_fading:
        lda fade
        ldx #0
        rts

; Reecrit les six amplitudes, attenuees. Detruit A, X, Y, tmp.
apply_amps:
        ldy #0
@l:     sty tmp
        lda amps,y
        sec
        sbc atten
        bcs :+
        lda #0
:       pha
        tya
        jsr chip_of
        clc
        adc #8
        tax
        pla
        jsr ay_write
        ldy tmp
        iny
        cpy #6
        bne @l
        stz via
        rts

; Un pas de fondu par FADE_STEP ticks ; a l'arrivee, fade repasse a zero.
fade_tick:
        lda fade
        beq @rts
        dec fstep
        bne @rts
        lda #FADE_STEP
        sta fstep
        lda fade
        cmp #1
        bne @in
        lda atten
        cmp #15
        bcs @done
        inc atten
        jmp apply_amps
@in:    lda atten
        beq @done
        dec atten
        jmp apply_amps
@done:  stz fade
@rts:   rts

; ── Le tick ─────────────────────────────────────────────────────────────
; Entree : retenue a zero. Sortie : retenue a un si l'IRQ etait la notre.
music_irq:
        lda playing
        beq @notours
        jsr set_via
        ldy #IFR
        lda #$7F
        sta (via),y             ; acquitter, par ecriture seulement
        jsr fade_tick
        dec delay
        bne @done
        lda cur_lo
        sta cur
        lda cur_hi
        sta cur+1
@next:  jsr aux_read_cur
        NEXT
        cmp #$80
        bcs @cmd
        sta delay               ; DELAY n
        lda cur
        sta cur_lo
        lda cur+1
        sta cur_hi
@done:  sec
        rts
@notours:
        clc
        rts

@cmd:   tax
        and #$0F
        sta tmp                 ; la voix
        txa
        and #$F0
        cmp #$80
        beq @note
        cmp #$90
        beq @off
        cmp #$A0
        beq @vol
        cmp #$E0
        beq @end
        cmp #$F0
        bne :+
        jmp @fade
:       cmp #$B0
        bne :+
        jmp @noise
:       jmp @next               ; paquet inconnu : ignore

@note:  jsr aux_read_cur               ; index de note 0-59
        NEXT
        asl a
        sta tmp2
        lda tmp
        jsr chip_of             ; via -> la puce, A = voix 0-2 dans la puce
        asl a
        tax                     ; R0/R2/R4 : periode, poids faible
        ldy tmp2
        lda note_table,y
        jsr ay_write
        inx                     ; R1/R3/R5 : poids fort
        ldy tmp2
        lda note_table+1,y
        jsr ay_write
        clc
        jsr mix_voice           ; ton ouvert, bruit coupe (la voix a pu battre)
        ldy tmp
        lda vols,y
        jmp @amp

@vol:   jsr aux_read_cur
        NEXT
        ldy tmp
        sta vols,y
        jmp @amp

@off:   lda #0
@amp:   ldy tmp                 ; A = amplitude brute, tmp = voix 0-5
        sta amps,y
        sec
        sbc atten               ; attenuee par le fondu en cours
        bcs :+
        lda #0
:       pha
        lda tmp
        jsr chip_of
        clc
        adc #8
        tax
        pla
        jsr ay_write
        stz via                 ; retour sur le VIA #1 (IFR, T1)
        jmp @next

@end:   jsr set_base            ; seul COMBAT porte encore le drapeau boucle
        ldy #5
        jsr aux_read_header
        and #1
        beq @stop
        ldy #6
        jsr aux_read_header
        clc
        adc tmp
        sta cur
        ldy #7
        jsr aux_read_header
        adc tmp2
        sta cur+1
        jsr fade_in_setup
        jmp @next
@stop:  jsr _music_stop
        sec
        rts

@fade:  lda #1                  ; FADE : la fin du morceau s'efface en 0,9 s
        sta fade
        sta fstep
        jmp @next

@noise: jsr aux_read_cur               ; NOISE : periode de bruit (R6 de la puce)
        NEXT
        pha
        sec
        jsr mix_voice           ; ton coupe, bruit ouvert ; via -> la puce
        ldx #6
        pla
        jsr ay_write
        ldy tmp
        lda vols,y
        jmp @amp

; MAIN and AUX contain the same instructions across RAMRD transitions.
; AUX $1000-$1DFF holds both streams; the mirror lives at its linked CODE
; address, above $4000, separate from DHGR page 1 and stream storage.
; All entries require MAIN RAMRD/RAMWRT and MAIN ZP, as the existing driver.
; Copying uses SEI so its temporary RAMWRT AUX cannot redirect IRQ globals.
init_aux_reader:
        php
        sei
        ldx #aux_mirror_end-aux_read_cur-1
@copy:  lda aux_read_cur,x
        sta $C005
        sta aux_read_cur,x
        sta $C004
        dex
        bpl @copy
        plp
        rts
aux_read_cur:
        sta $C003
        lda (cur)
        sta $C002
        rts
aux_read_header:
        sta $C003
        lda (tmp),y
        sta $C002
        rts
aux_mirror_end:
        .assert aux_read_cur >= $4000, lderror, "AUX mirror overlaps low RAM"

; music_store(offset, count): count is 1..256, offset within both streams.
; The C caller has validated bounds and placed count bytes in _music_buf.
_music_store:
        php
        sei
        sta tmp                 ; low byte 0 denotes 256
        jsr popax               ; offset, A low / X high
        sta cur
        txa
        clc
        adc #>AUX_MUSIC
        sta cur+1
        ldy #0
@copy:  lda _music_buf,y
        sta $C005
        sta (cur),y
        sta $C004
        iny
        cpy tmp
        bne @copy
        plp
        rts

; Set the selected stream's loop byte, with the reader paused.
_music_set_loop:
        php
        sei
        pha
        jsr set_base
        pla
        ldy #5
        sta $C005
        sta (tmp),y
        sta $C004
        plp
        rts
