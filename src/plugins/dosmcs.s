.ifndef STAGE_LIMIT
STAGE_LIMIT=$3700
.endif
.ifndef STAGE_FLAGS
STAGE_FLAGS=5
.endif
; Two-stage import: C has returned and closed its DOS source before the
; loader borrows $0C00. Only ONE ProDOS FILE is open (its buffer is $0800).
; No code/return address in the overwritten overlay is used after fread.
.import _md_entrypoint, _md_player, _md_cpu_tag
.import __MCSHANDOFF_LOAD__, __MCSHANDOFF_SIZE__
.importzp sp, ptr1
.export _plugin_entry
.segment "CODE"
_plugin_entry:
 sta apilo+1
 stx apihi+1
 pha
 txa
 pha
apilo:
 lda #0
apihi:
 ldx #0
 jsr _md_entrypoint
 cmp #0
 bne copy
 pla
 pla
 rts
copy:
 ldx #0
@page:
 lda __MCSHANDOFF_LOAD__,x
 sta $0C00,x
 inx
 bne @page
 ldx #0
@tail:
 lda __MCSHANDOFF_LOAD__+$100,x
 sta $0D00,x
 inx
 cpx #<(__MCSHANDOFF_SIZE__-$100)
 bne @tail
 pla
 sta fieldhi+2
 sta fieldlo+2
 pla
 sta fieldhi+1
 sta fieldlo+1
 lda _md_cpu_tag
 sta cpu_tag+1
 lda _md_player
 sta fh
 lda _md_player+1
 sta fh+1
 jmp load
.segment "MCSHANDOFF"
load:
 lda #0
 sta failed
 lda #<$1B00
 ldx #>$1B00
 jsr push
 lda #1
 ldx #0
 jsr push
 lda #<(STAGE_LIMIT-$1B00)
 ldx #>(STAGE_LIMIT-$1B00)
 jsr push
 lda fh
 ldx fh+1
 ldy #48
 jsr call
 sta length
 stx length+1
 jsr errorflag
 beq :+
 jmp error
:
 ; A full window may conceal extra trailing bytes; EOF is checked even
 ; on this boundary, before closing and before executing the new code.
 lda #<probe
 ldx #>probe
 jsr push
 lda #1
 ldx #0
 jsr push
 lda #1
 ldx #0
 jsr push
 lda fh
 ldx fh+1
 ldy #48
 jsr call
 cpx #0
 bne error
 cmp #0
 bne error
 jsr errorflag
 bne error
 ; The sealed player length includes its whole code/data. A short file
 ; with a superficially valid eight-byte header is never executable.
 lda $1B00
 cmp #$FD
 bne error
 lda $1B01
 cmp #$A2
 bne error
 lda $1B02
 cmp #STAGE_FLAGS
 bne error
 lda $1B07
cpu_tag:
 cmp #1
 bne error
 lda $1B05
 cmp length
 bne error
 lda $1B06
 cmp length+1
 bne error
 lda length+1
 beq error
 ; Entry must belong to the loaded payload, after its eight-byte header.
 lda $1B04
 cmp #$1B
 bcc error
 cmp #>STAGE_LIMIT
 bcs error
 bne :+
 lda $1B03
 cmp #8
 bcc error
: clc
 lda length
 adc #<$1B00
 sta length
 lda length+1
 adc #>$1B00
 sta length+1
 lda $1B04
 cmp length+1
 bcc close
 bne error
 lda $1B03
 cmp length
 bcc close
error:
 lda #1
 sta failed
close:
 lda fh
 ldx fh+1
 ldy #52
 jsr call
 cpx #0
 bne closebad
 cmp #0
 beq closed
closebad:
 lda #1
 sta failed
closed:
 lda failed
 beq execute
 ldy #92
 jsr field
 sta ptr1
 stx ptr1+1
 ldy #0
@reason:
 lda reason,y
 sta (ptr1),y
 iny
 cmp #0
 bne @reason
 rts
execute:
 lda fieldlo+1
 ldx fieldlo+2
 jmp ($1B03)                ; inherits original resident return address
errorflag:
 lda fh
 sta ptr1
 lda fh+1
 sta ptr1+1
 ldy #1
 lda (ptr1),y
 and #4
 rts
push:
 pha
 lda sp
 sec
 sbc #2
 sta sp
 bcs :+
 dec sp+1
: ldy #1
 txa
 sta (sp),y
 dey
 pla
 sta (sp),y
 rts
call:
 pha
 txa
 pha
 jsr field
 sta target+1
 stx target+2
 pla
 tax
 pla
target:
 jmp $FFFF
field:
 iny
fieldhi:
 lda $FFFF,y
 tax
 dey
fieldlo:
 lda $FFFF,y
 rts
.if STAGE_FLAGS = 1
reason: .asciiz "IDENT read/close or version error."
.else
reason: .asciiz "MCSPLAY read/close or version error."
.endif
fh: .res 2
length: .res 2
failed: .res 1
probe: .res 1
end:
.assert end-$0C00 > $100, lderror, "DOSMCS handoff copy assumes more than one page"
.assert end-$0C00 < $200, lderror, "DOSMCS handoff exceeds its two-page copy"
