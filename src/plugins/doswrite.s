; Disk II write-protection sensing only. No write mode, AUX or RAM disk use.
.export _dw_protected, _dw_mainbank
.segment "CODE"
_dw_mainbank:
 bit $C056
 bit $C002
 bit $C004
 rts
_dw_protected:
 php
 sei
 tax
 lda $C600
 ; Standard Disk II boot ROM signature; refuse an unknown controller.
 lda $C601
 cmp #$20
 bne protected
 lda $C603
 bne protected
 lda $C605
 cmp #$03
 bne protected
 txa
 bmi drive2
 bit $C0EA
 jmp sense
drive2:
 bit $C0EB
sense:
 bit $C0E0
 bit $C0E2
 bit $C0E4
 bit $C0E6
 bit $C0ED
 lda $C0EE
 and #$80
 pha
 bit $C0EC
 pla
 ldx #0
 plp
 rts
protected:
 lda #1
 ldx #0
 plp
 rts
