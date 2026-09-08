; mouse.s -- la souris : une carte AppleMouse II (341-0270) dans n'importe
; quel slot, en mode passif, sans interruption.
;
;   unsigned char mouse_init(void);   cherche la carte, de $C7 a $C1 en
;                                     sautant le 3 (le firmware 80 colonnes du
;                                     //e y repond) ; INITMOUSE, bornes 0..79
;                                     et 0..23 -- des cases de l'ecran 80
;                                     colonnes, aucun calcul ensuite --, mode 1
;                                     (allumee, sans interruption). Rend le
;                                     slot, 0 sans carte.
;   unsigned char mouse_read(void);   READMOUSE ; met a jour mouse_x, mouse_y
;                                     et rend l'octet d'etat : bit 7 le bouton
;                                     est enfonce, bit 6 il l'etait a la
;                                     lecture d'avant, bit 5 la souris a bouge.
;   void mouse_show(void);            dessine le pointeur -- la fleche
;                                     MouseText $42, le firmware 80 colonnes
;                                     laisse ALTCHARSET arme -- en (mouse_x,
;                                     mouse_y), apres avoir efface le precedent.
;   void mouse_hide(void);            rend a l'ecran l'octet que le pointeur
;                                     cachait.
;
; Le firmware (Apple II Mouse Technical Notes) s'appelle X = $Cn, Y = $n0,
; A = argument, interruptions coupees ; ses points d'entree sont les octets
; bas d'une table en $Cn12 (SETMOUSE) .. $Cn19 (INITMOUSE). CLAMPMOUSE lit
; ses bornes dans les trous d'ecran du slot 0 : $478 et $578 le minimum,
; $4F8 et $5F8 le maximum, octet bas puis haut (la meme disposition que la
; position lue, X puis Y). READMOUSE ecrit la position
; dans ceux du slot n -- $478+n X bas, $4F8+n Y bas, $578+n X haut, $5F8+n
; Y haut -- et l'etat en $778+n. Le firmware peut se servir de $C800 :
; $CFFF apres chaque appel le rend au firmware 80 colonnes, qui s'en sert.
;
; Le pointeur est un caractere : l'ecran est en texte 80 colonnes, dont les
; colonnes paires vivent en banque AUX, atteinte par PAGE2 tant que 80STORE
; est arme -- ce que le firmware 80 colonnes et switch_to_text garantissent.
; Une cellule vaut $400 + (y & 7) * $80 + (y / 8) * 40 + x / 2.

        .export _mouse_init, _mouse_read, _mouse_show, _mouse_hide
        .export _mouse_x, _mouse_y
        .importzp ptr1

        .segment "LOWBSS"
_mouse_x:       .res 1
_mouse_y:       .res 1
slot:           .res 1          ; n, 0 sans souris
cn:             .res 1          ; $Cn
n0:             .res 1          ; $n0
shown:          .res 1          ; le pointeur est a l'ecran...
px:             .res 1          ; ... ici
py:             .res 1
under:          .res 1          ; l'octet qu'il cache
vec:            .res 2

        .segment "CODE"

; Appelle la routine du firmware dont l'index de table est en Y, A en
; argument. $Cn est charge une fois, dans X, qui le garde pour l'appel ;
; l'octet bas de l'entree se lit dans la ROM avant que Y ne recoive $n0.
; (Colin Leroy-Mira, 2026-09-08 : trois chargements de cn ou un seul.)
call:   pha
        stz ptr1
        ldx cn
        stx ptr1+1
        stx vec+1
        lda (ptr1),y
        sta vec
        ldy n0
        pla
        php
        sei
        jsr go
        plp
        bit $CFFF
        rts
go:     jmp (vec)

; La signature de la carte : (decalage dans $Cn00, valeur), du dernier au
; premier. $CnFB = $D6 est celle de la souris ; les quatre autres, celles
; d'une carte a firmware Pascal.
sig:    .byte $05, $38, $07, $18, $0B, $01, $0C, $20, $FB, $D6

_mouse_init:
        lda #7
        sta slot
@slot:  lda slot
        cmp #3
        beq @next
        ora #$C0
        sta cn
        sta ptr1+1
        stz ptr1
        ldx #8
@sig:   ldy sig,x
        lda (ptr1),y
        cmp sig+1,x
        bne @next
        dex
        dex
        bpl @sig
        lda slot                ; trouvee : $n0
        asl a
        asl a
        asl a
        asl a
        sta n0
        ldy #$19                ; INITMOUSE
        jsr call
        lda #79
        sta $4F8                ; maximum, octet bas
        lda #0
        sta $478                ; minimum 0, octets bas et haut
        sta $578
        sta $5F8                ; maximum, octet haut
        ldy #$17                ; CLAMPMOUSE, A = 0 : X, 0..79
        jsr call
        lda #23
        sta $4F8
        lda #1                  ; Y : 0..23
        ldy #$17
        jsr call
        lda #1                  ; allumee, sans interruption
        ldy #$12                ; SETMOUSE
        jsr call
        lda slot
        ldx #0
        rts
@next:  dec slot
        bne @slot
        ldx #0                  ; aucune : slot = 0
        txa
        rts

_mouse_read:
        ldy #$14                ; READMOUSE
        jsr call
        ldx slot
        lda $478,x
        sta _mouse_x
        lda $4F8,x
        sta _mouse_y
        lda $778,x
        ldx #0
        rts

; ptr1 := la cellule (px, py), et PAGE2 arme si elle est en AUX (colonne
; paire). L'appelant rend la banque principale par $C054.
cell:   lda py
        and #7
        lsr a
        ora #4
        sta ptr1+1              ; $04 + (y & 7) / 2
        lda #0
        ror a                   ; bit 0 de (y & 7) en bit 7
        sta ptr1
        lda py
        lsr a
        lsr a
        lsr a
        tax
        lda px
        lsr a
        clc
        adc thirds,x
        adc ptr1                ; pas de retenue : au plus 119 + 128
        sta ptr1
        lda px
        lsr a                   ; C = colonne impaire, en banque principale
        bcs :+
        sta $C055               ; PAGE2 : $400-$7FF vers AUX
:       rts
thirds: .byte 0, 40, 80

_mouse_hide:
        lda shown
        beq @done
        stz shown
        jsr cell
        lda under
        sta (ptr1)
        sta $C054
@done:  rts

_mouse_show:
        jsr _mouse_hide
        lda _mouse_x
        sta px
        lda _mouse_y
        sta py
        jsr cell
        lda (ptr1)
        sta under
        lda #$42                ; MouseText : la fleche
        sta (ptr1)
        sta $C054
        inc shown
        rts
