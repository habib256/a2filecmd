; Hardware-only Mockingboard probe, no AUX, IRQ vector or resident player.
; Includes the //c Mockingboard 4c: its connector answers at $C400-$C4FF.
; Return the VIA address page (4), not an emulator's virtual storage slot.
; Probe T1 before any VIA write; plain //c ROM must remain a no-card result.
.export _music_detect_card
.importzp ptr1, ptr2
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
