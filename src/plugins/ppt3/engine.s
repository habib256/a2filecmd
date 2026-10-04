; engine.s -- GROUiK / French Touch's PT3 player (ppt3.s, a faithful ca65
; port of ppt3.a) wrapped for A2 File Cmd. This image runs in the AUXILIARY
; bank: the driver (driver.s, in main memory) copies it to AUX $2000, the
; module to AUX $4000, and calls PPT3_ENTRY through a trampoline that
; exists at the same address in both banks, with RAMRD and RAMWRT on AUX,
; interrupts off and decimal mode clear. Zero page and the 6502 stack stay
; in main memory (ALTZP off): this wrapper saves the host's $60-$7F, puts
; the engine's own copy there, and restores the host's bytes on every exit,
; including a guard trip.
;
; What A2FC adds around the original player, and nothing else:
;   - g_rd_c / g_rd_l / g_rd_ix / g_adc_l: every read through a pointer
;     derived from the module is checked. The address must lie inside the
;     module [PPT3_MODULE, modhi) or inside the PPT3_EMPTY bytes of the
;     player's built-in empty sample/ornament (EMPTYSAMORN); anything else,
;     $C000-$CFFF included, is never read: playback aborts (result 1).
;     Each call may make at most 255 such reads (a runaway command stream);
;   - g_push_check: at most PPT3_PUSHMAX deferred special commands per
;     channel decode (the player pushes their addresses on the 6502 stack);
;     the do-nothing ones (C_NOP) are not pushed at all;
;   - INIT copies a ZX note table (notes.inc) instead of generating one
;     scaled for a 1 MHz AY; make_out converts every period the player
;     outputs to the Mockingboard's 1.0227 MHz clock (tones, noise,
;     envelope), into PPT3_OUT instead of the card. The main-memory host
;     writes the AY (pt3.s pt_output).
; Stores: the player only stores through (z80_IX),Y with IX = ChanA/B/C or
; the volume table, and through (z80_L),Y into its note table, AddToEn and
; AYREGS -- all inside this image or PPT3BSS (tools/test_ppt3_engine.py
; records every write of the real code on real and malformed modules).

        PPT3_A2FC = 1
        .macpack longbranch
        .include "abi.inc"

        .segment "PPT3HDR"
        .byte   "PPT3", PPT3_ABI
        jmp     pg_entry                ; PPT3_ENTRY
pg_out: .res    14                      ; PPT3_OUT
modhi:  .word   0                       ; PPT3_MODHI
        .word   image_end - PPT3_BASE   ; PPT3_LEN
.assert pg_out = PPT3_OUT, error, "PPT3_OUT moved"
.assert modhi = PPT3_MODHI, error, "PPT3_MODHI moved"

        .segment "CODE"
.assert * = PPT3_BASE + 26, error, "header size"
; The player first, so that its zero-page symbols are known (and used as
; zero page) by the wrapper below. It ends in PPT3BSS: back to CODE after.
        .include "ppt3.s"
        .segment "CODE"

; ---- the entry: A = 0 INIT (module at PPT3_MODULE, modhi set), 1 PLAY ----
pg_entry:
        tsx
        stx     saved_sp
        tay
        ldx     #31
@save:  lda     $60,x
        sta     host_zp,x
        lda     eng_zp,x
        sta     $60,x
        dex
        bpl     @save
        lda     #0
        sta     budget                  ; 255 guarded reads, then a trip
        sta     result
        tya
        bne     @play
        ; INIT: the bounds the host gives must describe a plausible module.
        lda     modhi
        cmp     #<(PPT3_MODULE+202)
        lda     modhi+1
        sbc     #>(PPT3_MODULE+202)
        jcc     g_trip                  ; shorter than a PT3 header
        lda     #<(PPT3_MODULE+PPT3_MODMAX)
        cmp     modhi
        lda     #>(PPT3_MODULE+PPT3_MODMAX)
        sbc     modhi+1
        jcc     g_trip                  ; past $BFFF
        lda     #0
        ldx     #31
@zero:  sta     $60,x
        dex
        bpl     @zero
        lda     #1
        sta     SETUP                   ; play once: stop at the end
        jsr     START
        jmp     @done
@play:  jsr     PLAY
@done:  bit     SETUP                   ; bit 7: the end of the order list
        bpl     @out
        lda     #2
        sta     result
@out:   jsr     make_out
leave:  ldx     #31
@rest:  lda     $60,x
        sta     eng_zp,x
        lda     host_zp,x
        sta     $60,x
        dex
        bpl     @rest
        lda     result
        rts

