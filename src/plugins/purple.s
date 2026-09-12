; Original EVE modes: HR1/HR2/HR3, with CPREG writes disabled while loading.
; The common AN3 latch also selects COL140/BW560 on Feline/Video-7 cards.
.export _pu_prepare, _pu_aux_move, _pu_show, _pu_restore
.segment "CODE"
_pu_prepare:
 lda $C0BD                     ; LOCKCPREG on: no implicit AUX writes
 lda $C0B0                     ; ENHRCPREG off
 lda $C0B8                     ; TXT16 off
 lda #0
 sta $C000                     ; 80STORE off
 sta $C054
 sta $C002
 sta $C004
 rts
_pu_aux_move:
 lda #0
 sta $3C
 sta $42
 lda #$20
 sta $3D
 sta $43
 lda #$FF
 sta $3E
 lda #$3F
 sta $3F
 php
 sei
 sec
 jsr $C311
 plp
 rts
_pu_show:
 tay
 lda hr_modes,y
 pha
 and #1
 tax
 lda $C0B2,x
 pla
 lsr
 pha
 and #1
 tax
 lda $C0B4,x
 pla
 lsr
 and #1
 tax
 lda $C0B6,x
 lda #0
 sta $C000
 cpy #9
 beq @bw
 sta $C00D                     ; latch 11 = COL140
 jmp @clock
@bw:
 sta $C00C                     ; latch 00 = BW560
@clock:
 sta $C05E
 sta $C05F
 sta $C05E
 sta $C05F
 cpy #5
 bcc @plain
 sta $C00D
 sta $C05E                     ; extended graphics, AN3 off
 jmp @arm
@plain:
 sta $C00C                     ; standard HGR, AN3 remains on
@arm:
 sta $C057
 sta $C054
 sta $C052
 sta $C050
 rts
_pu_restore:
 lda $C0B2
 lda $C0B4
 lda $C0B6
 lda $C051                     ; text before rebuilding /RAM
 rts
hr_modes: .byte 0,1,2,4,6,0,1,2,7,6
