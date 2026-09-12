; Main bank only; no auxiliary memory or ProDOS RAM disk writes.
.export _hv_clear, _hv_show, _hv_row
.importzp ptr1
.segment "CODE"
_hv_clear:
 lda #0
 sta $C000
 sta $C002
 sta $C004
 sta $C054
 sta ptr1
 lda #$20
 sta ptr1+1
 ldy #0
 lda #0
@byte: sta (ptr1),y
 iny
 bne @byte
 inc ptr1+1
 ldx ptr1+1
 cpx #$40
 bne @byte
 rts
_hv_row:
 pha
 and #7
 asl
 asl
 ora #$20
 sta ptr1+1
 pla
 pha
 and #$38
 lsr
 lsr
 lsr
 lsr
 ora ptr1+1
 sta ptr1+1
 pla
 pha
 and #8
 beq @even
 lda #$80
@even:
 sta ptr1
 pla
 lsr
 lsr
 lsr
 lsr
 lsr
 lsr
 tax
 lda offsets,x
 clc
 adc ptr1
 ldx ptr1+1
 rts
 offsets: .byte 0,40,80
_hv_show:
 lda #0
 sta $C000
 sta $C00D
 sta $C05E
 sta $C05F
 sta $C05E
 sta $C05F
 sta $C00C
 sta $C057
 sta $C054
 sta $C052
 sta $C050
 rts

.export _font_draw
.import _fh, _fn, _fr, _fc
.importzp ptr2
.segment "BSS"
fg: .res 1
fy: .res 1
.segment "CODE"
_font_draw:
 sta ptr2
 stx ptr2+1
 lda #0
 sta fg
 lda _fr
 sta fy
@char:
 lda fy
 jsr _hv_row
 sta ptr1
 stx ptr1+1
 ldy fg
 lda (ptr2),y
 ldx _fc
 beq @width
 sec
 sbc #7
 bcs @width
 lda #0
@width:
 cmp #8
 bcc @mask
 lda #7
@mask:
 tax
 lda fg
 ora #$80
 tay
 lda (ptr2),y
 and masks,x
 pha
 lda fg
 and #15
 asl
 clc
 adc #4
 adc _fc
 tay
 pla
 sta (ptr1),y
 inc fg
 lda fg
 cmp _fn
 beq @done
 and #15
 bne @char
 lda fy
 clc
 adc _fh
 adc #2
 sta fy
 jmp @char
@done: rts
masks: .byte 0,1,3,7,15,31,63,127
