; The launcher's machine check (crt0_loader.s), in plain 6502 so that it
; runs on any Apple II. tools/test_machine_check.py runs this same text
; under sim65, as a NMOS 6502 and as a 65C02.
;
; IIe or later ($FBB3 = $06), 128 KB and an 80-column card (MACHID $BF98,
; bits 5 and 1). The 65C02 edition also needs the enhanced firmware
; ($FBC0 <> $EA: MouseText) AND a 65C02 processor: the two are independent,
; since some enhanced IIe run with a 6502 put back in, and an accelerator
; can bring a 65C02 to an unenhanced IIe. The processor test is the
; classic decimal-mode one, documented opcodes only: in decimal mode
; $99 + $01 gives $00 on both, but a NMOS 6502 takes the N flag from the
; unadjusted sum (set), a 65C02 from the result (clear). Interrupts stay
; masked while D is set, and the caller's flags come back after.
;
; Branches to `unfit` (wrong machine) or, 65C02 edition only, to `nmos`
; (the right machine with a 6502 in it); falls through when the machine
; fits. The includer defines the three labels.
        lda     $FBB3
        cmp     #$06
        bne     unfit
.ifndef A2_6502
        lda     $FBC0
        cmp     #$EA
        beq     unfit
        php
        sei
        sed
        lda     #$99
        clc
        adc     #$01
        cld
        php
        pla                     ; bit 7: the N flag of the decimal sum
        plp                     ; interrupts as the caller had them
        asl     a
        bcs     nmos
.endif
        lda     $BF98
        and     #$22
        cmp     #$22
        bne     unfit
