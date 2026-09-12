; pt3_lib_init.s

; Initialize a song

; this is done before song starts playing so it is not
; as performance / timing critical

	;====================================
	; pt3_init_song
	;====================================
	;
pt3_init_song:

	lda	#$0
	sta	DONE_SONG						; 3
	ldx	#(end_vars-begin_vars)
zero_song_structs_loop:
	dex
	sta	note_a,X
	bne	zero_song_structs_loop

	sta	pt3_noise_period_smc+1					; 4
	sta	pt3_noise_add_smc+1					; 4

	sta	pt3_envelope_period_l_smc+1				; 4
	sta	pt3_envelope_period_h_smc+1				; 4
	sta	pt3_envelope_slide_l_smc+1				; 4
	sta	pt3_envelope_slide_h_smc+1				; 4
	sta	pt3_envelope_slide_add_l_smc+1				; 4
	sta	pt3_envelope_slide_add_h_smc+1				; 4
	sta	pt3_envelope_add_smc+1					; 4
	sta	pt3_envelope_type_smc+1					; 4
	sta	pt3_envelope_type_old_smc+1				; 4
	sta	pt3_envelope_delay_smc+1				; 4
	sta	pt3_envelope_delay_orig_smc+1				; 4

	sta	PT3_MIXER_VAL						; 3

	sta	current_pattern_smc+1					; 4
	sta	current_line_smc+1					; 4
	sta	current_subframe_smc+1					; 4

	lda	#$f							; 2
	sta	note_a+NOTE_VOLUME					; 4
	sta	note_b+NOTE_VOLUME					; 4
	sta	note_c+NOTE_VOLUME					; 4

	; default ornament/sample in A
	; 	X is zero coming in here
	;ldx	#(NOTE_STRUCT_SIZE*0)					; 2
	jsr	load_ornament0_sample1					; 6+93

	; default ornament/sample in B
	ldx	#(NOTE_STRUCT_SIZE*1)					; 2
	jsr	load_ornament0_sample1					; 6+93

	; default ornament/sample in C
	ldx	#(NOTE_STRUCT_SIZE*2)					; 2
	jsr	load_ornament0_sample1					; 6+93

	;=======================
	; load default speed

header_patch_8:
	lda	PT3_LOC+PT3_SPEED					; 4
	sta	pt3_speed_smc+1						; 4

	;=======================
	; load loop

header_patch_9:
	lda	PT3_LOC+PT3_LOOP					; 4
	sta	LOOP						; 4


	;========================
	;========================
	; set up note/freq table
	; this saves some space and makes things marginally faster longrun
	;========================
	;========================
	; note (heh) that there are separate tables if version 3.3
	; but we are going to assume we are only going to be playing
	; newer 3.4+ version files so only need the newer tables

 jsr make_frequency_table

	;======================
	; calculate version
	ldx	#6							; 2
header_patch_10:
	lda	PT3_LOC+PT3_VERSION					; 4
	sec								; 2
	sbc	#'0'							; 2
	cmp	#9							; 2
	bcs	not_ascii_number	; bge				; 2/3
	tax								; 2

not_ascii_number:

	; adjust version<6 SMC code in the slide code

	; FIXME: I am sure there's a more clever way to do this

	lda	#$2C		; BIT					; 2
	cpx	#$6							; 2
	bcs	version_greater_than_or_equal_6	; bgt			; 3
	; less than 6, jump
	; also carry is known to be clear
	adc	#$20		; BIT->JMP  2C->4C			; 2
version_greater_than_or_equal_6:
	sta	version_smc						; 4

pick_volume_table:

	;=======================
	; Pick which volume number, based on version

	; if (PlParams.PT3.PT3_Version <= 4)

	cpx	#5							; 2

	; carry clear = 3.3/3.4 table
	; carry set = 3.5 table

	;==========================
	; VolTableCreator
	;==========================
	; Creates the appropriate volume table
	; based on z80 code by Ivan Roshin ZXAYHOBETA/VTII10bG.asm
	;

	; Called with carry==0 for 3.3/3.4 table
	; Called with carry==1 for 3.5 table

	; 177f-1932 = 435 bytes, not that much better than 512 of lookup


VolTableCreator:

	; Init initial variables
	lda	#$0
	sta	z80_d_smc+1
	ldy	#$11

	; Set up self modify

	ldx	#$2A		; ROL for self-modify
	bcs	vol_type_35

vol_type_33:

	; For older table, we set initial conditions a bit
	; different

	dey
	tya

	ldx	#$ea		; NOP for self modify

vol_type_35:
	sty	z80_l_smc+1	; l=16 or 17
	sta	z80_e_smc+1	; e=16 or 0
	stx	vol_smc		; set the self-modify code

	ldy	#16		; skip first row, all zeros
	ldx	#16		; c=16
