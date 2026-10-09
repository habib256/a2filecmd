; Foreground two-AY driver, timer polling. No IRQ/vector or AUX writes.
; Save the VIA configuration used here; silence both chips on every exit.
.importzp ptr1
.export _mc_regs, _mc_hw_start, _mc_tick, _mc_output, _mc_silence, _mc_hw_stop
.segment "BSS"
_mc_regs: .res 28
card: .res 1
old_acr: .res 1
old_ier: .res 1
old_t1: .res 2
old_ddr: .res 4
.segment "CODE"
via:
 lda #0
 sta ptr1
 lda card
 sta ptr1+1
 rts
_mc_hw_start:
 ora #$C0
 sta card
 jsr via
 ldy #$0B
 lda (ptr1),y
 sta old_acr
 ldy #$0E
 lda (ptr1),y
 sta old_ier
 lda #$7F
 sta (ptr1),y
 ldy #6
 lda (ptr1),y
 sta old_t1
 iny
 lda (ptr1),y
 sta old_t1+1
 ldy #2
 lda (ptr1),y
 sta old_ddr
 iny
 lda (ptr1),y
 sta old_ddr+1
 ldy #$82
 lda (ptr1),y
 sta old_ddr+2
 iny
 lda (ptr1),y
 sta old_ddr+3
 lda #$FF
 ldy #3
 sta (ptr1),y
 ldy #$83
 sta (ptr1),y
 lda #7
 ldy #2
 sta (ptr1),y
 ldy #$82
 sta (ptr1),y
 lda old_acr
 and #$3F
 ora #$40
 ldy #$0B
 sta (ptr1),y
 ldy #4
 lda #$FF
 sta (ptr1),y
 iny
 lda #$40
 sta (ptr1),y
 rts
_mc_tick:
 jsr via
 ldy #$0D
 lda (ptr1),y
 and #$40
 beq @done
 ldy #4
 lda (ptr1),y
 lda #1
@done:
 ldx #0
 rts
write:
 pha
 txa
 ldy #1
 sta (ptr1),y
 dey
 lda #7
 sta (ptr1),y
 lda #4
 sta (ptr1),y
 pla
 iny
 sta (ptr1),y
 dey
 lda #6
 sta (ptr1),y
 lda #4
 sta (ptr1),y
 rts
_mc_output:
 jsr via
 ldx #0
@first:
 lda _mc_regs,x
 jsr write
 inx
 cpx #14
 bne @first
 lda #$80
 sta ptr1
 ldx #0
@second:
 lda _mc_regs+14,x
 jsr write
 inx
 cpx #14
 bne @second
 rts
silent:
 ldx #7
 lda #$3F
 jsr write
 ldx #8
 lda #0
 jsr write
 inx
 lda #0
 jsr write
 inx
 lda #0
 jmp write
_mc_silence:
 jsr via
 jsr silent
 lda #$80
 sta ptr1
 jsr silent
 jmp via
_mc_hw_stop:
 jsr _mc_silence
 ldy #$0E
 lda #$7F
 sta (ptr1),y
 ldy #4
 lda (ptr1),y
 ldy #6
 lda old_t1
 sta (ptr1),y
 iny
 lda old_t1+1
 sta (ptr1),y
 ldy #$0B
 lda old_acr
 sta (ptr1),y
 ldy #2
 lda old_ddr
 sta (ptr1),y
 iny
 lda old_ddr+1
 sta (ptr1),y
 ldy #$82
 lda old_ddr+2
 sta (ptr1),y
 iny
 lda old_ddr+3
 sta (ptr1),y
 ldy #$0E
 lda old_ier
 ora #$80
 sta (ptr1),y
 rts
