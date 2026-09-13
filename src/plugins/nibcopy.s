; FORMAT /RAM may overwrite MAIN $2000-$21FF. C must return first.
; This entire continuation, including its failure report, stays below $2000.
.export _plugin_entry, _nb_note, _nb_ram_note
.import _nb_run, _nb_cleanup_fn
.segment "CLEANUP"
_plugin_entry:
 jsr _nb_run
Finish:
 cmp #0
 beq FinishDone
 jsr FormatRam
 cmp #0
 bne FinishDone
 php
 sei
 lda _nb_note
 sta $1D
 lda _nb_note+1
 sta $1E
 ldy #0
: lda _nb_ram_note,y
 sta ($1D),y
 beq :+
 iny
 bne :-
: plp
FinishDone:
 rts
FormatRam:
 jmp (_nb_cleanup_fn)
_nb_note: .word 0
_nb_ram_note: .res 48,0
.assert * <= $2000, lderror, "NIBCOPY cleanup exceeds low window"

; NIBCOPY Disk II transport, NMOS-compatible. No MLI or C while main
; $6500-$84FF is borrowed. IRQ state and every borrowed byte are restored.
; AUX: $4000 capture source, $6000 verification, $8000 write image,
; $A000-$BFFF resident backup. Caller MUST have obtained AUX consent.
; Seek/write timing adapted from ../format_diskii.s (Hyper-FORMAT/FASTDSK).
.export _nb_begin, _nb_end, _nb_read, _nb_write, _nb_protected
.export _nb_fetch, _nb_store, _nb_address, _nb_buffer, _nb_track, _nb_bank
Buffer=$1D
Step0=$C080
Step1=$C081
Step2=$C082
Step4=$C084
Step6=$C086
DiskOFF=$C088
DiskON=$C089
Select=$C08A
DiskRD=$C08C
DiskWR=$C08D
ModeRD=$C08E
ModeWR=$C08F
.segment "BSS"
Slot: .res 1
SlotF: .res 1
Count: .res 1
TRKcur: .res 1
TRKdes: .res 1
LInOut: .res 1
_nb_address: .res 2
_nb_buffer: .res 2
_nb_track: .res 1
_nb_bank: .res 1
Result: .res 1
.segment "RODATA"
LTable: .byte $02,$04,$06,$00,$06,$04,$02,$00
.segment "CODE"
_nb_begin:
 sta Slot
 and #$70
 sta SlotF
 tax
 lda Slot
 bpl :+
 inx
: lda Select,x
 ldx SlotF
 lda ModeRD,x
 lda DiskRD,x
 lda DiskON,x
 lda #35
 sta TRKcur
 lda #0
 sta TRKdes
 jsr Seek
 ; Spin up even when drive was already at track zero.
 lda #30
 sta Count
: jsr Wait20
 dec Count
 bne :-
 rts
_nb_end:
 ldx SlotF
 lda ModeRD,x
 lda DiskRD,x
 lda DiskOFF,x
 rts
_nb_protected:
 ldx SlotF
 lda Step0,x
 lda Step2,x
 lda Step4,x
 lda Step6,x
 lda DiskWR,x
 lda ModeRD,x
 and #$80
 pha
 lda DiskRD,x
 pla
 ldx #0
 rts
; AUXMOVE uses $3C..$43; no resident state is kept there.
; Fetch/store exactly one page, to/from the caller's main-RAM buffer.
_nb_fetch:
 php
 sei
 clc
 lda _nb_address
 sta $3C
 lda _nb_address+1
 sta $3D
 lda _nb_buffer
 sta $42
 lda _nb_buffer+1
 sta $43
 jmp PageMove
_nb_store:
 php
 sei
 sec
 lda _nb_buffer
 sta $3C
 lda _nb_buffer+1
 sta $3D
 lda _nb_address
 sta $42
 lda _nb_address+1
 sta $43
PageMove:
 php
 clc
 lda $3C
 adc #$FF
 sta $3E
 lda $3D
 adc #0
 sta $3F
 plp
 jsr $C311
 plp
 rts
; Main -> AUX backup, then AUX -> main restore. Sources differ, unlike
; the formatter's same-address save. All 8192 bytes, including tails.
Save:
 sec
 lda #$65
 ldx #$A0
 bne Move8K
Restore:
 clc
 lda #$A0
 ldx #$65
Move8K:
 php
 sta $3D
 stx $43
 clc
 adc #$1F
 sta $3F
 lda #0
 sta $3C
 sta $42
 lda #$FF
 sta $3E
 plp
 jmp $C311
Enter:
 php
 pla
 sta SavedP+1
 sei
 cld
 lda _nb_track
 sta TRKdes
 jsr Seek
 jsr Save
 rts
Leave:
 jsr Restore
SavedP:
 lda #0
 pha
 plp
 lda Result
 ldx #0
 rts
 .align 256
_nb_read:
 jsr Enter
 lda #$65
 sta Buffer+1
 lda #0
 sta Buffer
 sta Result
 tay
 ldx SlotF
 lda ModeRD,x
 lda DiskRD,x
 ; Discard an existing latch; read a bounded 8192-byte stream.
 jmp ReadByte
 ; Bounded straight-line polling: a timer decrement in the polling loop
 ; costs 14 cycles between latch reads and loses bits on real LSS hardware.
 ; Twelve 7-cycle probes bound a stuck latch without stretching any probe.
 .align 256
ReadByte:
Poll:
 .repeat 12
  lda DiskRD,x
  bpl :+
  jmp GotByte
 :
 .endrepeat
 lda #$27
 sta Result
 jmp Leave
GotByte:
 sta (Buffer),y
 iny
 bne ReadByte
 inc Buffer+1
 lda Buffer+1
 cmp #$85
 bne ReadByte
 sec
 lda #$65
 ldx _nb_bank
 jsr Move8K
 jmp Leave
_nb_write:
 jsr Enter
 clc
 lda #$80
 ldx #$65
 jsr Move8K
 jsr Trans
 sta Result
 jmp Leave
; -- Seek: move the head from TRKcur to TRKdes ---------------------------
Seek:
        lda #$00
        sta LInOut
        lda TRKcur
        sec
        sbc TRKdes
        beq LExit
        bcs LMove
        eor #$FF
        adc #$01
LMove:  sta Count
        rol LInOut
        lsr TRKcur
        rol LInOut
        asl LInOut
        ldy LInOut
ALoop:  lda LTable,y
        jsr Phase
        lda LTable+1,y
        jsr Phase
        tya
        eor #$02
        tay
        dec Count
        bne ALoop
        lda TRKdes
        sta TRKcur
LExit:  rts

Phase:  ora SlotF
        tax
        lda Step1,x             ; phase on
        jsr Wait20              ; 20 ms
        lda Step0,x             ; phase off
        rts

; 20 ms without the ROM: cc65 leaves the language card readable, and $FCA8
; lands in ProDOS there, not in the monitor. 15 x 256 x 5 cycles = 19,200.
; A, X and Y are preserved: Phase turns the phase off with X right after,
; and a phase 1 left energized reads as a write-protected floppy.
Wait20: pha
        txa
        pha
        tya
        pha
        ldy #15
@outer: ldx #0
@inner: dex
        bne @inner
        dey
        bne @outer
        pla
        tay
        pla
        tax
        pla
        rts

; -- Trans: write the track image to the disk ----------------------------
; The loop is calibrated to the cycle: it must fit within one page, hence
; the alignment. Returns C=1 and A=$2B if the floppy is write-protected.
        .align 256
Trans:
        lda #$00
        ldx #$65
        sta Buffer
        stx Buffer+1
        ldy #$32
        ldx SlotF
        sec
        lda DiskWR,x
        lda ModeRD,x
        bmi LWRprot
        lda #$FF
        sta ModeWR,x
        cmp DiskRD,x
        nop
        jmp LSync2
LSync1: eor #$80
        nop
        nop
        jmp MStore
LSync2: pha
        pla
LSync3: lda (Buffer),y
        cmp #$80
        bcc LSync1
        nop
MStore: sta DiskWR,x
        cmp DiskRD,x
        iny
        bne LSync2
        inc Buffer+1
        bpl LSync3              ; up to $8000
        lda ModeRD,x
        lda DiskRD,x
        lda #0
        clc
        rts
LWRprot:
        lda #$2B
        sec
        rts

; A taken branch must never add a page-crossing cycle to the write loop.
        .assert >LSync1 = >MStore, lderror, "Disk II write loop crosses a page"
        .assert >LSync2 = >(MStore+12), lderror, "Disk II write branch crosses a page"

.assert >ReadByte = >GotByte, lderror, "NIBCOPY read loop page crossing"

.assert Finish < $2000, lderror, "NIBCOPY cleanup must survive RAM formatter"
