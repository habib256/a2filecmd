; format_diskii.s -- the physical formatting of a 5.25-inch floppy
; (Disk II, 16 sectors, volume 254), for the A2 File Cmd formatter
; (F key).
;
; The core comes from Jerry Hewett's "ProDOS Hyper-FORMAT" (Living Legends
; Software, 1985, public domain), taken up by Gary Desrochers (1989), then
; integrated by David Schmidt into ADTPro (GPL); the track write loop
; (Trans) comes from FASTDSK, via ADTPro. Here: split into three C calls,
; one track at a time, to display the progress, and without ADTPro's
; message system. The track image occupies $6500-$7FFF, outside
; FORMAT.SYS which fits below $6400: the sixteen sectors are at their
; original place ($6800-$7FFF), but the GAP1 preceding them is extended by
; 512 sync bytes. A track written longer than one disk revolution
; (6,862 bytes, against 6,250 to 6,400 depending on the drive speed, 6,656
; for POM2) overwrites the start of the revolution, that is this GAP1:
; nothing of the old contents survives, and the address field of sector 0
; stays out of reach. With the original GAP1, an emulator with a long
; revolution kept a piece of the old track, and sector 0 became unreadable.
;
;   unsigned char __fastcall__ diskii_begin(unsigned char slotdrive);
;       slotdrive: $60 for slot 6 drive 1, $E0 for drive 2.
;       Motor on, head on track 0, track image built. Returns 0.
;   unsigned char __fastcall__ diskii_track(unsigned char track);
;       Computes the address fields, positions the head, writes the track.
;       Returns 0 or a ProDOS error code.
;   void diskii_end(void);   Motor off.
;
; The softswitches are indexed by slot x 16 (SlotF = $60 for slot 6):
; Step0+SlotF = $C0E0, etc.

        .export _diskii_begin, _diskii_track, _diskii_end

Buffer  = $1D                   ; pointer (2 bytes), free for cc65 and ProDOS

Step0   = $C080
Step1   = $C081
Step2   = $C082
Step4   = $C084
Step6   = $C086
DiskOFF = $C088
DiskON  = $C089
Select  = $C08A
DiskRD  = $C08C
DiskWR  = $C08D
ModeRD  = $C08E
ModeWR  = $C08F

        .segment "BSS"
Slot:   .res 1                  ; slot x 16, bit 7 = drive 2
SlotF:  .res 1                  ; slot x 16 only
LByte:  .res 1
Count:  .res 1
Track:  .res 1
Sector: .res 1
TRKcur: .res 1
TRKdes: .res 1
LInOut: .res 1

        .segment "RODATA"
LAddr:  .byte $D5,$AA,$96       ; address prologue
        .byte $AA,$AA,$AA,$AA,$AA,$AA,$AA,$AA   ; volume, track, sector, checksum (4&4)
        .byte $DE,$AA,$EB       ; address epilogue
        .byte $7F,$7F,$7F,$7F,$7F,$7F           ; GAP2
        .byte $D5,$AA,$AD       ; data prologue
        .byte $00
LData:  .byte $DE,$AA,$EB       ; data epilogue
        .byte $7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F,$7F   ; GAP3
        .byte $00
LTable: .byte $02,$04,$06,$00   ; phases inward
        .byte $06,$04,$02,$00   ; outward

        .segment "CODE"

; -- diskii_begin ----------------------------------------------------------
_diskii_begin:
        sta Slot
        and #$70
        sta SlotF
        tax                     ; $60: drive 1
        lda Slot
        bpl :+
        inx                     ; $61: drive 2
:       lda Select,x            ; select the drive
        ldx SlotF
        lda DiskON,x            ; motor
        lda ModeRD,x
        lda DiskRD,x
        ; the write protection is read in Trans, with all phases off:
        ; phase 1 still energized would make it look write-protected
        lda #$23                ; assume the head is on track 35
        sta TRKcur
        lda #$00
        sta TRKdes
        jsr Seek                ; ... and bring it back to track 0
        ldx SlotF
        lda Step0,x             ; all phases off
        lda Step2,x
        lda Step4,x
        lda Step6,x
        jsr Build
        lda #0
        ldx #0
        rts

; -- diskii_track ---------------------------------------------------------
_diskii_track:
        sta Track
        sta TRKdes
        jsr Seek
        jsr Calc
        jsr Trans
        bcs @err
        lda #0
@err:   ldx #0
        rts

; -- diskii_end -----------------------------------------------------------
_diskii_end:
        ldx SlotF
        lda DiskOFF,x
        rts

; -- Build: GAP1 then 16 sector images between $6700 and $8000 -----------
Build:
        lda #$10
        ldx #$65
        sta Buffer
        stx Buffer+1
        ldy #$00
        lda #$7F
        sta LByte
        ldx #$F0                ; GAP1: $2F0 sync bytes ($7F) --
        jsr LFill               ; LFill returns X = 0: the next two do 256
        jsr LFill
        jsr LFill
        lda #$10
        sta Count
LImage:
        ldx #$00
ELoop:  lda LAddr,x
        beq LInfo
        sta (Buffer),y
        jsr LInc
        inx
        bne ELoop
LInfo:  ldx #$AB                ; 343 data bytes at $96 (zero in 6&2)
        lda #$96
        sta LByte
        jsr LFill
        ldx #$AC
        jsr LFill
        ldx #$00
YLoop:  lda LData,x
        beq LDecCnt
        sta (Buffer),y
        jsr LInc
        inx
        bne YLoop
LDecCnt:
        dec Count
        bne LImage
        rts
LFill:  lda LByte
        sta (Buffer),y
        jsr LInc
        dex
        bne LFill
        rts
LInc:   inc Buffer
        bne :+
        inc Buffer+1
:       rts

; -- Calc: volume, track, sector, checksum in 4&4 into the 16 headers ----
Calc:
        lda #$03
        ldx #$68
        sta Buffer
        stx Buffer+1
        lda #$00
        sta Sector
ZLoop:  ldy #$00
        lda #$FE                ; volume 254
        jsr LEncode
        lda Track
        jsr LEncode
        lda Sector
        jsr LEncode
        lda #$FE
        eor Track
        eor Sector
        jsr LEncode
        clc                     ; next sector: + 385
        lda Buffer
        adc #$81
        sta Buffer
        lda Buffer+1
        adc #$01
        sta Buffer+1
        inc Sector
        lda Sector
        cmp #$10
        bcc ZLoop
        rts
LEncode:
        pha
        lsr a
        ora #$AA
        sta (Buffer),y
        iny
        pla
        ora #$AA
        sta (Buffer),y
        iny
        rts

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
        clc
        rts
LWRprot:
        lda #$2B
        sec
        rts
