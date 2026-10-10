; HGR handoff: everything executed after the first graphics byte is below
; $2000, including state and API-call/argument helpers. No linked cc65
; helper is called after the C driver returns. Source access is read-only.
.import _dv_entry
.importzp sp, ptr1, ptr2
.export _plugin_entry, _dh_map, _dh_length, _dh_unit, _dh_base, _dh_file, _dh_buffer
.export _dn_width, _dn_height, _dn_offset
.segment "HGRSAFE"
_plugin_entry:
 sta fieldlo+1
 sta fieldhi+1
 stx fieldlo+2
 stx fieldhi+2
 jsr _dv_entry
 cmp #1
 beq begin
 rts
begin:
 lda #0
 sta $C000                       ; 80STORE off, MAIN graphics page
 sta $C002
 sta $C004
 sta index
 sta failed
 sta ptr2
 lda #$20
 sta ptr2+1
 ldy #0
 lda #0
clearpage:
 sta (ptr2),y
 iny
 bne clearpage
 inc ptr2+1
 ldx ptr2+1
 cpx #$40
 bne clearpage
 lda #192
 sec
 sbc _dn_height
 lsr a
 sta drawrow
 lda #40
 sec
 sbc _dn_width
 lsr a
 sta left
 jsr placerow
sector:
 ldx index
 lda _dh_map,x
 sta secno
 lda _dh_map+1,x
 sta track
 ora secno
 bne allocated
 lda _dh_buffer
 sta ptr1
 lda _dh_buffer+1
 sta ptr1+1
 ldy #0
 lda #0
zero:
 sta (ptr1),y
 iny
 bne zero
 jmp copy
allocated:
 lda _dh_unit
 beq image
 sta parms+1
 ldx secno
 lda order,x
 pha
 lsr a
 sta parms+4
 lda track
 asl a
 asl a
 asl a
 ora parms+4
 sta parms+4
 lda track
 lsr a
 lsr a
 lsr a
 lsr a
 lsr a
 sta parms+5
 lda _dh_buffer
 sta parms+2
 sta ptr1
 lda _dh_buffer+1
 sta parms+3
 sta ptr1+1
 lda #$80
 jsr pushbyte
 lda #<parms
 ldx #>parms
 ldy #44                       ; mli(READ_BLOCK, parms)
 jsr call
 cmp #0
 beq readok
 pla
 jmp error
readok:
 pla
 and #1
 sta half
 jmp pointer
image:
 lda _dh_file
 ldx _dh_file+1
 jsr push
 lda _dh_base+3                ; fseek(file, base + (t*16+s)*256, SEEK_SET)
 ldx #0
 jsr push
 lda track
 asl a
 asl a
 asl a
 asl a
 ora secno
 clc
 adc _dh_base+1
 sta offset+1
 php
 lda track
 lsr a
 lsr a
 lsr a
 lsr a
 plp
 adc _dh_base+2
 sta offset+2
 lda _dh_base+3
 adc #0
 sta offset+3
 ; Replace the high word just pushed, then push the low word.
 ldy #0
 lda offset+2
 sta (sp),y
 iny
 lda offset+3
 sta (sp),y
 lda _dh_base
 ldx offset+1
 jsr push
 lda #2                        ; cc65 SEEK_SET (checked in dosview.c)
 ldx #0
 ldy #54
 jsr call
 cpx #0
 beq :+
 jmp error
:
 cmp #0
 beq :+
 jmp error
:
 lda _dh_buffer
 ldx _dh_buffer+1
 jsr push
 lda #1
 ldx #0
 jsr push
 lda #0
 ldx #1
 jsr push
 lda _dh_file
 ldx _dh_file+1
 ldy #48                       ; fread(buffer, 1, 256, file)
 jsr call
 cpx #1
 bne error
 cmp #0
 bne error
 lda _dh_file
 sta ptr1
 lda _dh_file+1
 sta ptr1+1
 ldy #1
 lda (ptr1),y                  ; cc65 FILE error flag, not short EOF
 and #4
 bne error
 lda #0
 sta half
pointer:
 lda _dh_buffer
 sta ptr1
 lda _dh_buffer+1
 clc
 adc half
 sta ptr1+1
copy:
 ldy #0
 lda index
 bne byte
 ldy _dn_offset
byte:
 lda (ptr1),y
 and #$7F
store:
 sta $2000
 inc store+1
 bne :+
 inc store+2
: lda _dh_length
 bne :+
 dec _dh_length+1
: dec _dh_length
 lda _dh_length
 ora _dh_length+1
 beq finish
 dec rowleft
 bne morebyte
 inc drawrow
 tya
 pha
 jsr placerow
 pla
 tay
morebyte:
 iny
 bne byte
 inc index
 inc index
 jmp sector
error:
 lda #1
 sta failed
finish:
 lda _dh_file
 ldx _dh_file+1
 ora _dh_file+1
 beq closed
 lda _dh_file
 ldy #52
 jsr call                      ; fclose even after a failed read/seek
 cpx #0
 bne errorclose
 cmp #0
 beq closed
errorclose:
 lda #1
 sta failed
closed:
 lda failed
 beq show
 ldy #92                       ; note: resident redraws and rereads panels
 jsr field
 sta ptr1
 stx ptr1+1
 ldy #0
message:
 lda reason,y
 sta (ptr1),y
 iny
 cmp #0
 bne message
 rts
show:
switches:
 sta $C00C                     ; 40 columns, single HGR, full page 1
 sta $C05F
 sta $C052
 sta $C054
 sta $C057
 sta $C050
 ldy #34                       ; wait_key; callbacks execute in resident
 jsr call
 sta $C051
 sta $C00D
 rts
; HGR row address, independent of the live source pointer in ptr1.
placerow:
 lda _dn_width
 sta rowleft
 lda drawrow
 pha
 and #7
 asl a
 asl a
 ora #$20
 sta ptr2+1
 pla
 pha
 and #$38
 lsr a
 lsr a
 lsr a
 lsr a
 ora ptr2+1
 sta ptr2+1
 pla
 pha
 and #8
 beq evenrow
 lda #$80
evenrow:
 sta ptr2
 pla
 lsr a
 lsr a
 lsr a
 lsr a
 lsr a
 lsr a
 tax
 lda ptr2
 clc
 adc rowoffset,x
 clc
 adc left
 sta store+1
 lda ptr2+1
 adc #0
 sta store+2
 rts
rowoffset: .byte 0,40,80
_dn_width: .res 1
_dn_height: .res 1
_dn_offset: .res 1
drawrow: .res 1
rowleft: .res 1
left: .res 1
; Local cc65 pushax: resident callbacks remove their arguments as usual.
pushbyte:
 pha
 lda sp
 bne :+
 dec sp+1
: dec sp
 ldy #0
 pla
 sta (sp),y
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
order: .byte 0,14,13,12,11,10,9,8,7,6,5,4,3,2,1,15
reason: .asciiz "DOS Newsroom read/close error."
parms: .byte 3,0,0,0,0,0
offset: .res 4
track: .res 1
secno: .res 1
half: .res 1
index: .res 1
failed: .res 1
_dh_map: .res 66
_dh_length: .res 2
_dh_unit: .res 1
_dh_base: .res 4
_dh_file: .res 2
_dh_buffer: .res 2
end:
.assert end <= $2000, lderror, "DOSVIEW HGR code/state overlaps the graphics page"
