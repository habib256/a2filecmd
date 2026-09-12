; One alternate decoder context. Swap only explicit mutable state, never
; unrelated code, AUX, stack or file buffers. Runtime tables have separate homes.
.ifndef PT3_HEADER_XOR
PT3_HEADER_XOR=$0E
.endif
.export _pt_swap
.segment "BSS"
other_notes: .res 120
other_zp: .res 32
other_smc: .res 18
.segment "CODE"
_pt_swap:
 ldx #119
@notes:
 lda note_a,x
 ldy other_notes,x
 sta other_notes,x
 tya
 sta note_a,x
 dex
 bpl @notes
 ldx #31
@zp:
 lda song_zp,x
 ldy other_zp,x
 sta other_zp,x
 tya
 sta song_zp,x
 dex
 bpl @zp
 ldx #0
@smc:
 lda context_patches,x
 sta ptr1
 lda context_patches+1,x
 sta ptr1+1
 txa
 lsr
 tay
 lda other_smc,y
 pha
 ldy #0
 lda (ptr1),y
 pha
 txa
 lsr
 tay
 pla
 sta other_smc,y
 pla
 ldy #0
 sta (ptr1),y
 inx
 inx
 cpx #context_patches_end-context_patches
 bne @smc
 ldy #header_runtime_end-header_patches
 lda _pt_running
 cmp #5
 bcs :+
 ldy #header_patches_end-header_patches
: sty header_patch_limit+1
 ldx #0
header_loop:
 lda header_patches,x
 sta ptr1
 lda header_patches+1,x
 sta ptr1+1
 ldy #0
 lda (ptr1),y
 eor #PT3_HEADER_XOR                       ; $3700 <-> $3900
 sta (ptr1),y
 inx
 inx
header_patch_limit:
 cpx #header_patches_end-header_patches
 bne header_loop
 rts
; Per-note scratch operands are assigned before use within each frame.
; Only the following operands persist between frame calls.
context_patches:
 .word pt3_pattern_done_smc+1
 .word current_line_smc+1
 .word current_pattern_smc+1
 .word current_subframe_smc+1
 .word pt3_envelope_delay_orig_smc+1
 .word pt3_envelope_delay_smc+1
 .word pt3_envelope_period_h_smc+1
 .word pt3_envelope_period_l_smc+1
 .word pt3_envelope_slide_add_h_smc+1
 .word pt3_envelope_slide_add_l_smc+1
 .word pt3_envelope_slide_h_smc+1
 .word pt3_envelope_slide_l_smc+1
 .word pt3_envelope_type_old_smc+1
 .word pt3_envelope_type_smc+1
 .word pt3_noise_add_smc+1
 .word pt3_noise_period_smc+1
 .word pt3_speed_smc+1
 .word version_smc
context_patches_end:
header_patches:
 .word header_patch_0+2
 .word header_patch_1+2
 .word header_patch_2+2
 .word header_patch_3+2
 .word header_patch_4+2
 .word header_patch_5+2
 .word header_patch_6+2
 .word header_patch_7+2
header_runtime_end:
 .word header_patch_8+2
 .word header_patch_9+2
 .word header_patch_10+2
 .word header_patch_11+2
 .word header_patch_12+2
header_patches_end:
