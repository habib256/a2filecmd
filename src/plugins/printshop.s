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

.export _ps_draw
.import _py
.importzp ptr2
.segment "BSS"
row: .res 1
sx: .res 1
srcbit: .res 1
col: .res 1
mask: .res 1
.segment "CODE"
_ps_draw:
 sta ptr2
 stx ptr2+1
 lda #0
 sta row
@row:
 lda _py
 clc
 adc row
 jsr _hv_row
 sta ptr1
 stx ptr1+1
 lda #7
 sta col
 lda #8
 sta mask
 lda #0
 sta sx
 lda #$80
 sta srcbit
@pixel:
 lda sx
 lsr
 lsr
 lsr
 tay
 lda (ptr2),y
 and srcbit
 bne @black
 jsr white
 jsr advance
 jsr white
 jmp @second
@black:
 jsr advance
@second:
 jsr advance
 lsr srcbit
 bne @next
 lda #$80
 sta srcbit
@next:
 inc sx
 lda sx
 cmp #88
 bne @pixel
 inc row
 lda row
 cmp #3
 bne @row
 rts
white:
 ldy col
 lda (ptr1),y
 ora mask
 sta (ptr1),y
 rts
advance:
 asl mask
 bpl @ret
 lda #1
 sta mask
 inc col
@ret: rts
