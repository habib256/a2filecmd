; vsdrive.s -- VDrive: two ProDOS volumes served over the serial line.
;
;   unsigned char vsdrive_install(void);     returns (serial slot << 4) | slot of
;                                            the volumes, or 0 without a serial card
;   void vsdrive_uninstall(void);            cc65 destructor: Q, X, F, exit
;
; The protocol is that of ADTPro's VSDrive, also served by veserver.py
; (ProDOS-Utils) and surl-server (a2tools, Raspberry): for each block, a
; five-byte envelope -- $C5, the command (read 3 or 5, write 2 or 4
; depending on the drive), the block (low, high), the XOR of the four -- then
; the 512 bytes and their XOR. On a read the host first echoes the envelope
; back, followed by four bytes of ProDOS time and date, then their XOR; we
; take the opportunity to set the clock ($BF90). A wrong XOR signals the error.
;
; As in Ammonoid (Colin Leroy-Mira, a2tools/src/lib/vsdrive.s, which this
; driver draws on): the driver lives INSIDE the program, not inside ProDOS. At
; install time we look for a serial card (the Pascal 1.1 signature of its
; ROM: $Cn05=$38 $Cn07=$18 $Cn0B=$01 $Cn0C=$31, then a 6551 that answers), we
; set it to 115 200 baud 8N1, and we take the first slot 1..7 of which neither
; drive 1 nor drive 2 appears in DEVLST: its DEVADR entry receives our
; driver, its two units enter DEVLST, and the volume list shows them like
; any other disk. The destructor undoes everything: ProDOS must no longer
; point at us once the program is gone.
;
; Space: the main window is full, so the driver and its serial layer live
; in the language card (segment LC, bank 2, $D400-$DFFF). ProDOS, though,
; calls its drivers from ITS bank 1: a 17-byte thunk in page 3 ($0300, free
; under ProDOS; chain.s only puts its own thunk there after the destructor)
; switches bank 2 in for reading, calls the driver, and restores bank 1 for
; read/write before returning to the MLI. The language card is read-only
; (crt0: bit $C080): the variables are in page 3 as well.
;
; Timing: at 115 200 baud a byte arrives about every 87 cycles; the receive
; loop takes ~60, with interrupts disabled (SEI) for the duration of a
; block, otherwise the Mockingboard music would lose bytes. Each wait for a
; byte has a timeout (~0.3 s): an absent host yields an I/O error ($27)
; instead of freezing the machine -- the volume list reports it.

        .export         _vsdrive_install, _vsdrive_uninstall
        .destructor     _vsdrive_uninstall, 9
        .importzp       ptr1

; ProDOS
DEVADR          = $BF10         ; 16 words: slot 0..7, drive 1 then 2
DEVCNT          = $BF31         ; units minus one
DEVLST          = $BF32
DATE            = $BF90
TIME            = $BF92
P_CMD           = $42           ; 0 STATUS, 1 READ, 2 WRITE, 3 FORMAT
P_UNIT          = $43           ; slot x 16, + $80 for drive 2
P_BUF           = $44
P_BLK           = $46
E_IO            = $27
E_NODEV         = $28

; The 6551: $C088 + slot x 16 (data, status, command, control). The base
; $BFF9 = $C088 - $8F makes the spurious read of the indexing fall in page
; $BF, never in the I/O space (the trick of cc65 and a2tools).
ACIA_OFS        = $8F
ACIA_DATA       = $C088 - ACIA_OFS
ACIA_STATUS     = $C089 - ACIA_OFS
ACIA_CMD        = $C08A - ACIA_OFS
ACIA_CTRL       = $C08B - ACIA_OFS

; The protocol
VD_ENV          = $C5
VD_WRITE        = $02
VD_READ         = $03