vol_outer:
	clc			; add HL,DE
z80_l_smc:
	lda	#$d1
z80_e_smc:
	adc	#$d1
	sta	z80_e_smc+1
	lda	#0
z80_d_smc:
	adc	#$d1
	sta	z80_d_smc+1	; carry is important

			; sbc hl,hl
	lda	#0
	adc	#$ff
	eor	#$ff

vol_write:
	sta	z80_h_smc+1
	pha

vol_inner:
	pla
	pha

vol_smc:
	nop			; nop or ROL depending

z80_h_smc:
	lda	#$d1

	adc	#$0		; a=a+carry;

patch_table_18:
	sta	VolumeTable,Y
	iny

	pla			; add HL,DE
	adc	z80_e_smc+1
	pha
	lda	z80_h_smc+1
	adc	z80_d_smc+1
	sta	z80_h_smc+1

	inx		; inc C
	txa		; a=c
	and	#$f
	bne	vol_inner


	pla

	lda	z80_e_smc+1	; a=e
	cmp	#$77
	bne	vol_m3

	inc	z80_e_smc+1

vol_m3:
	txa			; a=c
	bne	vol_outer

vol_done:
	rts


	;=========================================
	; copy note table seed to proper location
	;=========================================

; faster inlined

;NoteTableCopy:

;	ldy	#11			; !2
;note_table_copy_loop:
;ntc_smc1:
;	lda	base1_high,Y		; !3
;	sta	NoteTable_high,Y	; !3
;ntc_smc2:
;	lda	base1_low,Y		; !3
;	sta	NoteTable_low,Y		; !3
;	dey				; !1
;	bpl	note_table_copy_loop	; !2
;	rts				; !1


	;==========================================
	; propogate the freq down, dividing by two
	;==========================================
NoteTablePropogate:

	ldy	#0
note_table_propogate_loop:
	clc
patch_table_19:
	lda	NoteTable_high,Y
	ror
patch_table_20:
	sta	NoteTable_high+12,Y

patch_table_21:
	lda	NoteTable_low,Y
	ror
patch_table_22:
	sta	NoteTable_low+12,Y

	iny
	cpy	#84
	bne	note_table_propogate_loop

	rts


	;================================================
	; propogation isn't enough, various values
	; are often off by one, so adjust using a bitmask
	;================================================
NoteTableAdjust:

	ldx	#0
note_table_adjust_outer:

note_table_adjust_smc:
	lda	freq_0+24,X
	sta	PT3_TEMP

	; reset smc
	lda table_base
	sta	ntl_smc+1
	lda table_base+1
	sta	ntl_smc+2


	ldy	#7
note_table_adjust_inner:
	ror	PT3_TEMP
	bcc	note_table_skip_adjust

ntl_smc:
patch_table_23:
	inc	NoteTable_low,X

note_table_skip_adjust:
	clc
	lda	#12
	adc	ntl_smc+1
	sta	ntl_smc+1
	lda	#0
	adc	ntl_smc+2	; unnecessary if aligned
	sta	ntl_smc+2

skip_adjust_done:
	dey
	bpl	note_table_adjust_inner

	inx
	cpx	#12
	bne	note_table_adjust_outer

	rts


; All seven historical tables: one seed octave plus rounding bitmasks.
; The full archived 96-word tables remain the independent test oracle.
make_frequency_table:
header_patch_11:
 ldx PT3_LOC+PT3_HEADER_FREQUENCY
header_patch_12:
 lda PT3_LOC+PT3_VERSION
 cmp #'0'
 bcc freq_modern
 cmp #'4'
 bcc freq_pick
freq_modern:
 txa
 ora #4
 tax
freq_pick:
 lda freq_choices,x
 sta freq_choice
 tax
 lda freq_ptr_low,x
 sta SAMPLE_L
 lda freq_ptr_high,x
 sta SAMPLE_H
 ldy #0
 ldx #0
freq_copy:
 lda (SAMPLE_L),y
patch_table_7:
 sta NoteTable_low,x
 iny
 lda (SAMPLE_L),y
patch_table_8:
 sta NoteTable_high,x
 iny
 inx
 cpx #12
 bne freq_copy
 clc
 lda SAMPLE_L
 adc #24
 sta note_table_adjust_smc+1
 lda SAMPLE_H
 adc #0
 sta note_table_adjust_smc+2
 jsr NoteTablePropogate
 jsr NoteTableAdjust
 lda table_base
 sta GUARD
 lda table_base+1
 sta GUARD+1
 lda freq_choice
 cmp #2
 bne freq_asm
 ldy #23
 lda #$FD
 sta (GUARD),y
 ldy #46
 lda (GUARD),y
 sec
 sbc #1
 sta (GUARD),y
 rts
