; Read-only DOS adapter: FONTVIEW's exact HRCG renderer, no live I/O.
; Everything used after the first HGR write stays below $2000.
.export _plugin_entry, _df_tail, _df_count, _df_buf
.import _df_preflight, _df_wait_offset
.importzp ptr1, ptr3
.segment "HGRSAFE"
_plugin_entry:
 sta apilo+1
 sta apihi+1
 stx apilo+2
 stx apihi+2
 jsr _df_preflight
 cmp #1
 beq draw
 rts
draw:
 lda _df_wait_offset
 sta waitfield+1
 jsr hv_clear
 lda _df_buf
 sta ptr3
 lda _df_buf+1
 sta ptr3+1
 lda #0
 sta g
glyph:
 lda #0
 sta fr
.include "font_raw_glyph.inc"
 inc g
 lda g
 cmp _df_count
 beq done
 cmp #64
 beq tail
 lda ptr3
 clc
 adc #8
 sta ptr3
 bcc glyph
 inc ptr3+1
 jmp glyph
tail:
 lda #<_df_tail
 sta ptr3
 lda #>_df_tail
 sta ptr3+1
 jmp glyph
done:
 jsr hv_show
waitfield:
 ldy #0
apilo:
 lda $FFFF,y
 sta wait+1
 iny
apihi:
 lda $FFFF,y
 sta wait+2
wait:
 jsr $FFFF
 lda #0
 sta $C051
 sta $C00D
 rts
.include "font_hgr_screen.inc"
offsets: .byte 0,40,80
t: .res 2
g: .res 1
fr: .res 1
_df_buf: .res 2
_df_count: .res 1
_df_tail: .res 512
end:
.assert end <= $2000, lderror, "DOS font renderer/bitmap overlaps HGR"
