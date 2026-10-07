; vsdrive.s -- VDrive: two ProDOS volumes served over the serial line.
;
;   unsigned char vsdrive_install(void);     returns (serial slot << 4) | slot of
;                                            the volumes; (serial slot << 4) alone
;                                            when no slot is free for them; 0
;                                            without a serial card (or with no
;                                            interrupt handler left in ProDOS)
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
; install time we look for a serial card in slot 2, then 3 to 7 -- never
; slot 1, the printer's (see `slots`) -- (the Pascal 1.1 signature of its
; ROM: $Cn05=$38 $Cn07=$18 $Cn0B=$01 $Cn0C=$31, its mode switches read and
; found in communications mode -- a card set up for a printer is left
; before any write --, then a 6551 that answers), we take the first slot
; 1..7 of which neither drive 1 nor drive 2 appears in DEVLST, we register
; an interrupt handler with ProDOS, and only then is the 6551 set to
; 115 200 baud 8N1 with DTR up: the slot's DEVADR entry receives our driver,
; its two units enter DEVLST, and the volume list shows them like any other
; disk. Without a free slot, or when ProDOS has no interrupt handler left
; (ALLOC_INTERRUPT fails), nothing is installed and the card stays as the
; probe left it, DTR down: a 6551 with DTR up and no handler would raise
; interrupts nobody claims (see irq_src). The destructor undoes everything:
; ProDOS must no longer point at us once the program is gone.
;
; Space: the main window is full, so the driver and its serial layer live
; in the language card (segment LC, bank 2, $D400-$DFFF). ProDOS, though,
; calls its drivers from ITS bank 1: a thunk in page 3 ($0300, free under
; ProDOS; chain.s only puts its own thunk there after the destructor)
; switches bank 2 in for reading, calls the driver, and restores bank 1 for
; read/write before returning to the MLI. The language card is read-only
; (crt0: bit $C080): the variables are in page 3 as well.
;
; Timing: at 115 200 baud a byte arrives every 88 cycles (1.02 MHz), and the
; 6551 holds ONE byte: the receive loop must have taken each byte before the
; next one is complete, or the register overruns and the block is lost. The
; loop runs from page 3 (rd_src), with ProDOS's bank in, so that it stores
; straight into the caller's buffer: about 33 cycles a byte once the byte
; is there, 19 more at most to notice it (tools/test_vsdrive.py measures
; both under sim65 and holds the sum under 85). The former loop went
; through getc/wait and a per-byte thunk, 100 cycles a byte: fine behind
; POM2's 4 KB FIFO, an overrun after a few bytes on a real card. Interrupts
; are disabled (SEI) for the duration of a block, otherwise the Mockingboard
; music would lose bytes. Each wait for a byte sent has a timeout (~0.3 s), a
; block's bytes may idle ~0.3 s in total: an absent host, or a 6551 whose
; transmitter never empties (CTS not asserted: no cable), yields an I/O
; error ($27) instead of freezing the machine -- the volume list reports it.
;
; Failures: a read that fails leaves in the caller's buffer whatever had
; arrived, as the Disk II driver does -- ProDOS treats the buffer of a failed
; READ_BLOCK as undefined -- but $44-$45 are given back as ProDOS set them.
; Before every command, and after every failure, the receive side is
; drained (drain): the late reply of a call that timed out must not be
; taken for the echo of the next one, which would fail in turn, and so on.

        .export         _vsdrive_install, _vsdrive_uninstall
        .destructor     _vsdrive_uninstall, 9
        .importzp       ptr1

; A byte to zero: stz on the 65C02 edition (two bytes fewer in the full
; language card), lda #0 / sta on the 6502. A is not 0 afterwards.
.macro  ZERO    addr
.ifpc02
        stz     addr
.else
        lda     #0
        sta     addr
.endif
.endmacro

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
SSC_DSW1        = $C081 - ACIA_OFS      ; the SSC's DIP bank 1 (see the probe)
RDRF            = $08                   ; status: a byte received
TDRE            = $10                   ; status: the transmitter is empty