; ---- the registers for the Mockingboard ----
; The player now computes in ZX units throughout (ZX note tables, see
; ppt3.s INIT): every period it outputs is converted here, the way pt3_lib
; does (core.inc, conv_mb): x 1181/2048 = 1.0227/1.7734, rounded. Tones
; first keep the ZX AY's 12 bits, the noise its 5 bits; the envelope
; period is 16 bits. Grouik's ROUT halved the noise and multiplied the
; envelope by 289/512 (a 1 MHz AY), and wrote the old R13 when the player
; said >= $80; A2FC writes R13 only when the player sets a shape ($FF =
; skip, for pt3.c's writer).
make_out:
        ldx     #13
@copy:  lda     AYREGS,x
        sta     pg_out,x
        dex
        bpl     @copy
        ldx     #4                      ; tones C, B, A
@tone:  lda     pg_out+1,x
        and     #$0F
        sta     pg_out+1,x
        jsr     mb_scale
        dex
        dex
        bpl     @tone
        lda     pg_out+Noise
        and     #$1F
        sta     pg_out+Noise
        lda     #0
        sta     pg_out+Mixer            ; borrowed as the noise's high byte
        ldx     #Noise
        jsr     mb_scale
        lda     AYREGS+Mixer            ; put the mixer back
        sta     pg_out+Mixer
        ldx     #Env
        jsr     mb_scale
        lda     AYREGS+EnvTp
        bpl     @shape
        lda     #$FF
@shape: sta     pg_out+EnvTp
        rts

; pg_out+X (lo), +X+1 (hi) = (P x 1181 + 1024) >> 11, the very routine
; of pt3_lib's conv_mb (core.inc): 1181/2048 = 1.0227/1.7734 within 0.09
; cent. gptr is the 17-bit accumulator (free outside the read guards).
mb_scale:
        lda     #0
        sta     gptr
        sta     gptr+1
        jsr     mb_add                  ; bit 0 of 1181 = %10010011101
        lsr     gptr+1                  ; bit 1
        ror     gptr
        jsr     mb_add                  ; bit 2
        jsr     mb_add                  ; bit 3
        jsr     mb_add                  ; bit 4
        lsr     gptr+1                  ; bit 5
        ror     gptr
        lsr     gptr+1                  ; bit 6
        ror     gptr
        jsr     mb_add                  ; bit 7
        lsr     gptr+1                  ; bit 8
        ror     gptr
        lsr     gptr+1                  ; bit 9
        ror     gptr
        jsr     mb_add                  ; bit 10: C = bit 10 of the product
        lda     gptr
        adc     #0
        sta     pg_out,x
        lda     gptr+1
        adc     #0
        sta     pg_out+1,x
        rts
mb_add: clc
        lda     gptr
        adc     pg_out,x
        sta     gptr
        lda     gptr+1
        adc     pg_out+1,x
        ror                             ; the 17th bit comes in
        sta     gptr+1
        ror     gptr
        rts

g_trip: ldx     saved_sp                ; drop whatever the player stacked
        txs
        lda     #1
        sta     result
        jmp     leave

; ---- the read guards ----
; Out: A = the byte at (pointer),Y; N/Z from it; X, Y, C, V, I, D kept.
g_rd_ix:
        php
        stx     g_x
        ldx     #z80_IX
        bne     g_rd
g_rd_c: php
        stx     g_x
        ldx     #z80_C
        bne     g_rd
g_rd_l: php
        stx     g_x
        ldx     #z80_L
g_rd:   sty     g_y
        dec     budget
        beq     g_trip
        tya
        clc
        adc     $00,x
        sta     gptr
        lda     $01,x
        adc     #0
        bcs     g_trip                  ; past $FFFF
        sta     gptr+1
        cmp     #>PPT3_MODULE
        bcc     @low
        cmp     modhi+1
        bcc     @ok
        bne     g_trip
        lda     gptr
        cmp     modhi
        bcs     g_trip
        bcc     @ok
@low:   lda     gptr                    ; the built-in empty sample/ornament
        sec
        sbc     #<EMPTYSAMORN
        tax
        lda     gptr+1
        sbc     #>EMPTYSAMORN
        bne     g_trip                  ; below it (borrow) or far above
        cpx     #PPT3_EMPTY
        bcs     g_trip
@ok:    ldy     #0
        lda     (gptr),y
        sta     g_v
        ldy     g_y
        ldx     g_x
        plp
        lda     g_v
        rts

; ADC (z80_L),Y with the same checks; the carry in is the caller's.
g_adc_l:
        sta     g_a
        jsr     g_rd_l
        lda     g_a
        adc     g_v
        rts

; Called at so7, before the player pushes a deferred special command
; (A = $F0 + its number). The commands that do nothing (C_NOP: 0, 6, 7,
; 10-15 -- a channel reading on past its own $00 end marker meets many) are
; not pushed: the player's effect on z80_L/H is reproduced and it goes on
; at PD_LOOP, as after the push; C_NOP's RTS would have done nothing more.
; The others count: more than PPT3_PUSHMAX in one decode is a trip, so
; the 6502 stack cannot overflow into the host's.
g_push_check:
        tax
        and     #$0F
        tay
        lda     g_nop,y
        beq     @real
        txa                             ; the player's z80_L/H for this entry
        asl
        sta     z80_E
        tya
        asl
        clc
        adc     #<SPCCOMS
        sta     z80_L
        lda     #>SPCCOMS
        adc     #0
        sta     z80_H
        pla                             ; drop so7's JSR
        pla
        jmp     PD_LOOP
@real:  txa
        inc     g_push
        ldx     g_push
        cpx     #PPT3_PUSHMAX+1
        bcc     @ok
        jmp     g_trip
@ok:    rts
g_nop:  .byte   1, 0, 0, 0, 0, 0, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1

        .include "notes.inc"

        .segment "PPT3END"
image_end:

        .segment "PPT3BSS"
saved_sp:       .res 1
budget:         .res 1
result:         .res 1
g_x:            .res 1
g_y:            .res 1
g_v:            .res 1
g_a:            .res 1
g_push:         .res 1
host_zp:        .res 32
eng_zp:         .res 32
