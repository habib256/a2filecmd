; music.s -- the Mockingboard plays the disk's music, on six voices.
;
; An MB1 stream reader (DOCS/MUSIQUE.md section 5.2) under interrupt: Timer 1
; of the card's first 6522 ticks at 50 Hz, and each tick decodes the packets
; of the stream up to the next DELAY. Everything is in assembly and in the
; CODE segment: never in the LC, ProDOS switches the other bank in under IRQ.
;
; Six voices: Mockingboards A and C carry two AY-3-8910s, one behind VIA #1
; at $Cn00, the other behind VIA #2 at $Cn80. Stream voices 0-2 go to the
; first chip (on the left in POM2), voices 3-5 to the second (on the
; right): voice v >= 3 is written to chip 2 under the number v-3.
;
; Three rules learned from reading POM2 (DOCS/MUSIQUE.md section 1):
;  - acknowledge the IRQ by WRITING $7F to the IFR ($Cn0D), never by reading
;    a register: the //e Monitor's IRQ entry routes $C100-$CFFF to the ROM;
;  - scan the slots from $C7 down to $C1 skipping 3: POM2 puts the card in
;    slot 2 by default, and a silent //e has its 80-column firmware in slot 3;
;  - without a card, no write goes out: mb_slot = 0 and every entry point
;    tests it first. The game stays identical, sfx.s carries on alone.
;
; cc65 does the ProDOS plumbing: `.interruptor` enters the table that
; a2fc.cfg declares, the runtime does ALLOC_INTERRUPT at startup and
; DEALLOC at exit, and calls music_irq with the carry clear; we set it
; if the IRQ is ours. ProDOS saves A, X, Y and $FA-$FF around the
; handler: those six zero-page bytes are therefore ours, here and outside
; the IRQ (cc65 only occupies $80-$99).
;
; C API (music.h):
;   unsigned char music_detect(void);   slot found (1-7) or 0; initialises
;   void music_play(void);              plays the stream once only
;   void music_stop(void);              clean silence, timer disarmed

.ifdef A2_6502
; The non-enhanced IIe has neither STZ nor BRA: the same names, in 6502. STZ
; keeps A, X and Y like the original; only N and Z change (those of A), and
; no use below reads them afterwards.
.macro  stz     addr, idx
        pha
        lda     #0
.ifblank idx
        sta     addr
.else
        sta     addr,idx
.endif
        pla
.endmacro
.macro  bra     target
        jmp     target
.endmacro
.else
        .setcpu "65C02"
.endif
        .export _music_detect, _music_play, _music_stop, _music_buf
        .export _music_store, _music_set_loop, aux_read_cur, aux_mirror_end
        .import popax
        .export _music_select, _music_pause, _music_resume, _music_continue
        .export _music_fade_out, _music_fade_in, _music_fading
        .interruptor music_irq
        .destructor  music_done, 11     ; exit() cuts the timer before DEALLOC:
                                        ; donelib walks the table backwards,
                                        ; irq_done (priority 10) must come after