; The protocol
VD_ENV          = $C5
VD_WRITE        = $02
VD_READ         = $03

; Page 3: the thunk at $0300, the variables behind it.
THUNK           = $0300
vs_slot         = $03B0         ; the slot of the volumes
vs_dev1         = $03B1         ; its drive 1 unit (slot x 16)
vs_dev2         = $03B2         ; drive 2 (+ $80)
vs_orig         = $03B3         ; the former DEVADR words of this slot, drive 1
                                ; then drive 2 (4 bytes; see swap_devadr)
vs_on           = $03B7         ; 1: installed
vs_acia         = $03B8         ; the X index of the 6551 (slot x 16 + $8F)
vs_chk          = $03B9
vs_env          = $03BA         ; the envelope (4 bytes): $C5, the command,
                                ; the block -- sent, then expected back
vs_to           = $03BE         ; the timeout countdown (2 bytes)
vs_dt           = $03C0         ; time and date received (4 bytes), then
vs_pg           = $03C4         ; their XOR -- reused as the pages still to go
vs_ip           = $03C5         ; the MLI parameters of our interrupt handler
                                ; (4 bytes): count, number, address
vs_int          = vs_ip+1       ; the ProDOS number of the handler, 0 without
vs_sp           = $03C9         ; the 6502 stack under the envelope's php
vs_msk          = $03CA         ; the 6551 status bit awaited
vs_bufhi        = $03CB         ; $45 as ProDOS gave it (the loop moves it)
        .assert vs_bufhi < $03D0, error, "VDrive page-3 variables reach the vectors"

; ----------------------------------------------------------------------
; The destructor: in the main window, because _exit (crt0) restores the ROM
; before calling donelib -- the language card is no longer readable then.
; ----------------------------------------------------------------------
        .segment "CODE"

_vsdrive_uninstall:
        lda     vs_on
        beq     un_done
        dec     vs_on
        ldx     vs_acia                 ; DTR drops first: the port closes,
        lda     #$0A                    ; and no interrupt comes once the
        sta     ACIA_CMD,x              ; handler is gone
        jsr     del_irq
        jsr     swap_devadr             ; the former drivers take DEVADR back
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
un_done:
        rts

; Exchanges the DEVADR words of slot vs_slot, drive 1 and drive 2, with
; the four bytes of vs_orig. At install time vs_orig holds the thunk's
; address twice: ProDOS gets the thunk, vs_orig the former drivers --
; each drive its own, which need not be the same one (a /RAM moved out of
; DEVLST keeps $FF00 in drive 2). The destructor exchanges them back.
; In the main window: the destructor runs with the ROM switched in.
swap_devadr:
        ldy     #3
sw_byte:
        lda     vs_slot
        asl                             ; slot x 2 (carry clear: slot < 8)
        adc     sw_ofs,y
        tax
        lda     DEVADR,x
        pha
        lda     vs_orig,y
        sta     DEVADR,x
        pla
        sta     vs_orig,y
        dey
        bpl     sw_byte
        rts
sw_ofs: .byte   0, 1, 16, 17

; ----------------------------------------------------------------------
; The rest in the language card.
; ----------------------------------------------------------------------
        .segment "LC"

; The Pascal 1.1 signature of a type 1 serial or parallel card.
id_ofs: .byte   $05, $07, $0B, $0C
id_val: .byte   $38, $18, $01, $31
; The slots in the order we probe them (ins_card): 2 first -- the modem
; port of a //c, the usual place of a modem on a IIe --, then 3 to 7.
; NEVER slot 1: it is the printer's, the //c's port 1 (printer port) and
; the SSC a //e keeps for its printer, with the same signature and the
; same 6551. The probe below writes the 6551's command register, and a
; card taken is reprogrammed (115 200 baud, DTR) and sent an envelope at
; every block: on a printer that is garbage on paper and its settings
; lost. Slot 1 is not even read, so a VDrive host on a slot-1 SSC is not
; served. In slots 2-7, an SSC whose switches say printer is skipped
; before the probe writes anything (see ins_6551).
; (Michel Sitruk, //c, 0.6.7: the VDrive went out on the printer port;
; bench/vdrive_printer.py: a //e with its only SSC in slot 1 got 100 bytes
; of envelopes and control $10, command $0B.)
SLOT_FIRST      = $C2           ; the ROM page of the first slot probed
SLOT_END        = $C8           ; one past the last

