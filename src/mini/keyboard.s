; keyboard.s -- the Apple II+ keyboard, and the moment the screen updates.
;
; Every wait for a key presents the composed image first, so what the
; user is answering is always what is on the glass. Isolated in its own
; module because the host tests drive the program with a scripted key
; source instead of the hardware.

        .include "mini.inc"

        .export key

        .import present

        .segment "CODE"

key:
        jsr     present
@wait:
        lda     KBD
        bpl     @wait
        and     #$7F
        bit     KBDSTROBE       ; clears the strobe, leaves A alone
        rts