; Page 3: the thunk at $0300, the variables behind it.
THUNK           = $0300
vs_slot         = $03B0         ; the slot of the volumes
vs_dev1         = $03B1         ; its drive 1 unit (slot x 16)
vs_dev2         = $03B2         ; drive 2 (+ $80)
vs_orig         = $03B3         ; the former DEVADR of this slot (2 bytes)
vs_on           = $03B5         ; 1: installed
vs_acia         = $03B6         ; the X index of the 6551 (slot x 16 + $8F)
vs_chk          = $03B7
vs_cmd          = $03B8
vs_to           = $03B9         ; the timeout countdown (2 bytes)
vs_dt           = $03BB         ; time and date received (4 bytes)
vs_pg           = $03BF         ; the pages of the block still to go
vs_int          = $03C0         ; the ProDOS number of our interrupt handler, 0 without
vs_ip           = $03C1         ; its MLI parameters (3 bytes): count, number, address

; ----------------------------------------------------------------------
; The destructor: in the main window, because _exit (crt0) restores the ROM
; before calling donelib -- the language card is no longer readable then.
; ----------------------------------------------------------------------
        .segment "CODE"

_vsdrive_uninstall:
        lda     vs_on
        beq     un_done
        lda     #0
        sta     vs_on
        jsr     del_irq
        lda     vs_slot                 ; the former driver takes DEVADR back
        asl
        tax
        lda     vs_orig
        sta     DEVADR,x
        sta     DEVADR+16,x
        lda     vs_orig+1
        sta     DEVADR+1,x
        sta     DEVADR+17,x
        ldx     #0                      ; our two units leave DEVLST,
        ldy     #0                      ; wherever they are (a rebuilt /RAM
un_scan:                                ; may have added some after us)
        lda     DEVLST,y
        cmp     vs_dev1
        beq     un_skip
        cmp     vs_dev2
        beq     un_skip
        sta     DEVLST,x
        inx
un_skip:
        iny
        cpy     DEVCNT
        bcc     un_scan
        beq     un_scan
        dex
        stx     DEVCNT
        ldx     vs_acia                 ; DTR drops: the port closes
        lda     #$0A
        sta     ACIA_CMD,x
un_done:
        rts

; ----------------------------------------------------------------------
; The rest in the language card.
; ----------------------------------------------------------------------
        .segment "LC"

