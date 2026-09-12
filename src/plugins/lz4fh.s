; Main bank only; no auxiliary memory or ProDOS RAM disk writes.
.export _hv_clear, _hv_show
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