freq_asm:
 cmp #3
 bne freq_done
 ldy #86
 lda (GUARD),y
 clc
 adc #1
 sta (GUARD),y
 iny
 lda (GUARD),y
 clc
 adc #1
 sta (GUARD),y
freq_done:
 rts
freq_choice: .byte 0
freq_choices: .byte 0,2,3,5,1,2,4,6
freq_ptr_low: .byte <freq_0,<freq_1,<freq_2,<freq_3,<freq_4,<freq_5,<freq_6
freq_ptr_high: .byte >freq_0,>freq_1,>freq_2,>freq_3,>freq_4,>freq_5,>freq_6
freq_0:
 .word $0C21,$0B73,$0ACE,$0A33,$09A0,$0916,$0893,$0818,$07A4,$0736,$06CE,$066D
 .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
freq_1:
 .word $0C22,$0B73,$0ACF,$0A33,$09A1,$0917,$0894,$0819,$07A4,$0737,$06CF,$066D
 .byte $40,$E6,$9C,$66,$40,$2C,$20,$30,$48,$6C,$1C,$5A
freq_2:
 .word $0EF8,$0E10,$0D60,$0C80,$0BD8,$0B28,$0A88,$09F0,$0960,$08E0,$0858,$07E0
 .byte $00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00,$00
freq_3:
 .word $0D3E,$0C80,$0BCC,$0B22,$0A82,$09EC,$095C,$08D6,$0858,$07E0,$076E,$0704
 .byte $F8,$80,$90,$C0,$04,$F0,$F8,$EC,$E0,$C0,$FC,$40
freq_4:
 .word $0D10,$0C55,$0BA4,$0AFC,$0A5F,$09CA,$093D,$08B8,$083B,$07C5,$0755,$06EC
 .byte $20,$A8,$40,$F8,$BC,$90,$78,$70,$74,$08,$2A,$50
freq_5:
 .word $0CDA,$0C22,$0B73,$0ACF,$0A33,$09A1,$0917,$0894,$0819,$07A4,$0737,$06CF
 .byte $B4,$40,$E6,$9C,$66,$40,$2C,$28,$30,$48,$6C,$1C
freq_6:
 .word $0CDA,$0C22,$0B73,$0ACF,$0A33,$09A1,$0917,$0894,$0819,$07A4,$0737,$06CF
 .byte $B4,$40,$E6,$9C,$66,$40,$2C,$20,$30,$48,$6C,$1C

; Table #1 of Pro Tracker 3.3x - 3.5x
;PT3NoteTable_ST_high:
;.byte $0E,$0E,$0D,$0C,$0B,$0B,$0A,$09
;.byte $09,$08,$08,$07,$07,$07,$06,$06
;.byte $05,$05,$05,$04,$04,$04,$04,$03
;.byte $03,$03,$03,$03,$02,$02,$02,$02
;.byte $02,$02,$02,$01,$01,$01,$01,$01
;.byte $01,$01,$01,$01,$01,$01,$01,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00

;PT3NoteTable_ST_low:
;.byte $F8,$10,$60,$80,$D8,$28,$88,$F0
;.byte $60,$E0,$58,$E0,$7C,$08,$B0,$40
;.byte $EC,$94,$44,$F8,$B0,$70,$2C,$FD
;.byte $BE,$84,$58,$20,$F6,$CA,$A2,$7C
;.byte $58,$38,$16,$F8,$DF,$C2,$AC,$90
;.byte $7B,$65,$51,$3E,$2C,$1C,$0A,$FC
;.byte $EF,$E1,$D6,$C8,$BD,$B2,$A8,$9F
;.byte $96,$8E,$85,$7E,$77,$70,$6B,$64
;.byte $5E,$59,$54,$4F,$4B,$47,$42,$3F
;.byte $3B,$38,$35,$32,$2F,$2C,$2A,$27
;.byte $25,$23,$21,$1F,$1D,$1C,$1A,$19
;.byte $17,$16,$15,$13,$12,$11,$10,$0F


; Table #2 of Pro Tracker 3.4x - 3.5x
;PT3NoteTable_ASM_34_35_high:
;.byte $0D,$0C,$0B,$0A,$0A,$09,$09,$08
;.byte $08,$07,$07,$06,$06,$06,$05,$05
;.byte $05,$04,$04,$04,$04,$03,$03,$03
;.byte $03,$03,$02,$02,$02,$02,$02,$02
;.byte $02,$01,$01,$01,$01,$01,$01,$01
;.byte $01,$01,$01,$01,$01,$00,$00,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00
;.byte $00,$00,$00,$00,$00,$00,$00,$00

