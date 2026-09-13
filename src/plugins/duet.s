; duet.s -- Electric Duet playback: the speaker player and the AY helpers.
;
; The speaker player is Alex Patalenski's improved Electric Duet player
; (circa 1989, published by Emil Dotchevski; the one Apple II DeskTop
; uses): it plays Paul Lutus's song files without the carrier whistle of
; the original routine. It is transcribed instruction for instruction from
; the $2800 listing: the two pulse waves come from counting iterations of
; one 73-cycle loop, so every instruction of that loop, its NOPs and its
; equal-length paths, is kept as it was. Only three things change: the
; zero page is cc65's scratch (ptr1-ptr3, tmp1-tmp3) instead of $1E/$1F
; and $D2-$D8, the loop sits in a 128-byte aligned segment so no taken
; branch crosses a page (a crossing would add a cycle and detune a voice),
; and a voice record (first byte 1, the duty shifts of the original player,
; which this one derives from the pitch) is skipped instead of being played
; as a one-unit blip. The keyboard is read once per record, as it was.
;
; The AY helpers poll VIA timer 1, as MUSIC does: no interrupt vector.
; Nothing here touches AUX or the disk.
.importzp ptr1, ptr2, ptr3, tmp1, tmp2, tmp3
.export _ed_pos, _ed_speaker, _ed_pulse
.export _ay_start, _ay_tick, _ay_write, _ay_silence, _ay_stop

; Patalenski's zero page, on cc65's scratch page.
SONG    = ptr1          ; $1E/$1F  the current three-byte record
DUR     = tmp1          ; $D2      duration, in units of 256 iterations
COUNT   = tmp2          ; $D3      the 256-iteration counter
PITCH   = ptr2          ; $D4/$D5  the two pitches (iterations per period)
DUTY    = ptr3          ; $D6/$D7  where each pulse falls (pitch/4 or /16)
PHASE   = tmp3          ; $D8      bit 7: the speaker's current level

SPKR    = $C030
KBD     = $C000

.segment "BSS"
_ed_pos:   .res 2       ; C: unsigned char* -- the record to play next
card:      .res 1
old_acr:   .res 1

.segment "CODE"
; unsigned char ed_speaker(void): plays from ed_pos until the terminator
; (returns 0) or a key (returns the $C000 byte, strobe untouched, ed_pos
; on the interrupted record so a second call resumes there).
_ed_speaker:
        lda _ed_pos
        sta SONG
        lda _ed_pos+1
        sta SONG+1
        lda #0                  ; $2800
        sta PHASE
        sta DUTY
        sta DUTY+1
l08:    ldy #0                  ; $2808: the next record
        lda (SONG),y
        bne l0F
        tax                     ; the terminator: 0
        rts
l0F:    cmp #1                  ; a voice record: nothing to play
        bne :+
        jmp lA5
:       sta DUR
        lda KBD                 ; $2811: a key ends the note
        bmi key_done
        ldx #0                  ; $2816: voice 1
        jsr sub
        sta m1+1
        sta m2+1
        stx m1+4
        stx m2+4
        ldx #1                  ; $2827: voice 2
        jsr sub
        sta m3+1
        sta m4+1
        stx m3+4
        stx m4+4
        lda #0                  ; $2838
        ldx #$8A
        ldy #$40
        sta COUNT
        jmp l40
key_done:
        ldx SONG                ; a key: keep the record for a resume
        stx _ed_pos
        ldx SONG+1
        stx _ed_pos+1
        ldx #0
        rts
; void __fastcall__ ed_pulse(unsigned char n): the pulse width, 1/16 (0),
; 1/8 (1) or 1/4 (2) of the period -- the first two shifts of sub, or NOPs.
_ed_pulse:
        ldx #$4A
        cmp #2
        bcc :+
        ldx #$EA
:       stx ed_lsr
        ldx #$4A
        cmp #1
        bcc :+
        ldx #$EA
:       stx ed_lsr+1
        rts