; The thunk, copied to $0300. Its source is in main memory (segment CODE),
; not in the language card: the LC image is full, and a source that is
; only ever copied has no business there.
;
; The driver lives in bank 2 of the language card ($D400-$DFFF, the LC
; image of cc65) and ProDOS in bank 1 -- with its general buffer GBUF at
; $DC00: that is where ON_LINE, reading a directory and writing a
; directory block put P_BUF. A `sta (P_BUF),y` executed from bank 2
; cannot reach it (the two banks share the same addresses, and bank 2 was
; even read-only): the buffer kept the last block read by the Disk II
; driver, and the remote volume showed up under the floppy's name. Both
; buffer accesses therefore go through here, in page 3, outside the
; language card: bank 1 read/write while the buffer is touched, then back
; to bank 2 to find the driver again. (POM2 bench, bench/vdrive.py,
; 2026-09-08.) The whole receive loop of a block is here (rd_src): a
; thunk per byte cost more than a byte time (see the header).
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
ld_src:                                 ; A <- (P_BUF),y in ProDOS's bank
        bit     $C08B
        bit     $C08B
        lda     (P_BUF),y
rd_out:
        bit     $C080
        rts
; The block received: vs_pg pages into (P_BUF),y onwards in ProDOS's bank,
; XORed into vs_chk, P_BUF+1 moved to the last page (drv_exit gives it
; back). X = the 6551, Y = 0. Carry set when the countdown vs_to runs out
; while waiting (the caller sets vs_to+1). Cycles, byte there: lda 5 (the
; index crosses a page), and 2, beq 2, lda 5, sta 6, eor 4, sta 4, iny 2,
; bne 3 = 33; a poll that finds nothing: 5+2+3+6+3 = 19.
rd_src:
        bit     $C08B
        bit     $C08B
rd_poll:
        lda     ACIA_STATUS,x
        and     #RDRF
        beq     rd_wait
        lda     ACIA_DATA,x
        sta     (P_BUF),y
        eor     vs_chk
        sta     vs_chk
        iny
        bne     rd_poll
        inc     P_BUF+1
        dec     vs_pg
        bne     rd_poll
        clc
        bcc     rd_out
rd_wait:
        inc     vs_to
        bne     rd_poll
        inc     vs_to+1
        bne     rd_poll
        sec
        bcs     rd_out