;PT3NoteTable_ASM_34_35_low:
;.byte $10,$55,$A4,$FC,$5F,$CA,$3D,$B8
;.byte $3B,$C5,$55,$EC,$88,$2A,$D2,$7E
;.byte $2F,$E5,$9E,$5C,$1D,$E2,$AB,$76
;.byte $44,$15,$E9,$BF,$98,$72,$4F,$2E
;.byte $0F,$F1,$D5,$BB,$A2,$8B,$74,$60
;.byte $4C,$39,$28,$17,$07,$F9,$EB,$DD
;.byte $D1,$C5,$BA,$B0,$A6,$9D,$94,$8C
;.byte $84,$7C,$75,$6F,$69,$63,$5D,$58
;.byte $53,$4E,$4A,$46,$42,$3E,$3B,$37
;.byte $34,$31,$2F,$2C,$29,$27,$25,$23
;.byte $21,$1F,$1D,$1C,$1A,$19,$17,$16
;.byte $15,$14,$12,$11,$10,$0F,$0E,$0D


;PT3VolumeTable_33_34:
;.byte $0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0
;.byte $0,$0,$0,$0,$0,$0,$0,$0,$1,$1,$1,$1,$1,$1,$1,$1
;.byte $0,$0,$0,$0,$0,$0,$1,$1,$1,$1,$1,$2,$2,$2,$2,$2
;.byte $0,$0,$0,$0,$1,$1,$1,$1,$2,$2,$2,$2,$3,$3,$3,$3
;.byte $0,$0,$0,$0,$1,$1,$1,$2,$2,$2,$3,$3,$3,$4,$4,$4
;.byte $0,$0,$0,$1,$1,$1,$2,$2,$3,$3,$3,$4,$4,$4,$5,$5
;.byte $0,$0,$0,$1,$1,$2,$2,$3,$3,$3,$4,$4,$5,$5,$6,$6
;.byte $0,$0,$1,$1,$2,$2,$3,$3,$4,$4,$5,$5,$6,$6,$7,$7
;.byte $0,$0,$1,$1,$2,$2,$3,$3,$4,$5,$5,$6,$6,$7,$7,$8
;.byte $0,$0,$1,$1,$2,$3,$3,$4,$5,$5,$6,$6,$7,$8,$8,$9
;.byte $0,$0,$1,$2,$2,$3,$4,$4,$5,$6,$6,$7,$8,$8,$9,$A
;.byte $0,$0,$1,$2,$3,$3,$4,$5,$6,$6,$7,$8,$9,$9,$A,$B
;.byte $0,$0,$1,$2,$3,$4,$4,$5,$6,$7,$8,$8,$9,$A,$B,$C
;.byte $0,$0,$1,$2,$3,$4,$5,$6,$7,$7,$8,$9,$A,$B,$C,$D
;.byte $0,$0,$1,$2,$3,$4,$5,$6,$7,$8,$9,$A,$B,$C,$D,$E
;.byte $0,$1,$2,$3,$4,$5,$6,$7,$8,$9,$A,$B,$C,$D,$E,$F

;PT3VolumeTable_35:
;.byte $0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0,$0
;.byte $0,$0,$0,$0,$0,$0,$0,$0,$1,$1,$1,$1,$1,$1,$1,$1
;.byte $0,$0,$0,$0,$1,$1,$1,$1,$1,$1,$1,$1,$2,$2,$2,$2
;.byte $0,$0,$0,$1,$1,$1,$1,$1,$2,$2,$2,$2,$2,$3,$3,$3
;.byte $0,$0,$1,$1,$1,$1,$2,$2,$2,$2,$3,$3,$3,$3,$4,$4
;.byte $0,$0,$1,$1,$1,$2,$2,$2,$3,$3,$3,$4,$4,$4,$5,$5
;.byte $0,$0,$1,$1,$2,$2,$2,$3,$3,$4,$4,$4,$5,$5,$6,$6
;.byte $0,$0,$1,$1,$2,$2,$3,$3,$4,$4,$5,$5,$6,$6,$7,$7
;.byte $0,$1,$1,$2,$2,$3,$3,$4,$4,$5,$5,$6,$6,$7,$7,$8
;.byte $0,$1,$1,$2,$2,$3,$4,$4,$5,$5,$6,$7,$7,$8,$8,$9
;.byte $0,$1,$1,$2,$3,$3,$4,$5,$5,$6,$7,$7,$8,$9,$9,$A
;.byte $0,$1,$1,$2,$3,$4,$4,$5,$6,$7,$7,$8,$9,$A,$A,$B
;.byte $0,$1,$2,$2,$3,$4,$5,$6,$6,$7,$8,$9,$A,$A,$B,$C
;.byte $0,$1,$2,$3,$3,$4,$5,$6,$7,$8,$9,$A,$A,$B,$C,$D
;.byte $0,$1,$2,$3,$4,$5,$6,$7,$7,$8,$9,$A,$B,$C,$D,$E
;.byte $0,$1,$2,$3,$4,$5,$6,$7,$8,$9,$A,$B,$C,$D,$E,$F
