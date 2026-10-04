; hook.s -- the main-memory half of the calls into GROUiK's engine (AUX),
; included by pt3.s and linked at $3B00 with driver.s (segments PG*,
; sdk/pt3.cfg). Self-contained for tools/test_ppt3_driver.py: it needs
; _pt_regs and the C globals driver.s imports.
.include "abi.inc"
.export _pg_call, _pg_setup, _pg_end
.importzp ptr1, ptr2, tmp1, tmp2
.ifndef _pt_regs
.import _pt_regs                 ; pt3.s defines it before including this
.endif
.segment "PGCODE"
; unsigned char __fastcall__ pg_call(unsigned char fn): fn 0 INIT, 1 PLAY.
; Returns 0, 1 (guard trip) or 2 (end); PPT3_OUT lands in _pt_regs.
; From the store to RDAUX to the store to RDMAIN the 6502 fetches these
; bytes from AUX: driver.s copies pg_tramp..pg_tramp_end there first, at
; the same address. LORES first: with 80STORE on, HIRES would route
; $2000-$3FFF by PAGE2 instead of RAMRD/RAMWRT. Interrupts stay off from
; the first AUX access to the last; zero page and stack are main memory.
pg_tramp:
_pg_call:
 php
 sei
 cld
 sta $C056                       ; LORES
 sta $C003                       ; RAMRD AUX: the next byte comes from AUX
 sta $C005                       ; RAMWRT AUX
 jsr PPT3_ENTRY
 sta $C004                       ; RAMWRT main: the registers go to main
 tax
 ldy #13
@out:
 lda PPT3_OUT,y                  ; read in AUX
 sta _pt_regs,y                  ; written in main
 dey
 bpl @out
 sta $C002                       ; RAMRD main: back to the main copy
 plp
 txa
 ldx #0
 rts
pg_tramp_end:
.ifndef PPT3_SIM_LAYOUT                  ; sim65 (one flat bank) links it elsewhere
.assert pg_tramp >= PPT3_LIMIT && pg_tramp_end <= PPT3_MODULE, lderror, "pg_call's AUX mirror must sit between the engine and the module"
.endif

; tmp1/tmp2 bytes from ptr1 (main) to ptr2 (AUX), with RAMWRT only: this
; code and its reads stay in main memory. Interrupts off meanwhile.
pg_put:
 php
 sei
 sta $C056                       ; LORES (see pg_call)
 sta $C005                       ; RAMWRT AUX
 ldy #0
@loop:
 lda tmp1
 ora tmp2
 beq @done
 lda (ptr1),y
 sta (ptr2),y
 iny
 bne :+
 inc ptr1+1
 inc ptr2+1
: lda tmp1
 bne :+
 dec tmp2
: dec tmp1
 jmp @loop
@done:
 sta $C004                       ; RAMWRT main
 plp
 rts

.include "driver.s"
