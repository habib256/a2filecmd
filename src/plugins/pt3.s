; Foreground adapter for Vince Weaver's 0BSD PT3 core.
; Every indirect module read is bounded. A 255-read frame budget bounds
; malformed command loops. Decoder ZP and IRQ state never escape a call.
.export _pt_init, _pt_frame, _pt_end, _pt_regs
.importzp ptr1
.import _pt_pages, _pt_page
PT3_LOC=$3300                    ; resident header only
PT3_DATA_BASE=0                  ; decoder pointers are logical file offsets
PT3_DISABLE_SWITCHABLE_FREQ_CONVERSION=1
.include "pt3lib/zp.inc"
GUARD=$6C
.segment "BSS"
_pt_end: .res 2
saved_sp: .res 1
host_zp: .res 32
song_zp: .res 32
_pt_regs: .res 14
guard_y: .res 1
guard_byte: .res 1
guard_budget: .res 1
result: .res 1
.segment "CODE"
_pt_init:
 lda #0
 ldx #31
@zero:
 sta song_zp,x
 dex
 bpl @zero
 lda #<pt3_init_song
 sta call_song+1
 lda #>pt3_init_song
 bne pt_enter
_pt_frame:
 lda #<pt3_make_frame
 sta call_song+1
 lda #>pt3_make_frame
pt_enter:
 sta call_song+2
 php
 sei
 cld
 tsx
 stx saved_sp
 ldx #31
@save:
 lda $60,x
 sta host_zp,x
 lda song_zp,x
 sta $60,x
 dex
 bpl @save
 lda #0
 sta result
 sta guard_budget
call_song:
 jsr $FFFF
 lda DONE_SONG
 beq pt_leave
 lda #2
 sta result
 bne pt_leave
pt_abort:
 ldx saved_sp
 txs
 lda #1
 sta result
pt_leave:
 ldx #13
@regs:
 lda AY_REGISTERS,x
 sta _pt_regs,x
 dex
 bpl @regs
 ldx #31
@restore:
 lda $60,x
 sta song_zp,x
 lda host_zp,x
 sta $60,x
 dex
 bpl @restore
 plp
 lda result
 ldx #0
 rts

checked_sample:
 php
 txa
 pha
 ldx #SAMPLE_L
 bne checked
checked_ornament:
 php
 txa
 pha
 ldx #ORNAMENT_L
 bne checked
checked_pattern:
 php
 txa
 pha
 ldx #PATTERN_L
checked:
 sty guard_y
 dec guard_budget
 beq pt_abort
 tya
 clc
 adc $00,x
 sta GUARD
 lda $01,x
 adc #0
 bcs pt_abort                    ; never wrap a file offset to the header
 sta GUARD+1
 cmp _pt_end+1
 bcc @page
 bne pt_abort
 lda GUARD
 cmp _pt_end
 bcs pt_abort
@page:
 ldy GUARD+1
 lda _pt_pages,y
 bne @mapped
 ; A cache miss can call resident stdio/MLI. Give it the host ZP and
 ; restore the decoder ZP afterwards, even when it reports an I/O error.
 ldx #31
@host:
 lda $60,x
 sta song_zp,x
 lda host_zp,x
 sta $60,x
 dex
 bpl @host
 tya
 jsr _pt_page
 sta guard_byte
 ldx #31
@song:
 lda song_zp,x
 sta $60,x
 dex
 bpl @song
 lda guard_byte
 bne @mapped
 jmp pt_abort
@mapped:
 sta GUARD+1
@read:
 ldy #0
 lda (GUARD),y
 sta guard_byte
 pla
 tax
 plp
 ldy guard_y
 lda guard_byte
 rts
.include "pt3lib/core.inc"
.include "pt3lib/init.inc"

; VIA timer polling, no new IRQ vector; channel A/B/C on the first AY.
.export _pt_hw_start, _pt_tick, _pt_output, _pt_silence, _pt_hw_stop
.segment "BSS"
card: .res 1
old_acr: .res 1
.segment "CODE"
pt_via:
 lda #0
 sta ptr1
 lda card
 sta ptr1+1
 rts
_pt_hw_start:
 ora #$C0
 sta card
 jsr pt_via
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
_pt_tick:
 jsr pt_via
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
pt_write:
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
_pt_output:
 jsr pt_via
 ldx #0
@reg:
 lda _pt_regs,x
 cpx #13
 bne @write
 cmp #$FF
 beq @next
@write:
 jsr pt_write
@next:
 inx
 cpx #14
 bne @reg
 rts
_pt_silence:
 jsr pt_via
 ldx #7
 lda #$3F
 jsr pt_write
 ldx #8
 lda #0
 jsr pt_write
 inx
 lda #0
 jsr pt_write
 inx
 lda #0
 jmp pt_write
_pt_hw_stop:
 jsr _pt_silence
 ldy #$0E
 lda #$7F
 sta (ptr1),y
 ldy #4
 lda (ptr1),y
 ldy #$0B
 lda old_acr
 sta (ptr1),y
 rts

; The caller lends copy_buf (512 bytes) to the 448-byte tone/volume tables.
; Patch only explicit operand locations, never scan and replace code bytes.
.export _pt_tables
.importzp ptr2
.segment "BSS"
table_base: .res 2
.segment "CODE"
_pt_tables:
 sta table_base
 sta ptr2
 stx table_base+1
 stx ptr2+1
 ldx #0
@patch:
 lda table_patches,x
 sta ptr1
 lda table_patches+1,x
 sta ptr1+1
 lda table_patches+2,x
 clc
 adc ptr2
 ldy #0
 sta (ptr1),y
 lda ptr2+1
 adc #0
 iny
 sta (ptr1),y
 inx
 inx
 inx
 cpx #table_patches_end-table_patches
 bne @patch
 rts
table_patches:
 .word patch_table_0+1
 .byte 0
 .word patch_table_1+1
 .byte 96
 .word patch_table_2+1
 .byte 192
 .word patch_table_3+1
 .byte 0
 .word patch_table_4+1
 .byte 96
 .word patch_table_5+1
 .byte 0
 .word patch_table_6+1
 .byte 96
 .word patch_table_7+1
 .byte 96
 .word patch_table_8+1
 .byte 0
 .word patch_table_9+1
 .byte 96
 .word patch_table_10+1
 .byte 96
 .word patch_table_11+1
 .byte 0
 .word patch_table_12+1
 .byte 96
 .word patch_table_13+1
 .byte 0
 .word patch_table_14+1
 .byte 23
 .word patch_table_15+1
 .byte 46
 .word patch_table_16+1
 .byte 96
 .word patch_table_17+1
 .byte 0
 .word patch_table_18+1
 .byte 192
 .word patch_table_19+1
 .byte 96
 .word patch_table_20+1
 .byte 108
 .word patch_table_21+1
 .byte 0
 .word patch_table_22+1
 .byte 12
 .word patch_table_23+1
 .byte 0
table_patches_end:
