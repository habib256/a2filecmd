; Disk II write-protection sensing only. No write mode, AUX or RAM disk use.
.export _dw_protected, _dw_mainbank
.importzp ptr1
.segment "CODE"
_dw_mainbank:
 bit $C056
 bit $C002
 bit $C004
 rts
_dw_protected:
 php
 sei
 pha
 and #$70
 lsr
 lsr
 lsr
 lsr
 ora #$C0
 sta ptr1+1
 lda #0
 sta ptr1
 ; Standard Disk II boot ROM signature; refuse an unknown controller.
 ldy #0
 lda (ptr1),y
 cmp #$A2
 bne protected
 ldy #1
 lda (ptr1),y
 cmp #$20
 bne protected
 ldy #3
 lda (ptr1),y
 bne protected
 ldy #5
 lda (ptr1),y
 cmp #$03
 bne protected
 ; Block/SmartPort ROMs share the ProDOS signature above. Disk II has
 ; no ROM block driver: ProDOS supplies it from the language card.
 ldy #$FF
 lda (ptr1),y
 bne protected
 pla
 pha
 and #$70
 tax
 pla
 bmi drive2
 lda $C08A,x
 jmp sense
drive2:
 lda $C08B,x
sense:
 lda $C080,x
 lda $C082,x
 lda $C084,x
 lda $C086,x
 lda $C08D,x
 lda $C08E,x
 and #$80
 pha
 lda $C08C,x
 pla
 ldx #0
 plp
 rts
protected:
 pla
 lda #1
 ldx #0
 plp
 rts