via     = $FA           ; pointer to $Cn00 (VIA #1) or $Cn80 (VIA #2)
cur     = $FC           ; stream cursor (working copy under IRQ)
tmp     = $FE
tmp2    = $FF

; 6522 registers, offsets from $Cn00
VIA_ORB = $00
VIA_ORA = $01
DDRB    = $02
DDRA    = $03
T1CL    = $04
T1CH    = $05
ACR     = $0B
IFR     = $0D
IER     = $0E

; 50 Hz: 1,022,727 / 50 = 20,454.5 cycles; effective period = latch + 2
T1_50HZ = 20452
FADE_STEP = 3           ; ticks between two fade steps

.segment "BSS"
; Two AUX buffers: 2304 bytes (half 0, the zone themes) and 1280 bytes
; (half 1, the overlays: combat, death, victory), read from
; a .MB file by the host program. MUSIC_ZONE and MUSIC_OVER in
; music.h state the same sizes. Each half keeps its cursor: coming back
; to the zone after a combat resumes it where it was, without rereading.
; Only the staging page below is reserved in MAIN -- or in low RAM
; (LOWBSS) for A2FC, assembled with -D LOWBUF: its main BSS
; is full, the game keeps its own as it is.
.ifdef LOWBUF
.segment "LOWBSS"
.endif
_music_buf:     .res 256         ; disk staging, resident streams in AUX
.ifdef LOWBUF
.segment "BSS"
.endif
AUX_MUSIC = $1000
mb_slot:        .res 1
playing:        .res 1
_music_active   = playing       ; read by A2FC: 0 when the stream is finished
        .export _music_active
paused:         .res 1
half:           .res 1          ; the selected half, 0 or 1
delay:          .res 1
cur_lo:         .res 1
cur_hi:         .res 1
saved:          .res 6          ; cur_lo, cur_hi, delay of each half
vols:           .res 6
; The fade: `atten` (0-15) is subtracted from every amplitude written; `fade`
; is 1 for a fade-out (atten rises), 2 for a fade-in (atten falls),
; 0 otherwise; one step every FADE_STEP ticks, i.e. 45 ticks = 0.9 s
; from one end to the other. `amps` keeps the last raw amplitude of each
; voice so it can be rewritten attenuated.
atten:          .res 1
fade:           .res 1
fstep:          .res 1
amps:           .res 6
mix:            .res 2          ; R7 of each chip: tones and noise per voice

.segment "RODATA"
        .include "ay_notes.inc"
; R7 mixer bits for voice 0-2 of a chip: tone (bit v) and noise (bit 3+v),
; active at ZERO; the masks turn them off.
tbit:   .byte $01, $02, $04
nbit:   .byte $08, $10, $20
tmask:  .byte $FE, $FD, $FB
nmask:  .byte $F7, $EF, $DF

.segment "CODE"

.macro  NEXT                    ; cur++
        inc cur
        bne :+
        inc cur+1
:
.endmacro

; via := $Cn00 from mb_slot (VIA #1)
set_via:
        stz via
        lda mb_slot
        ora #$C0
        sta via+1
        rts

; via := the chip of voice A (0-5); returns in A the voice number within
; the chip (0-2).
chip_of:
        cmp #3
        bcc :+
        sbc #3                  ; carry already set
        ldy #$80
        sty via
        rts
:       stz via
        rts

; Writes A to register X of AY #1. Preserves X, destroys Y.
; BDIR/BC1 sequence on port B: LATCH ($07), INACTIVE ($04), WRITE ($06),
; INACTIVE. PB2 (/RESET) stays high.
ay_write:
        pha
        txa
        ldy #VIA_ORA
        sta (via),y
        ldy #VIA_ORB
        lda #$07
        sta (via),y
        lda #$04
        sta (via),y
        pla
        ldy #VIA_ORA
        sta (via),y
        ldy #VIA_ORB
        lda #$06
        sta (via),y
        lda #$04
        sta (via),y
        rts

; Mixer closed, three volumes at zero -- on the chip that `via` designates.
silence1:
        ldx #7
        lda #$3F
        jsr ay_write
        ldx #8
        lda #0
        jsr ay_write
        inx
        jsr ay_write
        inx
        jmp ay_write

; Both chips.
silence:
        stz via
        jsr silence1
        lda #$80
        sta via
        jsr silence1
        stz via
        rts

; Ports as outputs and /RESET low then high -- on the chip that `via` designates.
init1:
        lda #$FF
        ldy #DDRA
        sta (via),y
        ldy #DDRB
        sta (via),y
        ldy #VIA_ORB
        lda #$00
        sta (via),y
        lda #$04
        sta (via),y
        rts

; R7 := A on both chips. $38 opens tones A, B, C (noise closed),
; $3F closes everything without touching the amplitudes: that is the pause.
mixer_set:
        sta tmp2
        stz via
        jsr mix1
        lda #$80
        sta via
        jsr mix1
        stz via
        rts
mix1:   ldx #7
        lda tmp2
        jmp ay_write

; R7 := mix[] on both chips: the reopening after a pause, and the
; start of a stream (tones open, noise closed).
mixer_restore:
        stz via
        ldx #7
        lda mix
        jsr ay_write
        lda #$80
        sta via                 ; X is still 7: ay_write leaves it intact
        lda mix+1
        jsr ay_write
        stz via
        rts

; The mixer of voice `tmp` (0-5): entry C=1 -> noise open, tone off
; (percussion); C=0 -> tone open, noise off (note). Sets via to its chip.
mix_voice:
        php
        ldx #0                  ; X = chip 0/1
        lda tmp
        cmp #3
        bcc :+
        inx
:       jsr chip_of             ; A = tmp, intact after cmp
        tay                     ; Y = voice 0-2 within the chip
        lda mix,x
        plp
        bcs @noise
        and tmask,y
        ora nbit,y
        bra @w
@noise: ora tbit,y
        and nmask,y
@w:     sta mix,x
        ldx #7
        jmp ay_write

; tmp/tmp2 := address of the selected half-buffer.
set_base:
        lda #<AUX_MUSIC
        sta tmp
        lda #>AUX_MUSIC
        sta tmp2
        lda half
        beq :+
        lda #<2304
        clc
        adc tmp
        sta tmp
        lda #>2304
        adc tmp2
        sta tmp2
:       rts

; Z=1 if the T1 counter went down by 8 between two reads 8 cycles
; apart: 4am's probe, taken up by Total Replay and by POM2's tests.
t1_probe:
        ldy #T1CL
        lda (via),y
        sta tmp
        lda (via),y
        sec
        sbc tmp
        cmp #$F8
        rts

; -- unsigned char music_detect(void) ------------------------------------
_music_detect:
        jsr init_aux_reader
        ldx #7
@slot:  cpx #3
        beq @next
        stx mb_slot
        jsr set_via
        jsr t1_probe
        bne @next
        jsr t1_probe
        bne @next
        ; found: both VIAs as outputs, both AYs reset
        jsr init1
        lda #$80
        sta via
        jsr init1
        stz via
        txa
        ldx #0
        rts
@next:  dex
        bne @slot
        stz mb_slot
        txa                     ; 0
        rts

; -- void music_play(void) -----------------------------------------------
_music_play:
        lda mb_slot
        beq @rts
        jsr set_via
        jsr silence
        lda #$38                ; tones open, noise closed, on both chips
        sta mix
        sta mix+1
        jsr mixer_restore
        jsr set_base            ; the stream starts after the 8-byte header
        lda tmp
        clc
        adc #8
        sta cur_lo
        lda tmp2
        adc #0
        sta cur_hi
        lda #1
        sta delay
        sta playing
        stz paused
        lda #12
        ldx #5
:       sta vols,x
        stz amps,x
        dex
        bpl :-
        jsr fade_in_setup
        ldy #ACR                ; T1 free-running
        lda #$40
        sta (via),y
        ldy #T1CL
        lda #<T1_50HZ
        sta (via),y
        ldy #T1CH
        lda #>T1_50HZ
        sta (via),y             ; loads and starts
        ldy #IFR
        lda #$7F
        sta (via),y
        ldy #IER                ; enable T1
        lda #$C0
        sta (via),y
@rts:   rts

; -- void music_stop(void) -----------------------------------------------
_music_stop:
music_done:
        lda mb_slot
        beq @rts
        stz playing
        stz paused
        stz fade
        stz atten
        jsr set_via
        ldy #IER                ; disable T1
        lda #$40
        sta (via),y
        ldy #IFR
        lda #$7F
        sta (via),y
        jmp silence
@rts:   rts

; -- void __fastcall__ music_select(unsigned char half) ------------------
; Switches half-buffer while keeping the cursor of each. To be called while
; stopped or paused: the tick must not run during the swap.
_music_select:
        cmp half
        beq @rts
        pha
        lda half                ; x = 3 * current half
        asl a
        adc half
        tax
        lda cur_lo
        sta saved,x
        lda cur_hi
        sta saved+1,x
        lda delay
        sta saved+2,x
        pla
        sta half
        asl a
        adc half
        tax
        lda saved,x
        sta cur_lo
        lda saved+1,x
        sta cur_hi
        lda saved+2,x
        sta delay
@rts:   rts

; -- void music_pause(void) ----------------------------------------------
; Mixer closed, timer disarmed, cursor and amplitudes intact: for disk
; reads, during which ProDOS masks IRQs.
_music_pause:
        lda mb_slot
        beq @rts
        lda playing
        beq @rts
        lda #1
        sta paused
        jsr set_via
        ldy #IER
        lda #$40
        sta (via),y
        ldy #IFR
        lda #$7F
        sta (via),y
        lda #$3F
        jmp mixer_set
@rts:   rts

; -- void music_resume(void) ---------------------------------------------
; After music_pause only: reopens the mixer and rearms the timer.
_music_resume:
        lda paused
        beq @rts
        stz paused
        bra rearm
@rts:   rts

; -- void music_continue(void) -------------------------------------------
; Resumes the selected half-buffer where its cursor stands -- after a
; music_stop and a music_select. The caller guarantees that this half has
; already been started by music_play.
_music_continue:
        lda mb_slot
        beq rearm_rts
        lda #1
        sta playing
        stz paused
        jsr fade_in_setup
rearm:  jsr set_via
        jsr mixer_restore
        ldy #IFR
        lda #$7F
        sta (via),y
        ldy #IER
        lda #$C0
        sta (via),y
rearm_rts:
        rts

; -- The fade ------------------------------------------------------------
fade_in_setup:
        lda #15
        sta atten
        lda #2
        sta fade
        lda #1
        sta fstep
        rts

; void music_fade_out(void): the current music fades away in 0.9 s; the
; tick keeps advancing it, we only turn the sound down.
_music_fade_out:
        lda playing
        beq @rts
        lda #1
        sta fade
        sta fstep
@rts:   rts

; void music_fade_in(void): from the current attenuation, goes back up.
_music_fade_in:
        lda playing
        beq @rts
        lda #2
        sta fade
        lda #1
        sta fstep
@rts:   rts

; unsigned char music_fading(void): 0 when the current fade is finished.
_music_fading:
        lda fade
        ldx #0
        rts

; Rewrites the six amplitudes, attenuated. Destroys A, X, Y, tmp.
apply_amps:
        ldy #0
@l:     sty tmp
        lda amps,y
        sec
        sbc atten
        bcs :+
        lda #0
:       pha
        tya
        jsr chip_of
        clc
        adc #8
        tax
        pla
        jsr ay_write
        ldy tmp
        iny
        cpy #6
        bne @l
        stz via
        rts

; One fade step every FADE_STEP ticks; on arrival, fade goes back to zero.
fade_tick:
        lda fade
        beq @rts
        dec fstep
        bne @rts
        lda #FADE_STEP
        sta fstep
        lda fade
        cmp #1
        bne @in
        lda atten
        cmp #15
        bcs @done
        inc atten
        jmp apply_amps
@in:    lda atten
        beq @done
        dec atten
        jmp apply_amps
@done:  stz fade
@rts:   rts

; -- The tick ------------------------------------------------------------
; Entry: carry clear. Exit: carry set if the IRQ was ours.
music_irq:
        lda playing
        beq @notours
        jsr set_via
        ldy #IFR
        lda #$7F
        sta (via),y             ; acknowledge, by writing only
        jsr fade_tick
        dec delay
        bne @done
        lda cur_lo
        sta cur
        lda cur_hi
        sta cur+1
@next:  jsr aux_read_cur
        NEXT
        cmp #$80
        bcs @cmd
        sta delay               ; DELAY n
        lda cur
        sta cur_lo
        lda cur+1
        sta cur_hi
@done:  sec
        rts
@notours:
        clc
        rts

@cmd:   tax
        and #$0F
        sta tmp                 ; the voice
        txa
        and #$F0
        cmp #$80
        beq @note
        cmp #$90
        beq @off
        cmp #$A0
        beq @vol
        cmp #$E0
        beq @end
        cmp #$F0
        bne :+
        jmp @fade
:       cmp #$B0
        bne :+
        jmp @noise
:       jmp @next               ; unknown packet: ignored

@note:  jsr aux_read_cur               ; note index 0-59
        NEXT
        asl a
        sta tmp2
        lda tmp
        jsr chip_of             ; via -> the chip, A = voice 0-2 within the chip
        asl a
        tax                     ; R0/R2/R4: period, low byte
        ldy tmp2
        lda note_table,y
        jsr ay_write
        inx                     ; R1/R3/R5: high byte
        ldy tmp2
        lda note_table+1,y
        jsr ay_write
        clc
        jsr mix_voice           ; tone open, noise off (the voice may have been drumming)
        ldy tmp
        lda vols,y
        jmp @amp

@vol:   jsr aux_read_cur
        NEXT
        ldy tmp
        sta vols,y
        jmp @amp

@off:   lda #0
@amp:   ldy tmp                 ; A = raw amplitude, tmp = voice 0-5
        sta amps,y
        sec
        sbc atten               ; attenuated by the fade in progress
        bcs :+
        lda #0
:       pha
        lda tmp
        jsr chip_of
        clc
        adc #8
        tax
        pla
        jsr ay_write
        stz via                 ; back on VIA #1 (IFR, T1)
        jmp @next

@end:   jsr set_base            ; only COMBAT still carries the loop flag
        ldy #5
        jsr aux_read_header
        and #1
        beq @stop
        ldy #6
        jsr aux_read_header
        clc
        adc tmp
        sta cur
        ldy #7
        jsr aux_read_header
        adc tmp2
        sta cur+1
        jsr fade_in_setup
        jmp @next
@stop:  jsr _music_stop
        sec
        rts

@fade:  lda #1                  ; FADE: the end of the piece fades away in 0.9 s
        sta fade
        sta fstep
        jmp @next

@noise: jsr aux_read_cur               ; NOISE: noise period (the chip's R6)
        NEXT
        pha
        sec
        jsr mix_voice           ; tone off, noise open; via -> the chip
        ldx #6
        pla
        jsr ay_write
        ldy tmp
        lda vols,y
        jmp @amp

; MAIN and AUX contain the same instructions across RAMRD transitions.
; AUX $1000-$1DFF holds both streams; the mirror lives at its linked CODE
; address, above $4000, separate from DHGR page 1 and stream storage.
; All entries require MAIN RAMRD/RAMWRT and MAIN ZP, as the existing driver.
; Copying uses SEI so its temporary RAMWRT AUX cannot redirect IRQ globals.
init_aux_reader:
        php
        sei
        ldx #aux_mirror_end-aux_read_cur-1
@copy:  lda aux_read_cur,x
        sta $C005
        sta aux_read_cur,x
        sta $C004
        dex
        bpl @copy
        plp
        rts
aux_read_cur:
        sta $C003
.ifdef A2_6502
        ldy #0                  ; no (zp) without Y on 6502; Y is free here
        lda (cur),y
.else
        lda (cur)
.endif
        sta $C002
        rts
aux_read_header:
        sta $C003
        lda (tmp),y
        sta $C002
        rts
aux_mirror_end:
        .assert aux_read_cur >= $4000, lderror, "AUX mirror overlaps low RAM"

; music_store(offset, count): count is 1..256, offset within both streams.
; The C caller has validated bounds and placed count bytes in _music_buf.
_music_store:
        php
        sei
        sta tmp                 ; low byte 0 denotes 256
        jsr popax               ; offset, A low / X high
        sta cur
        txa
        clc
        adc #>AUX_MUSIC
        sta cur+1
        ldy #0
@copy:  lda _music_buf,y
        sta $C005
        sta (cur),y
        sta $C004
        iny
        cpy tmp
        bne @copy
        plp
        rts

; Set the selected stream's loop byte, with the reader paused.
_music_set_loop:
        php
        sei
        pha
        jsr set_base
        pla
        ldy #5
        sta $C005
        sta (tmp),y
        sta $C004
        plp
        rts
