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
;   void music_play(void);              joue le flux de music_buf en boucle
;   void music_stop(void);              silence net, timer desarme

        .setcpu "65C02"
        .export _music_detect, _music_play, _music_stop, _music_buf
        .export _music_select, _music_pause, _music_resume, _music_continue
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

.segment "BSS"
; Deux demi-tampons de 1280 octets : le theme de la zone (0) et la surcouche
; (1 : combat, mort, victoire), lus depuis MUSIC/<NOM>.MB par music_load
; (scoswamp.c). MUSIC_BUF_SIZE et MUSIC_HALF de music.h disent les memes
; tailles. Chaque moitie garde son curseur : revenir a la zone apres un
; combat la reprend ou elle en etait, sans rien relire.
_music_buf:     .res 2560
mb_slot:        .res 1
playing:        .res 1
paused:         .res 1
half:           .res 1          ; la moitie selectionnee, 0 ou 1
delay:          .res 1
cur_lo:         .res 1
cur_hi:         .res 1
saved:          .res 6          ; cur_lo, cur_hi, delay de chaque moitie
vols:           .res 6

.segment "RODATA"
        .include "ay_notes.inc"

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

; tmp/tmp2 := adresse du demi-tampon selectionne.
set_base:
        lda #<_music_buf
        sta tmp
        lda #>_music_buf
        sta tmp2
        lda half
        beq :+
        lda #<1280
        clc
        adc tmp
        sta tmp
        lda #>1280
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
        lda #$38
        jsr mixer_set
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
        dex
        bpl :-
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
rearm:  jsr set_via
        lda #$38
        jsr mixer_set
        ldy #IFR
        lda #$7F
        sta (via),y
        ldy #IER
        lda #$C0
        sta (via),y
rearm_rts:
        rts

; ── Le tick ─────────────────────────────────────────────────────────────
; Entree : retenue a zero. Sortie : retenue a un si l'IRQ etait la notre.
music_irq:
        lda playing
        beq @notours
        jsr set_via
        ldy #IFR
        lda #$7F
        sta (via),y             ; acquitter, par ecriture seulement
        dec delay
        bne @done
        lda cur_lo
        sta cur
        lda cur_hi
        sta cur+1
@next:  lda (cur)
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
        jmp @next               ; paquet inconnu : ignore

@note:  lda (cur)               ; index de note 0-59
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
        ldy tmp
        lda vols,y
        bra @amp

@vol:   lda (cur)
        NEXT
        ldy tmp
        sta vols,y
        bra @amp

@off:   lda #0
@amp:   pha                     ; A = amplitude, tmp = voix 0-5 -> R8+voix de sa puce
        lda tmp
        jsr chip_of
        clc
        adc #8
        tax
        pla
        jsr ay_write
        stz via                 ; retour sur le VIA #1 (IFR, T1)
        jmp @next

@end:   jsr set_base            ; tmp/tmp2 = le demi-tampon qui joue
        ldy #5
        lda (tmp),y             ; drapeau de boucle
        and #1
        beq @stop
        ldy #6
        lda (tmp),y
        clc
        adc tmp
        sta cur
        ldy #7
        lda (tmp),y
        adc tmp2
        sta cur+1
        jmp @next
@stop:  jsr _music_stop
        sec
        rts