; $28B3: X = voice. The pitch, its duty point, and A/X = the operands
; of that voice's BIT and EOR: $30/$A0 for a tone, unchanged for a rest
; (BIT $C000 and EOR #0 or #1 then touch neither the speaker nor bit 7).
; The original narrows every pulse to 1/16 of its period (four shifts);
; C turns the first two shifts into NOPs (ed_lsr) for 1/8 or 1/4: wider
; pulses carry more fundamental, which the bass needs on a small speaker.
sub:    iny
        lda (SONG),y
        php
        sta PITCH,x
        cmp #5
        bcc :+
ed_lsr: lsr
        lsr
:       lsr
        lsr
        sta DUTY,x
        plp
        beq :+
        lda #$30
        ldx #$A0
:       rts

; The 73-cycle loop, $2840-$28B2 of the original: within one page.
.segment "LOOP"
.align 128
l40:    sta PHASE               ; $2840
        dey
        bne l53
        ldy PITCH               ; $2845: voice 1 rises
        bit PHASE
        bmi l64
m1:     bit SPKR                ; $284B: operand $30 (tone) or $00 (rest)
        eor #$A0                ; $284E: operand $A0 (tone) or $00 (rest)
        jmp l68
l53:    cpy DUTY                ; $2853: voice 1 falls
        bne l63
        bit PHASE
        bpl l65
m2:     bit SPKR                ; $285B
        eor #$A0
        jmp l69
l63:    nop                     ; $2863
l64:    nop
l65:    nop
        nop
        nop
l68:    nop
l69:    nop
        sta PHASE               ; $286A
        dex
        bne l7D
        ldx PITCH+1             ; $286F: voice 2 rises
        bit PHASE
        bmi l8E
m3:     bit SPKR                ; $2875
        eor #$A0
        jmp l92
l7D:    cpx DUTY+1              ; $287D: voice 2 falls
        bne l8D
        bit PHASE
        bpl l8F
m4:     bit SPKR                ; $2885
        eor #$A0
        jmp l93
l8D:    nop                     ; $288D
l8E:    nop
l8F:    nop
        nop
        nop
l92:    nop
l93:    nop
        dec COUNT               ; $2894
        bne l9F
        dec DUR
        beq lA5
        jmp l40
l9F:    nop                     ; $289F
        nop
        nop
        jmp l40
lA5:    lda SONG                ; $28A5: the next record
        clc
        adc #3
        sta SONG
        bcc :+
        inc SONG+1
:       jmp l08
loop_end:
.assert >l40 = >loop_end, error, "Electric Duet loop crosses a page"

; ---------------------------------------------------------------------
; The Mockingboard: VIA 1 of the card at page $Cs, timer 1 free-running
; at one Electric Duet duration unit (256 iterations of 73 cycles).
.segment "CODE"
UNIT = 256*73
ay_via:
        lda #0
        sta ptr1
        lda card
        sta ptr1+1
        rts
; void __fastcall__ ay_start(unsigned char slot)
_ay_start:
        ora #$C0
        sta card
        jsr ay_via
        ldy #$0B                ; ACR: T1 free-running
        lda (ptr1),y
        sta old_acr
        ora #$40
        sta (ptr1),y
        ldy #$0E                ; IER: no interrupts
        lda #$7F
        sta (ptr1),y
        ldy #4
        lda #<UNIT
        sta (ptr1),y
        iny
        lda #>UNIT
        sta (ptr1),y
        rts
; unsigned char ay_tick(void): 1 once per unit
_ay_tick:
        jsr ay_via
        ldy #$0D                ; IFR bit 6
        lda (ptr1),y
        and #$40
        beq @done
        ldy #4                  ; reading T1 low clears it
        lda (ptr1),y
        lda #1
@done:  ldx #0
        rts
; void __fastcall__ ay_write(unsigned int regval): X = register, A = value
_ay_write:
        pha
        jsr ay_via
        txa
        ldy #1                  ; ORA = register
        sta (ptr1),y
        dey
        lda #7                  ; ORB: latch address
        sta (ptr1),y
        lda #4
        sta (ptr1),y
        pla
        iny
        sta (ptr1),y            ; ORA = value
        dey
        lda #6                  ; ORB: write data
        sta (ptr1),y
        lda #4
        sta (ptr1),y
        rts
; void ay_silence(void): both volumes to zero
_ay_silence:
        ldx #8
        lda #0
        jsr _ay_write
        ldx #9
        lda #0
        jmp _ay_write
; void ay_stop(void): silence, then the VIA as it was
_ay_stop:
        jsr _ay_silence
        jsr ay_via
        ldy #$0E
        lda #$7F
        sta (ptr1),y
        ldy #4
        lda (ptr1),y
        ldy #$0B
        lda old_acr
        sta (ptr1),y
        rts
