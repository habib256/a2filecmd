; scratch.s -- pins the 8 KB working area to hi-res page one.
;
; On the Apple II+ the area has to be at $2000: it is the only 8 KB block
; free between the Applesoft launcher and DOS, and a picture has to be
; there anyway for the hardware to show it. See mini.inc for the rule
; that exactly one owner uses it at a time.
;
; It is a symbol rather than an address in the code so that the sim65
; harness can hand out eight real kilobytes of its own instead: there,
; $2000 is somewhere in the middle of the test program.

        .include "mini.inc"

        .export scratch

scratch = SCRATCH