; The ProDOS interrupt handler. A 6551 raises IRQ when DCD or DSR changes,
; whatever its registers say: on a real SSC whose cable carries those
; lines, unplugging the host would kill ProDOS ("RESTART SYSTEM -
; $01", nobody claimed the interrupt). Reading the status register
; acknowledges it; bit 7 says whether it was us: into the carry, inverted
; (clear = claimed). The low byte of the address is filled in at install
; time (page 3: writable). ProDOS 8 wants its interrupt handlers to begin
; with CLD (Technical Reference, ALLOC_INTERRUPT).
irq_src:
        cld
        lda     $C089                   ; -> $C089 + slot x 16
        eor     #$80
        asl
        rts
thunk_len = * - thunk_src
irq_adr = THUNK + (irq_src - thunk_src) + 2
IRQH    = THUNK + (irq_src - thunk_src)
rd_buf  = THUNK + (rd_src - thunk_src)
ld_buf  = THUNK + (ld_src - thunk_src)
        .assert THUNK + thunk_len <= vs_slot, error, "VDrive thunk reaches its variables"

; The two interrupt calls of the MLI ($40 ALLOC, $41 DEALLOC), on the
; parameter block vs_ip, from the main window: the MLI reads the bytes
; behind a `jsr $BF00` with ProDOS's bank 1 in, so no call may be inlined
; in the language card. Main RAM: the command byte is written in place.
int_mli:
        sta     int_cmd
        jsr     $BF00
int_cmd:.byte   $40
        .word   vs_ip
        rts

; Removing the handler, in the main window: it serves the destructor,
; outside the language card. vs_int (the number ProDOS gave, 0 when it
; gave none) stays in the parameter block, where $41 wants it.
del_irq:
        lda     vs_int
        beq     :+
        lda     #1
        sta     vs_ip
        lda     #$41
        jsr     int_mli
:       rts

; The install runs once, from the language card like the driver, on both
; editions: on the 6502 one, in main memory, it made A2FILE.CODE a block
; longer on the floppy, while the language image has a fixed size.
        .segment "LC"
; Registering the handler. The thunk is in place: the address of the
; 6551's status register goes into its lda ($C0 is there already). Z set
; on failure, vs_int 0.
ins_irq:
        lda     vs_acia                 ; $C089 + slot x 16 = vs_acia - $8F + $89
        sec
        sbc     #ACIA_OFS-$89
        sta     irq_adr
        lda     #2
        sta     vs_ip
        lda     #<IRQH
        sta     vs_ip+2
        lda     #>IRQH
        sta     vs_ip+3
        lda     #$40
        jsr     int_mli
        bcc     :+
        ZERO    vs_int                  ; no room left in ProDOS: no handler
:       lda     vs_int
        rts

; unsigned char vsdrive_install(void)
_vsdrive_install:
        ZERO    vs_on                   ; page 3 is not initialised: without
        ZERO    ptr1                    ; a card, the destructor must not undo
                                        ; anything
        lda     #SLOT_FIRST
        sta     vs_to                   ; the slot being probed
ins_card:
        lda     vs_to
        cmp     #SLOT_END
        beq     ins_none                ; past the last slot: no card
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
        ; A Super Serial Card set to anything but communications mode is a
        ; printer's: leave it before the first write, and before reading
        ; its 6551 (a status read acknowledges the ACIA's interrupt). The
        ; mode is SW1-5/6, DIP bank 1 at $C081 + slot x 16, bits $03:
        ; $00 communications, $01 and $03 the SIC P8/P8A emulations, $02
        ; printer (MAME a2ssc.cpp read_c0nx and DSW1; Apple's firmware
        ; 341-0065-A reads the same `lda $C081,y` at $C828 and takes its
        ; printer path for every value but $00). Reading it has no side
        ; effect. The Pascal byte $31 is also that of the //c's ports, which
        ; have no switches ($C0A1 is not a register there): on a //c (MACHID
        ; bits 7,6,3 = 1,0,1, ProDOS 8 Technical Reference 5.2.4) port 2 is
        ; taken as before -- nothing can tell a printer on it from a modem.
        ; A IIgs reads as a IIe: its $C0n1 is a real SSC's switches or no
        ; register at all (its own ports are an SCC at $C038-$C03B).
        lda     $BF98                   ; MACHID
        and     #$C8
        cmp     #$88
        beq     ins_6551                ; a //c: no switches to read
        lda     SSC_DSW1,x
        and     #$03
        bne     ins_next                ; printer or SIC emulation: not ours
ins_6551:
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
        pla                             ; the two saved registers, discarded:
        pla                             ; the 6551 stays reset (DTR down)
        stx     vs_acia                 ; until everything else is in place
        ; The slot of the volumes: the first one of which no unit is taken.
        ZERO    vs_slot
ins_slot:
        inc     vs_slot
        lda     vs_slot
        cmp     #8
        bcs     ins_noslot              ; seven slots taken: no room
        asl
        asl
        asl
        asl
        sta     vs_dev1
        ora     #$80
        sta     vs_dev2
        ldy     DEVCNT
ins_dev:
        lda     DEVLST,y                ; DSSSIIII: the slot alone. A Disk II
        and     #$70                    ; has IIII = 0, but a SmartPort or a
        cmp     vs_dev1                 ; ProFile unit does not, nor /RAM
        beq     ins_slot                ; ($BF): compared whole, their slot
        dey                             ; passed for free and was taken over
        bpl     ins_dev
        ; The slot is free: the thunk, the handler -- ProDOS may have none
        ; left, and then nothing has been touched --, DEVADR (both drives),
        ; DEVLST, and the 6551 last.
        ldy     #thunk_len-1
ins_cpy:
        lda     thunk_src,y
        sta     THUNK,y
        dey
        bpl     ins_cpy
        jsr     ins_irq
        beq     ins_none
        lda     #<THUNK
        sta     vs_orig
        sta     vs_orig+2
        lda     #>THUNK
        sta     vs_orig+1
        sta     vs_orig+3
        jsr     swap_devadr
        ldy     DEVCNT
        iny
        lda     vs_dev1
        sta     DEVLST,y
        iny
        lda     vs_dev2
        sta     DEVLST,y
        sty     DEVCNT
        ldx     vs_acia
        lda     #%00010000              ; 115 200 baud (external clock x16),
        sta     ACIA_CTRL,x             ; 8 bits, 1 stop
        lda     #%00001011              ; DTR, no interrupt, RTS low
        sta     ACIA_CMD,x
        lda     #1
        sta     vs_on
        bne     ins_ret
ins_noslot:                             ; a card but no slot for its volumes:
        ZERO    vs_slot                 ; (serial slot << 4) | 0, so that the
                                        ; status line says why (nothing touched)
ins_ret:
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
        .segment "LC"
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
        bne     drv_status              ; FORMAT and the rest: nothing to do
        jmp     drv_write
drv_status:
        lda     #0                      ; the size: 0 blocks, "unknown". The
        tax                             ; protocol has no size query, and
        tay                             ; $FFFF let FORMAT write a 65535-
        clc                             ; block volume past the end of a
        rts                             ; blank image; the volume header
                                        ; stays the only size (format.c)

drv_read:
        clc
        adc     #VD_READ                ; 3 or 5
        jsr     envelope                ; php, sei, X = 6551, the envelope sent
        jsr     expect_env              ; its echo
        bcs     drv_fail
        ldy     #0                      ; the time and date and their XOR
rd_dt:  jsr     getc                    ; (the fifth byte lands in vs_pg,
        bcs     drv_fail                ; set below): folded into the XOR
        sta     vs_dt,y                 ; of the envelope, zero when right
        eor     vs_chk
        sta     vs_chk
        iny
        cpy     #5
        bcc     rd_dt
        lda     vs_chk
        bne     drv_fail
        lda     #2                      ; the 512 bytes: two pages, from
        sta     vs_pg                   ; page 3 (see rd_src), with ~0.3 s
        lda     #$C0                    ; of waiting in all
        sta     vs_to+1
        ldy     #0
        jsr     rd_buf
        bcs     drv_fail
        jsr     getc                    ; the XOR of the block
        bcs     drv_fail
        eor     vs_chk
        bne     drv_fail
        ldy     #3                      ; the ProDOS clock set to the host's
rd_clk: tya                             ; time: vs_dt holds time then date,
        eor     #2                      ; ProDOS DATE ($BF90) then TIME
        tax
        lda     vs_dt,y
        sta     DATE,x
        dey
        bpl     rd_clk
drv_ok:
        plp                             ; interrupts as before
        lda     #0
        clc
        bcc     drv_exit
drv_fail:
        jsr     drain                   ; the rest of a late or broken reply
        plp
        lda     #E_IO
        sec
drv_exit:
        ldy     vs_bufhi                ; $45 as ProDOS gave it
        sty     P_BUF+1
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

; The echo of the envelope: its four bytes, byte for byte. Carry set if
; one is missing or differs.
expect_env:
        ldy     #0
ex_byte:
        jsr     getc
        bcs     ex_bad
        cmp     vs_env,y
        bne     ex_bad
        iny
        cpy     #4
        bcc     ex_byte
        clc
        rts
ex_bad: sec
        rts

; The envelope: A = the command. Disables interrupts (php on the caller's
; stack, picked up again by drv_ok/drv_fail), keeps $45, builds the four
; bytes in vs_env, drains the line, loads X, sends the four bytes and
; their XOR, and leaves vs_chk at that XOR.
envelope:
        sta     vs_env+1
        pla                             ; the return address, under the php
        tay
        pla
        php
        sei
        tsx                             ; putc's way out (see putc)
        stx     vs_sp
        pha
        tya
        pha
        lda     P_BUF+1
        sta     vs_bufhi
        lda     #VD_ENV
        sta     vs_env
        lda     P_BLK
        sta     vs_env+2
        lda     P_BLK+1
        sta     vs_env+3
        jsr     drain
        lda     #0
        sta     vs_chk
        tay
en_byte:
        lda     vs_env,y
        jsr     putc_chk
        iny
        cpy     #4
        bcc     en_byte
        lda     vs_chk
        jmp     putc

; One byte sent, and folded into the XOR. getc and putc_chk go where the
; link has room: the language card on the 65C02 edition, whose main window
; is the fuller, main memory on the 6502 one, whose card is. Both run with
; bank 2 readable, from the driver.
.ifdef A2_6502
        .segment "CODE"
.endif
putc_chk:
        jsr     putc
        eor     vs_chk
        sta     vs_chk
        rts

; One byte received in A, carry clear; carry set after ~0.3 s with nothing
; (the data register read then is harmless). X = the 6551, Y intact.
getc:
        lda     #RDRF
        jsr     wait
        lda     ACIA_DATA,x
        rts
        .segment "LC"

; One byte sent (A preserved). X = the 6551. A transmitter that stays full
; (CTS high: no cable, no host) must not freeze the machine with interrupts
; off: after ~0.3 s the stack goes back to where the envelope left it --
; the php on top -- and the driver returns its I/O error.
putc:
        pha
        lda     #TDRE
        jsr     wait
        pla
        bcs     pu_dead
        sta     ACIA_DATA,x
        rts
pu_dead:
        ldx     vs_sp
        txs
        jmp     drv_fail

; Waits for the status bit A of the 6551 X: carry clear when it is up,
; set after ~0.3 s (the low byte of the countdown starts wherever it is).
wait:
        sta     vs_msk
        lda     #$C0
        sta     vs_to+1
:       lda     ACIA_STATUS,x
        and     vs_msk
        bne     :+
        inc     vs_to
        bne     :-
        inc     vs_to+1
        bne     :-
        sec
        rts
:       clc
        rts

; Reads and drops what the 6551 holds or still receives, until the line
; has stayed quiet for 64 polls (~1 000 cycles, eleven byte times): before
; a command, so that the late reply of a call that timed out is not taken
; for the echo of this one; after a failure, until the host has finished
; the block it was sending. Bounded by the countdown: ~16 K bytes of
; continuous noise (~1.5 s). Loads X with the 6551 (pu_dead lost it).
drain:
        lda     #$C0
        sta     vs_to+1
        ldx     vs_acia
dr_new: ldy     #$C0
dr_poll:
        lda     ACIA_STATUS,x
        and     #RDRF
        beq     dr_idle
        lda     ACIA_DATA,x
        inc     vs_to
        bne     dr_new
        inc     vs_to+1
        bne     dr_new
        rts
dr_idle:
        iny
        bne     dr_poll
        rts
