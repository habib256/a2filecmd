; lowstart.s -- BRUN enters at $1000; the resident start lives at $4000.

        .import start

        .segment "LOWSTART"

        jmp     start
