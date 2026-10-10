; Stage and commit graphics without writing resident MAIN or executing AUX.
; C returns before AUX bitmap replaces MAIN $2000-$3FFF. Plain 6502.
 .export _plugin_entry, _vg_write, _vg_read
 .import _vg_run, _vg_addr, _vg_buf, _vg_count
 .importzp ptr1
 .segment "VGDATA"
safe_api: .word 0
flags: .byte 0
 .segment "VGTAIL"
_plugin_entry:
 sta safe_api
 stx safe_api+1
 jsr _vg_run
 sta flags
 and #4
 beq @cleanup
 lda #$40
 jsr commit             ; AUX $4000 -> MAIN $2000
 lda flags
 and #2
 beq @show
 lda #$20
 sta $3D
 sta $43
 lda #0
 sta $3C
 sta $42
 lda #$FF
 sta $3E
 lda #$3F
 sta $3F
 php
 sei
 sec
 jsr $C311             ; MAIN $2000 -> AUX $2000
 plp
 lda #$60
 jsr commit             ; AUX $6000 -> MAIN $2000
@show:
 lda flags
 and #2
 tax
 sta $C000
 sta $C00D
 sta $C05E
 sta $C05F
 sta $C05E
 sta $C05F
 cpx #0
 beq @plain
 sta $C05E
 bne @arm
@plain:
 sta $C00C
@arm:
 sta $C057
 sta $C054
 sta $C052
 sta $C050
 ldy #34               ; api->wait_key()
 jsr callback
@cleanup:
 sta $C000
 sta $C002
 sta $C004
 sta $C054
 sta $C05F
 sta $C00D
 sta $C051
 lda flags
 and #1
 beq @done
 ldy #98               ; api->ram_format(), overwrites MAIN $2000-$21FF
 jsr callback
 bne @done
 lda safe_api
 sta ptr1
 lda safe_api+1
 sta ptr1+1
 ldy #92
 lda (ptr1),y
 tax
 iny
 lda (ptr1),y
 sta ptr1+1
 stx ptr1
 ldy #0
@error:
 lda ram_error,y
 sta (ptr1),y
 beq @done
 iny
 bne @error
@done:
 rts
ram_error:
 .asciiz "AUX used; /RAM erased; rebuild failed."
commit:
 sta $3D
 clc
 adc #$1F
 sta $3F
 lda #0
 sta $3C
 sta $42
 lda #$FF
 sta $3E
 lda #$20
 sta $43
 php
 sei
 clc
 jsr $C311
 plp
 rts
callback:
 lda safe_api
 sta ptr1
 lda safe_api+1
 sta ptr1+1
 lda (ptr1),y
 sta call+1
 iny
 lda (ptr1),y
 sta call+2
call:
 jmp $FFFF
_vg_write:             ; __fastcall__ value; writes one validated AUX byte
 pha
 lda _vg_addr
 sta ptr1
 lda _vg_addr+1
 sta ptr1+1
 pla
 ldy #0
 php
 sei
 sta $C005
 sta (ptr1),y
 sta $C004
 plp
 rts
_vg_read:              ; validated range to MAIN buffer via ROM AUXMOVE
 lda _vg_addr
 sta $3C
 clc
 adc _vg_count
 sta $3E
 lda _vg_addr+1
 sta $3D
 adc _vg_count+1
 sta $3F
 lda $3E
 bne @last
 dec $3F
@last:
 dec $3E
 lda _vg_buf
 sta $42
 lda _vg_buf+1
 sta $43
 php
 sei
 clc
 jsr $C311
 plp
 rts
