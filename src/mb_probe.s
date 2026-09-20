; Hardware-only Mockingboard probe, no AUX, IRQ vector or resident player.
; Includes the //c Mockingboard 4c: its connector answers at $C400-$C4FF.
; Return the VIA address page (4), not an emulator's virtual storage slot.
; A sleeping 4c exposes the //c ROM until its first $C4xx write. Wake it
; through DDRA (inputs), only on a positively identified //c. No AUX or
; disk writes. The timer probe must still reject a plain //c without a card.
.export _music_detect_card
.importzp ptr1, ptr2
.ifndef A2_6502
.import _a2fc_mouse
.endif
.segment "CODE"
t1_probe:
 ldy #4
 lda (ptr1),y
 sta ptr2
 lda (ptr1),y
 sec
 sbc ptr2
 cmp #$F8
 rts
init1:
 lda #$FF
 ldy #3
 sta (ptr1),y
 dey
 sta (ptr1),y
 ldy #0
 lda #0
 sta (ptr1),y
 lda #4
 sta (ptr1),y
 rts
_music_detect_card:
 bit $C082                ; expose firmware: the caller runs in LC RAM
 lda $FBB3
 cmp #$06
 bne @scan
 lda $FBC0
 bne @scan
 sta $C403                 ; A=0: wake 4c without driving the AY data bus
.ifndef A2_6502
 lda $C4FB                ; waking 4c can hide the //c mouse firmware
 cmp #$D6
 beq @scan
 lda #0
 sta _a2fc_mouse          ; never dispatch mouse calls into VIA registers
.endif
@scan:
 bit $C080                ; restore bank 2 RAM before returning to LC caller
 ldx #7
@slot:
 cpx #3
 beq @next
 txa
 ora #$C0
 sta ptr1+1
 lda #0
 sta ptr1
 jsr t1_probe
 bne @next
 jsr t1_probe
 bne @next
 jsr init1
 lda #$80
 sta ptr1
 jsr init1
 txa
 ldx #0
 rts
@next:
 dex
 bne @slot
 txa
 rts