; The Pascal 1.1 signature of a type 1 serial or parallel card.
id_ofs: .byte   $05, $07, $0B, $0C
id_val: .byte   $38, $18, $01, $31
; The slots in the order we probe them: 2 first -- the modem port of a
; //c, whose port 1 (printer) carries the same signature and the same
; 6551; the usual place of a modem on a IIe --, then 1, 3 to 7.
; (Michel Sitruk, //c, 0.6.7: the VDrive went out on the printer port.)
slots:  .byte   $C2, $C1, $C3, $C4, $C5, $C6, $C7, 0

; The thunk, copied to $0300. Its source is in main memory (segment CODE),
; not in the language card: the LC image is full to within 7 bytes, and a
; source that is only ever copied has no business there.
;
; The driver lives in bank 2 of the language card ($D400-$DFFF, the LC
; image of cc65) and ProDOS in bank 1 -- with its general buffer GBUF at
; $DC00: that is where ON_LINE, reading a directory and writing a
; directory block put P_BUF. A `sta (P_BUF),y` executed from bank 2
; cannot reach it (the two banks share the same addresses, and bank 2 was
; even read-only): the buffer kept the last block read by the Disk II
; driver, and the remote volume showed up under the floppy's name. Both
; buffer accesses therefore go through here, in page 3, outside the
; language card: bank 1 read/write for the duration of one byte, then back
; to bank 2 to find the driver again.
; (POM2 bench, bench/vdrive.py, 2026-09-08.)
        .segment "CODE"
thunk_src:
        bit     $C080                   ; bank 2 readable: us
        jsr     vs_driver
        php                             ; A and the carry: the verdict
        pha
        bit     $C08B                   ; bank 1 read/write: ProDOS, the
        bit     $C08B                   ; way it expects to find itself
        pla                             ; again
        plp
        rts
st_src:                                 ; A -> (P_BUF),y in ProDOS's bank
        bit     $C08B
        bit     $C08B
        sta     (P_BUF),y
        bit     $C080
        rts
ld_src:                                 ; A <- (P_BUF),y in ProDOS's bank
        bit     $C08B
        bit     $C08B
        lda     (P_BUF),y
        bit     $C080
        rts
; The ProDOS interrupt handler. A 6551 raises IRQ when DCD or DSR changes,
; whatever its registers say: on a real SSC whose cable carries those
; lines, unplugging the host would kill ProDOS ("RESTART SYSTEM -
; $01", nobody claimed the interrupt). Reading the status register
; acknowledges it; bit 7 says whether it was us. The address is filled in
; at install time (page 3: writable).
irq_src:
        lda     $C089                   ; -> $C089 + slot x 16
        and     #$80
        beq     irq_no
        clc                             ; claimed
        rts
irq_no: sec
        rts
thunk_len = * - thunk_src
irq_adr = THUNK + (irq_src - thunk_src) + 1
IRQH    = THUNK + (irq_src - thunk_src)

; Registering and removing the handler (MLI $40 / $41), in the main
; window: the removal serves the destructor, outside the language card.
ins_irq:
        lda     vs_acia                 ; the address of the status register:
        sec                             ; $C089 + slot x 16 = vs_acia - $8F + $89
        sbc     #ACIA_OFS-$89
        sta     irq_adr
        lda     #$C0
        sta     irq_adr+1
        lda     #2
        sta     vs_ip
        lda     #<IRQH
        sta     vs_ip+2
        lda     #>IRQH
        sta     vs_ip+3
        jsr     $BF00
        .byte   $40                     ; ALLOC_INTERRUPT
        .word   vs_ip
        bcc     :+
        lda     #0                      ; no room left in ProDOS: no handler
        sta     vs_ip+1
:       lda     vs_ip+1
        sta     vs_int
        rts
del_irq:
        lda     vs_int
        beq     :+
        sta     vs_ip+1
        lda     #1
        sta     vs_ip
        jsr     $BF00
        .byte   $41                     ; DEALLOC_INTERRUPT
        .word   vs_ip
        lda     #0
        sta     vs_int
:       rts
st_buf  = THUNK + (st_src - thunk_src)
ld_buf  = THUNK + (ld_src - thunk_src)
        .segment "LC"

; unsigned char vsdrive_install(void)
_vsdrive_install:
        lda     #0                      ; page 3 is not initialised: without
        sta     vs_on                   ; a card, the destructor must not
        sta     ptr1                    ; undo anything
        sta     vs_to                   ; the index into slots
ins_card:
        ldx     vs_to
        lda     slots,x
        beq     ins_none                ; end of the table: no card
        sta     ptr1+1                  ; $Cn: the ROM page of the slot
        inc     vs_to
        ldx     #0
ins_id: ldy     id_ofs,x
        lda     (ptr1),y
        cmp     id_val,x
        bne     ins_next
        inx
        cpx     #4
        bcc     ins_id
        lda     ptr1+1                  ; signature seen: slot x 16 + $8F
        asl
        asl
        asl
        asl
        clc
        adc     #ACIA_OFS
        tax
        ; Does a 6551 answer there? Two values written to its command
        ; register must read back (a2tools); otherwise we put everything back.
        lda     ACIA_STATUS,x
        pha
        lda     ACIA_CMD,x
        pha
        ldy     #%00000010
ins_try:
        tya
        sta     ACIA_CMD,x
        cmp     ACIA_CMD,x
        bne     ins_not
        iny
        cpy     #%00000100
        bne     ins_try
        sta     ACIA_STATUS,x           ; software reset
        lda     ACIA_CMD,x
        lsr
        bcc     ins_acia                ; DTR dropped: it really is a 6551
ins_not:
        pla
        sta     ACIA_CMD,x
        pla
        sta     ACIA_STATUS,x
ins_next:
        jmp     ins_card
ins_none:
        lda     #0
        tax
        rts

ins_acia:
        pla                             ; the two saved registers, discarded
        pla
        stx     vs_acia
        lda     #%00010000              ; 115 200 baud (external clock x16),
        sta     ACIA_CTRL,x             ; 8 bits, 1 stop
        lda     #%00001011              ; DTR, no interrupt, RTS low
        sta     ACIA_CMD,x
        ; The slot of the volumes: the first one of which no unit is taken.
        lda     #0
        sta     vs_slot
ins_slot:
        inc     vs_slot
        lda     vs_slot
        cmp     #8
        bcs     ins_none                ; seven slots taken: no room
        asl
        asl
        asl
        asl
        sta     vs_dev1
        ora     #$80
        sta     vs_dev2
        ldy     DEVCNT
ins_dev:
        lda     DEVLST,y
        cmp     vs_dev1
        beq     ins_slot
        cmp     vs_dev2
        beq     ins_slot
        dey
        bpl     ins_dev
        ; The slot is free: DEVADR, DEVLST, the thunk.
        lda     vs_slot
        asl
        tax
        lda     DEVADR,x
        sta     vs_orig
        lda     DEVADR+1,x
        sta     vs_orig+1
        lda     #<THUNK
        sta     DEVADR,x
        sta     DEVADR+16,x
        lda     #>THUNK
        sta     DEVADR+1,x
        sta     DEVADR+17,x
        ldy     DEVCNT
        iny
        lda     vs_dev1
        sta     DEVLST,y
        iny
        lda     vs_dev2
        sta     DEVLST,y
        sty     DEVCNT
        ldy     #thunk_len-1
ins_cpy:
        lda     thunk_src,y
        sta     THUNK,y
        dey
        bpl     ins_cpy
        jsr     ins_irq
        lda     #1
        sta     vs_on
        lda     vs_acia                 ; (serial slot << 4) | slot of the volumes
        sec
        sbc     #ACIA_OFS
        ora     vs_slot
        ldx     #0
        rts

; ----------------------------------------------------------------------
; The driver, as ProDOS calls it (through the thunk): $42-$47 set up,
; A = error and carry set on failure.
; ----------------------------------------------------------------------
vs_driver:
        cld
        lda     #0                      ; A = 0 (drive 1) or 2 (drive 2)
        ldx     P_UNIT
        cpx     vs_dev1
        beq     drv_cmd
        lda     #2
        cpx     vs_dev2
        beq     drv_cmd
        lda     #E_NODEV
        sec
        rts
drv_cmd:
        ldx     P_CMD
        beq     drv_status
        cpx     #1
        beq     drv_read
        cpx     #2
        bne     drv_other
        jmp     drv_write
drv_other:
        lda     #0                      ; FORMAT and the rest: nothing to do
        clc
        rts
drv_status:
        lda     #0                      ; unknown size: $FFFF blocks
        ldx     #$FF
        ldy     #$FF
        clc
        rts

drv_read:
        clc
        adc     #VD_READ                ; 3 or 5
        jsr     envelope                ; php, sei, X = 6551, the envelope sent
        jsr     expect_env              ; its echo
        bcs     drv_fail
        ldy     #0                      ; the time and date, into the XOR
rd_dt:  jsr     getc
        bcs     drv_fail
        sta     vs_dt,y
        eor     vs_chk
        sta     vs_chk
        iny
        cpy     #4
        bcc     rd_dt
        jsr     getc                    ; the XOR of the header
        bcs     drv_fail
        cmp     vs_chk
        bne     drv_fail
        lda     #0
        sta     vs_chk
        lda     #2                      ; the 512 bytes: two pages
        sta     vs_pg
        ldy     #0
rd_blk: jsr     getc
        bcs     drv_fail
        jsr     st_buf                  ; into ProDOS's bank (see the thunk)
        eor     vs_chk
        sta     vs_chk
        iny
        bne     rd_blk
        inc     P_BUF+1
        dec     vs_pg
        bne     rd_blk
        jsr     getc                    ; the XOR of the block
        bcs     drv_fail
        cmp     vs_chk
        bne     drv_fail
        dec     P_BUF+1                 ; the buffer as we received it
        dec     P_BUF+1
        lda     vs_dt                   ; the ProDOS clock set to the host's time
        sta     TIME
        lda     vs_dt+1
        sta     TIME+1
        lda     vs_dt+2
        sta     DATE
        lda     vs_dt+3
        sta     DATE+1
drv_ok:
        plp                             ; interrupts as before
        lda     #0
        clc
        rts
drv_fail:
        plp
        lda     #E_IO
        sec
        rts

drv_write:
        clc
        adc     #VD_WRITE               ; 2 or 4
        jsr     envelope
        lda     #0
        sta     vs_chk
        lda     #2
        sta     vs_pg
        ldy     #0
wr_blk: jsr     ld_buf                  ; from ProDOS's bank (see the thunk)
        jsr     putc_chk
        iny
        bne     wr_blk
        inc     P_BUF+1
        dec     vs_pg
        bne     wr_blk
        dec     P_BUF+1
        dec     P_BUF+1
        lda     vs_chk                  ; the XOR of the block
        jsr     putc
        jsr     expect_env              ; the echo of the envelope
        bcs     wr_fail
        jsr     getc                    ; the XOR of the block, as the host saw it
        bcs     wr_fail
        cmp     vs_chk
        beq     wr_ok
wr_fail:
        jmp     drv_fail
wr_ok:  jmp     drv_ok

; The echo of the envelope: $C5, the command, the block. Carry set if a
; byte is missing or differs.
expect_env:
        jsr     getc
        bcs     ex_bad
        cmp     #VD_ENV
        bne     ex_bad
        jsr     getc
        bcs     ex_bad
        cmp     vs_cmd
        bne     ex_bad
        jsr     getc
        bcs     ex_bad
        cmp     P_BLK
        bne     ex_bad
        jsr     getc
        bcs     ex_bad
        cmp     P_BLK+1
        bne     ex_bad
        clc
        rts
ex_bad: sec
        rts

; The envelope: A = the command. Disables interrupts (php on the caller's
; stack, picked up again by drv_ok/drv_fail), loads X, sends the five
; bytes and leaves vs_chk at their XOR.
envelope:
        sta     vs_cmd
        pla                             ; the return address, under the php
        tay
        pla
        php
        sei
        pha
        tya
        pha
        ldx     vs_acia
        lda     #0
        sta     vs_chk
        lda     #VD_ENV
        jsr     putc_chk
        lda     vs_cmd
        jsr     putc_chk
        lda     P_BLK
        jsr     putc_chk
        lda     P_BLK+1
        jsr     putc_chk
        lda     vs_chk
        jmp     putc

; One byte sent, and folded into the XOR.
putc_chk:
        jsr     putc
        eor     vs_chk
        sta     vs_chk
        rts

; One byte sent (A preserved). X = the 6551.
putc:
        pha
:       lda     ACIA_STATUS,x
        and     #$10                    ; TDRE
        beq     :-
        pla
        sta     ACIA_DATA,x
        rts

; One byte received in A, carry clear; carry set after ~0.3 s with nothing.
; X = the 6551, Y intact.
getc:
        lda     #0
        sta     vs_to
        lda     #$C0
        sta     vs_to+1
:       lda     ACIA_STATUS,x
        and     #$08                    ; RDRF
        bne     :+
        inc     vs_to
        bne     :-
        inc     vs_to+1
        bne     :-
        sec
        rts
:       lda     ACIA_DATA,x
        clc
        rts
