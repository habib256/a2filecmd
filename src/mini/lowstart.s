; lowstart.s -- BRUN enters at $1000; the resident start lives at $4000.
;
; The format module travels inside the working area of the BRUN image
; and runs from $0200-$03CF (see format.s). It is moved there first,
; before anything else runs: page two whole, then page three up to the
; DOS vectors at $03D0, which must stay DOS's.

        .include "mini.inc"

        .import start
        .import __FORMAT_LOAD__, __FORMAT_RUN__, __FORMAT_SIZE__

        .segment "LOWSTART"

        ldx     #0
@page2:
        lda     __FORMAT_LOAD__,x
        sta     __FORMAT_RUN__,x
        inx
        bne     @page2
@page3:
        lda     __FORMAT_LOAD__+$100,x
        sta     __FORMAT_RUN__+$100,x
        inx
        cpx     #<FORMAT_ROOM
        bne     @page3
        jmp     start

        .assert __FORMAT_RUN__ = FORMAT_HOME, error, "format.s must run from $0200"
        .assert __FORMAT_SIZE__ <= FORMAT_ROOM, error, "format.s reaches the DOS vectors"
