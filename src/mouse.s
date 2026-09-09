; mouse.s -- the mouse: an AppleMouse II card (341-0270) in any slot,
; in passive mode, without interrupts.
;
;   unsigned char mouse_init(void);   looks for the card, from $C7 down to
;                                     $C1 skipping 3 (the //e's 80-column
;                                     firmware answers there); INITMOUSE,
;                                     bounds 0..79 and 0..23 -- cells of the
;                                     80-column screen, no arithmetic
;                                     afterwards --, mode 1 (on, without
;                                     interrupts). Returns the slot, 0
;                                     without a card.
;   unsigned char mouse_read(void);   READMOUSE; updates mouse_x, mouse_y
;                                     and returns the status byte: bit 7 the
;                                     button is down, bit 6 it was down at
;                                     the previous read, bit 5 the mouse
;                                     has moved.
;   void mouse_show(void);            draws the pointer -- the MouseText
;                                     arrow $42, the 80-column firmware
;                                     leaves ALTCHARSET on -- at (mouse_x,
;                                     mouse_y), after erasing the previous
;                                     one.
;   void mouse_hide(void);            gives back to the screen the byte the
;                                     pointer was hiding.
;
; The firmware (Apple II Mouse Technical Notes) is called with X = $Cn,
; Y = $n0, A = argument, interrupts disabled; its entry points are the low
; bytes of a table at $Cn12 (SETMOUSE) .. $Cn19 (INITMOUSE). CLAMPMOUSE
; reads its bounds from the screen holes of slot 0: $478 and $578 the
; minimum, $4F8 and $5F8 the maximum, low byte then high (the same layout
; as the position read back, X then Y). READMOUSE writes the position
; into those of slot n -- $478+n X low, $4F8+n Y low, $578+n X high, $5F8+n
; Y high -- and the status at $778+n. The firmware may use $C800:
; $CFFF after each call hands it back to the 80-column firmware, which
; uses it.
;
; The pointer is a character: the screen is in 80-column text, whose even
; columns live in the AUX bank, reached through PAGE2 as long as 80STORE
; is on -- which the 80-column firmware and switch_to_text guarantee.
; A cell is at $400 + (y & 7) * $80 + (y / 8) * 40 + x / 2.

        .export _mouse_init, _mouse_read, _mouse_show, _mouse_hide
        .export _mouse_x, _mouse_y
        .importzp ptr1

.ifdef A2_6502
.macro  stz     addr            ; the non-enhanced IIe has no STZ (A is free here)
        lda     #0
        sta     addr
.endmacro
.endif

        .segment "LOWBSS"
_mouse_x:       .res 1
_mouse_y:       .res 1
slot:           .res 1          ; n, 0 without a mouse
cn:             .res 1          ; $Cn
n0:             .res 1          ; $n0
shown:          .res 1          ; the pointer is on screen...
px:             .res 1          ; ... here
py:             .res 1
under:          .res 1          ; the byte it hides
vec:            .res 2

        .segment "CODE"

; Calls the firmware routine whose table index is in Y, with A as the
; argument. $Cn is loaded once, into X, which keeps it for the call; the
; entry's low byte is read from the ROM before Y receives $n0.
; (Colin Leroy-Mira, 2026-09-08: three loads of cn or a single one.)
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

; The card's signature: (offset within $Cn00, value), from the last to the
; first. $CnFB = $D6 is the mouse's own; the four others are those of a
; card with Pascal firmware.
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
        lda slot                ; found: $n0
        asl a
        asl a
        asl a
        asl a
        sta n0
        ldy #$19                ; INITMOUSE
        jsr call
        lda #79
        sta $4F8                ; maximum, low byte
        lda #0
        sta $478                ; minimum 0, low and high bytes
        sta $578
        sta $5F8                ; maximum, high byte
        ldy #$17                ; CLAMPMOUSE, A = 0: X, 0..79
        jsr call
        lda #23
        sta $4F8
        lda #1                  ; Y: 0..23
        ldy #$17
        jsr call
        lda #1                  ; on, without interrupts
        ldy #$12                ; SETMOUSE
        jsr call
        ; A dummy read establishes the button state. Without it, the first
        ; READMOUSE returns an $80 edge (button down, not before) while
        ; nothing is pressed: the //c mouse firmware (and the initial state
        ; of many emulators) starts out that way. wait_key took it for a
        ; click at (0,0), that is an ESC: at the root, we fell back to the
        ; volume list.
        ldy #$14                ; READMOUSE
        jsr call
        lda slot
        ldx #0
        rts
@next:  dec slot
        bne @slot
        ldx #0                  ; none: slot = 0
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

; ptr1 := the cell (px, py), and PAGE2 on if it is in AUX (even column).
; The caller restores the main bank through $C054.
cell:   lda py
        and #7
        lsr a
        ora #4
        sta ptr1+1              ; $04 + (y & 7) / 2
        lda #0
        ror a                   ; bit 0 of (y & 7) into bit 7
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
        adc ptr1                ; no carry: at most 119 + 128
        sta ptr1
        lda px
        lsr a                   ; C = odd column, in the main bank
        bcs :+
        sta $C055               ; PAGE2: $400-$7FF to AUX
:       rts
thirds: .byte 0, 40, 80

_mouse_hide:
        lda shown
        beq @done
        stz shown
        jsr cell
        lda under
        ldy #0
        sta (ptr1),y
        sta $C054
@done:  rts

_mouse_show:
        jsr _mouse_hide
        lda _mouse_x
        sta px
        lda _mouse_y
        sta py
        jsr cell
        ldy #0
        lda (ptr1),y
        sta under
.ifdef A2_6502
        lda #$2B                ; without MouseText: an inverse '+'
.else
        lda #$42                ; MouseText: the arrow
.endif
        sta (ptr1),y
        sta $C054
        inc shown
        rts
