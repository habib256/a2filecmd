.importzp ptr1
.export _mb_regs
.segment "BSS"
_mb_regs: .res 28
; VIA timer polling, no new IRQ vector; channel A/B/C on the first AY.
.export _mb_hw_start, _mb_tick, _mb_output, _mb_silence, _mb_hw_stop
.segment "BSS"
card: .res 1
old_acr: .res 1
.segment "CODE"
mb_via:
 lda #0
 sta ptr1
 lda card
 sta ptr1+1
 rts
_mb_hw_start:
 ora #$C0
 sta card
 jsr mb_via
 ldy #$0B
 lda (ptr1),y
 sta old_acr
 ora #$40
 sta (ptr1),y
 ldy #$0E
 lda #$7F
 sta (ptr1),y
 ldy #4
 lda #<20452
 sta (ptr1),y
 iny
 lda #>20452
 sta (ptr1),y
 rts
_mb_tick:
 jsr mb_via
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
mb_write:
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
_mb_output:
 jsr mb_via
 ldx #0
@reg:
 lda _mb_regs,x
 cpx #13
 bne @write
 cmp #$FF
 beq @next
@write:
 jsr mb_write
@next:
 inx
 cpx #14
 bne @reg
 lda #$80
 sta ptr1
 ldx #0
@second:
 lda _mb_regs+14,x
 jsr mb_write
 inx
 cpx #14
 bne @second
 rts
_mb_silence:
 jsr mb_via
 jsr silent_chip
 lda #$80
 sta ptr1
 jsr silent_chip
 jmp mb_via
silent_chip:
 ldx #7
 lda #$3F
 jsr mb_write
 ldx #8
 lda #0
 jsr mb_write
 inx
 lda #0
 jsr mb_write
 inx
 lda #0
 jmp mb_write
_mb_hw_stop:
 jsr _mb_silence
 ldy #$0E
 lda #$7F
 sta (ptr1),y
 ldy #4
 lda (ptr1),y
 ldy #$0B
 lda old_acr
 sta (ptr1),y
 rts


.segment "RODATA"
.export _mb_notes
_mb_notes:
.include "../ay_notes.inc"
