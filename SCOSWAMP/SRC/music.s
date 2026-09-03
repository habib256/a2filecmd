; music.s -- la Mockingboard joue le _music_buf d'accueil.
;
; Un lecteur de flux MB1 (DOCS/MUSIQUE.md § 5.2) en interruption : le Timer 1
; du premier 6522 de la carte bat a 50 Hz, et chaque tick decode les paquets
; du flux jusqu'au prochain DELAY. Tout est en assembleur et en segment CODE :
; jamais en LC, ProDOS commute l'autre banque sous IRQ.
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
;   void music_play(void);              joue le _music_buf d'accueil en boucle
;   void music_stop(void);              silence net, timer desarme

        .setcpu "65C02"
        .export _music_detect, _music_play, _music_stop, _music_buf
        .interruptor music_irq
        .destructor  music_done         ; exit() coupe le timer avant DEALLOC

via     = $FA           ; pointeur vers $Cn00, le VIA #1
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
; Le flux MB1 courant, lu depuis MUSIC/<NOM>.MB par music_load (scoswamp.c).
; MUSIC_BUF_SIZE de music.h doit dire la meme taille.
_music_buf:     .res 2560
mb_slot:        .res 1
playing:        .res 1
delay:          .res 1
cur_lo:         .res 1
cur_hi:         .res 1
vols:           .res 3

.segment "RODATA"
        .include "ay_notes.inc"

.segment "CODE"

.macro  NEXT                    ; cur++
        inc cur
        bne :+
        inc cur+1
:
.endmacro

; via := $Cn00 d'apres mb_slot
set_via:
        stz via
        lda mb_slot
        ora #$C0
        sta via+1
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

; Mixeur ferme, trois volumes a zero.
silence:
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
        ; trouvee : ports en sortie, /RESET bas puis haut
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
        ldx #7                  ; tons A, B, C ouverts, bruit ferme
        lda #$38
        jsr ay_write
        lda #<(_music_buf+8)
        sta cur_lo
        lda #>(_music_buf+8)
        sta cur_hi
        lda #1
        sta delay
        sta playing
        lda #12
        sta vols
        sta vols+1
        sta vols+2
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
        jsr set_via
        ldy #IER                ; interdire T1
        lda #$40
        sta (via),y
        ldy #IFR
        lda #$7F
        sta (via),y
        jmp silence
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
@amp:   pha                     ; A = amplitude, tmp = voix -> R8+voix
        lda tmp
        clc
        adc #8
        tax
        pla
        jsr ay_write
        jmp @next

@end:   lda _music_buf+5             ; drapeau de boucle
        and #1
        beq @stop
        lda _music_buf+6
        clc
        adc #<_music_buf
        sta cur
        lda _music_buf+7
        adc #>_music_buf
        sta cur+1
        jmp @next
@stop:  jsr _music_stop
        sec
        rts
