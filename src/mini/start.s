; start.s -- entry and exit for a BRUN binary at $2000.
;
; DOS gives us the machine with Applesoft's state live underneath: HELLO
; called us and must be able to carry on. So page zero $80-$9F and the
; stack pointer are saved here and put back before the closing RTS.
;
; The BSS is cleared before anything reads it, the guarantee the C runtime
; used to provide. The saved copies live in DATA so the clear cannot eat
; them. Slot and drive come from DOS's own IOB: whatever DOS last used is
; where we were run from, which is the drive the panels must open first.

        .include "mini.inc"

        .export start

        .import main
        .import slot, drive
        .import __BSS_RUN__, __BSS_SIZE__

        .segment "DATA"
saved_stack:    .byte 0
saved_zp:       .res ZP_COUNT

        .segment "STARTUP"

start:
        cld
        tsx
        stx     saved_stack
        ldx     #ZP_COUNT-1
@save:
        lda     ZP_FIRST,x
        sta     saved_zp,x
        dex
        bpl     @save

        lda     #<__BSS_RUN__
        sta     ptr
        lda     #>__BSS_RUN__
        sta     ptr+1
        lda     #0
        ldx     #>__BSS_SIZE__
        beq     @tail
@page:
        ldy     #0
@onepage:
        sta     (ptr),y
        iny
        bne     @onepage
        inc     ptr+1
        dex
        bne     @page
@tail:
        ldx     #<__BSS_SIZE__
        beq     @cleared
        ldy     #0
@onebyte:
        sta     (ptr),y
        iny
        dex
        bne     @onebyte
@cleared:

        jsr     RWTS_LOCATE_IOB
        sty     iob
        sta     iob+1
        ldy     #IOB_SLOT
        lda     (iob),y         ; slot * 16
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     slot
        ldy     #IOB_DRIVE
        lda     (iob),y
        sta     drive

        jsr     main

        ldx     #ZP_COUNT-1
@restore:
        lda     saved_zp,x
        sta     ZP_FIRST,x
        dex
        bpl     @restore
        ldx     saved_stack
        txs
        rts
