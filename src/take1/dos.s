; dos.s -- TAKE1.SYSTEM: the command, and the files of a movie (DOS 3.3
; binary files on a disk image, on a real disk, or extracted to ProDOS).
;
; The command in the startup buffer (path0, length first, 46 characters at
; most; docs/TAKE1-FORMAT.md, "The player in A2 File Cmd"):
;
;   /PATH/TO/IMAGE.DSK,TTSS   the movie is a file of a DOS 3.3 image
;                             (.DSK/.DO in DOS order, or a DOS-order .2MG);
;                             TT, SS: its first track/sector list (hex)
;   %UU,TTSS                  the same on a real DOS 3.3 disk, ProDOS unit
;                             UU (hex), read with READ_BLOCK
;   /PATH/TO/MV.NAME          the movie is a ProDOS file extracted by A2 File
;                             Cmd; its files are found in the same directory
;                             under the names A2 File Cmd gave them
;
; dstart reads the command (and a .2MG's header); t1_mload (the engine's
; hook) reads the movie and sets t1_name to its name: "THE MOVIE" on a
; disk, its file name otherwise; t1_load (the engine's hook) reads the file
; named t1_name: on a disk, found by name in the DOS 3.3 catalog, its data
; the sectors its T/S lists give (a pair 0, 0 is a hole of zeros), the
; 4-byte binary header giving the length; else the ProDOS file of the
; movie's directory, under the name A2 File Cmd gives it. Errors: C = 1, A =
; E_NOTFOUND (no such file), E_READ (an I/O error, a damaged chain: a
; catalog or T/S chain longer than the disk, a file running short), E_BIG
; (more than t1_max), E_CMD (the command). A read error is never taken for
; the end of a file.
;
; Read-only: OPEN, SET_MARK, READ, CLOSE, READ_BLOCK only. Each call opens
; and closes what it reads: no file stays open between calls. Buffers: the
; page that is not shown (t1_front ^ $60), free whenever t1_load is called:
; +$000 the ProDOS I/O buffer, +$400 the block (sector) buffer, +$600 the
; T/S list, +$700 the path. ProDOS READs only into the block buffer; the
; data are copied from it. tools/test_take1.py runs this file under sim65
; with a fake MLI that injects errors.

        .export t1_load, t1_mload, dstart, E_CMD
        .import t1_name, t1_dest, t1_max, t1_len, t1_front
        .import path0

MLI     = $BF00
E_NOTFOUND = 1
E_READ  = 2
E_BIG   = 3
E_CMD   = 5
M_IMAGE = 0
M_UNIT  = 1
M_FILES = 2
MAXSEC  = 560                   ; sectors on a disk: longer chains are damaged

        .zeropage
secp:   .res 2          ; the sector read (in the block buffer)
tsp:    .res 2          ; the T/S list
op:     .res 2          ; where the data go
pp:     .res 2          ; the path built

        .segment "HIBSS"
cmd:    .res 65         ; the command, length first (path0 is overwritten)
mode:   .res 1
unit:   .res 1          ; M_UNIT: the ProDOS unit
dlen:   .res 1          ; M_IMAGE: the image path's length; M_FILES: the
                        ; directory's, its last '/' included
is2mg:  .res 1
base:   .res 3          ; M_IMAGE: the offset of sector (0, 0)
mt:     .res 1          ; the movie's first T/S list
ms:     .res 1
ft:     .res 1          ; the file read: its next T/S list
fs:     .res 1
cnt:    .res 2          ; sectors read in this chain
hcnt:   .res 1          ; header bytes seen (4: the length is known)
need:   .res 2          ; the file's length
got:    .res 2          ; its bytes delivered
pidx:   .res 1
spare:  .res 1          ; the free page (high byte)
done:   .res 1
mvname: .res 24         ; the movie's name, length first

        .segment "LOADER"               ; (once, from page 1: page 2 is free)
; -- the command --------------------------------------------------------------
; Reads the command: mode, the movie's place and name. C = 1: A = the
; error (t1_name: the movie's name, if it is known).
dstart: jsr     setspare
        ldx     path0                   ; the command, kept
        cpx     #47
        bcs     @bad
        txa
        beq     @bad
:       lda     path0,x
        sta     cmd,x
        dex
        bpl     :-
        lda     cmd+1
        cmp     #'%'
        beq     @unit
        ldx     cmd                     ; a comma: an image
:       lda     cmd,x
        cmp     #','
        beq     @image
        dex
        bne     :-
        ; a ProDOS path: its directory, then the movie itself
        lda     #M_FILES
        sta     mode
        ldx     cmd
:       lda     cmd,x
        cmp     #'/'
        beq     :+
        dex
        bne     :-
:       stx     dlen
        ldy     #0                      ; the movie's name: the file's
:       cpx     cmd
        beq     :+
        inx
        lda     cmd,x
        sta     mvname+1,y
        iny
        cpy     #23
        bne     :-
:       sty     mvname
        jmp     setname
@bad:   lda     #E_CMD
        sec
        rts
@unit:  lda     cmd                     ; %UU,TTSS
        cmp     #8
        bne     @bad
        lda     cmd+4
        cmp     #','
        bne     @bad
        ldx     #2
        jsr     hex2
        bcs     @bad
        sta     unit
        lda     #M_UNIT
        sta     mode
        ldx     #5
        bne     @ttss                   ; (always)
@image: stx     dlen                    ; PATH,TTSS: 4 digits after it
        dec     dlen
        txa
        clc
        adc     #4
        cmp     cmd
        bne     @bad
        lda     dlen
        beq     @bad
        lda     #M_IMAGE
        sta     mode
        inx
@ttss:  stx     pidx
        jsr     hex2
        bcs     @bad
        sta     mt
        ldx     pidx
        inx
        inx
        jsr     hex2
        bcs     @bad
        sta     ms
        ldx     #9                      ; the movie's name: "THE MOVIE"
:       lda     smovie,x
        sta     mvname,x
        dex
        bpl     :-
        jsr     setname
        lda     #0
        sta     is2mg
        sta     base
        sta     base+1
        sta     base+2
        lda     mode
        bne     @read
        ldx     dlen                    ; .2MG: the header gives the offset
        ldy     #3
:       lda     cmd,x
        and     #$DF                    ; (upper case; '.' and '2' kept as
        cmp     s2mg,y                  ;  $0E, $12: compared so)
        bne     @read
        dex
        dey
        bpl     :-
        inc     is2mg
@read:  lda     is2mg
        beq     @ok
        jsr     iopen
        bcs     @rts
        jsr     hdr2mg
        jmp     iclose
@ok:    clc
@rts:   rts

; A = the two hex digits at cmd+X, cmd+X+1; C = 1 if not hex.
hex2:   jsr     hex1
        bcs     :+
        asl
        asl
        asl
        asl
        sta     pp
        inx
        jsr     hex1
        bcs     :+
        ora     pp
        clc
:       rts
hex1:   lda     cmd,x
        and     #$7F
        cmp     #'a'
        bcc     :+
        and     #$DF
:       sec
        sbc     #'0'
        cmp     #10
        bcc     @ok
        sbc     #7                      ; 'A'-'F'
        cmp     #10
        bcc     @no
        cmp     #16
        bcs     @no
@ok:    clc
        rts
@no:    sec
        rts

; .2MG: "2IMG", format 0 (DOS order), the data offset (under 16 MB).
hdr2mg: lda     #0
        sta     markp+2
        sta     markp+3
        sta     markp+4
        jsr     setmark
        bcs     @rts
        lda     #64
        jsr     rdblk
        bcs     @rts
        ldy     #3
:       lda     (secp),y
        cmp     smagic,y
        bne     @bad
        dey
        bpl     :-
        ldy     #$0C
        lda     (secp),y
        bne     @bad
        ldy     #$1B
        lda     (secp),y
        bne     @bad
        dey
:       lda     (secp),y
        sta     base-$18,y
        dey
        cpy     #$17
        bne     :-
        clc
@rts:   rts
@bad:   lda     #E_READ
        sec
        rts

        .segment "HICODE"
; spare, secp (the block buffer), tsp, pp for the free page.
setspare:
        lda     t1_front
        eor     #$60
        sta     spare
        sta     openp+4                 ; I/O buffer
        clc
        adc     #4
        sta     secp+1
        sta     readp+3
        sta     rblkp+3
        adc     #2
        sta     tsp+1
        adc     #1
        sta     pp+1
        lda     #0
        sta     secp
        sta     tsp
        sta     pp
        sta     readp+2
        sta     rblkp+2
        rts

; -- t1_mload, t1_load -------------------------------------------------------------
; The movie: t1_name = its name, then its data.
t1_mload:
        jsr     setspare
        jsr     setname
        lda     mode
        cmp     #M_FILES
        bne     :+
        jsr     cmdpath
        jmp     rdprodos
:       lda     mt
        sta     ft
        lda     ms
        sta     fs
        jsr     iopen
        bcs     :+
        jsr     rdfile
        jmp     iclose
:       rts

; t1_name = the movie's name.
setname:
        ldx     #23
:       lda     mvname,x
        sta     t1_name,x
        dex
        bpl     :-
        clc
        rts

; The command as the path (pp).
cmdpath:
        ldy     cmd
:       lda     cmd,y
        sta     (pp),y
        dey
        bpl     :-
        rts

t1_load:
        jsr     setspare
        lda     mode
        cmp     #M_FILES
        bne     @dos
        jsr     namepath
        jmp     rdprodos
@dos:   jsr     iopen
        bcs     @rts
        jsr     find
        bcs     :+
        jsr     rdfile
:       jmp     iclose
@rts:   rts

; Opens the image (M_IMAGE only): C = 1, A = the error.
iopen:  lda     mode
        bne     @ok
        lda     dlen                    ; the path: cmd up to the comma
        sta     t0dos
        ldy     #0
        sta     (pp),y
:       iny
        lda     cmd,y
        sta     (pp),y
        cpy     t0dos
        bne     :-
        jsr     popen
        bcs     @no
@ok:    clc
        rts
@no:    rts

; Closes the image (M_IMAGE), keeping C and A; a failed close is a read
; error.
iclose: php
        pha
        lda     mode
        bne     @kept
        jsr     pclose
        bcc     @kept
        pla
        plp
        lda     #E_READ
        sec
        rts
@kept:  pla
        plp
        rts

; -- the catalog ----------------------------------------------------------------
; Finds t1_name: ft, fs = its first T/S list. C = 1: A = the error.
find:   lda     #0
        sta     cnt
        sta     cnt+1
        ldx     #17                     ; the VTOC
        ldy     #0
        jsr     rdsecc
        bcs     @rts
        ldy     #1
        lda     (secp),y
        sta     ft
        iny
        lda     (secp),y
        sta     fs
        lda     #0                      ; (the catalog's sectors are counted)
        sta     cnt
        sta     cnt+1
@sec:   lda     ft
        beq     @none
        ldx     ft
        ldy     fs
        jsr     rdsecc
        bcs     @rts
        lda     #11                     ; seven entries of 35 bytes
        sta     pidx
@ent:   ldy     pidx
        lda     (secp),y
        beq     @none                   ; never used: the end
        cmp     #$FF
        beq     @next                   ; deleted
        jsr     samename
        bne     @next
        ldy     pidx
        lda     (secp),y
        sta     ft
        iny
        lda     (secp),y
        sta     fs
        clc
@rts:   rts
@next:  lda     pidx
        clc
        adc     #35
        sta     pidx
        bcc     @ent                    ; (11 + 7 * 35 = 256)
        ldy     #1
        lda     (secp),y
        sta     ft
        iny
        lda     (secp),y
        sta     fs
        jmp     @sec
@none:  lda     #E_NOTFOUND
        sec
        rts

; Z = 1 if the entry at pidx is named t1_name (30 characters from +3, low
; 7 bits, trailing spaces removed).
samename:
        lda     pidx
        clc
        adc     #3 + 29
        tay
        ldx     #30
:       lda     (secp),y
        and     #$7F
        cmp     #' '
        bne     :+
        dey
        dex
        bne     :-
:       cpx     t1_name
        bne     @no
        txa
        beq     @yes
:       lda     (secp),y
        and     #$7F
        cmp     t1_name,x
        bne     @no
        dey
        dex
        bne     :-
@yes:   lda     #0
        rts
@no:    lda     #1
        rts

; -- a file's sectors -------------------------------------------------------------
; Reads the binary file whose first T/S list is ft, fs into t1_dest, its
; length (header bytes 2, 3) at most t1_max: t1_len. C = 1: A = the error.
rdfile: lda     #0
        sta     cnt
        sta     cnt+1
        sta     hcnt
        sta     got
        sta     got+1
        sta     done
        lda     t1_dest
        sta     op
        lda     t1_dest+1
        sta     op+1
@list:  ldx     ft
        ldy     fs
        jsr     rdsecc
        bcs     @rts
        ldy     #0                      ; the list, kept
:       lda     (secp),y
        sta     (tsp),y
        iny
        bne     :-
        lda     #12
        sta     pidx
@pair:  ldy     pidx
        lda     (tsp),y
        tax
        iny
        lda     (tsp),y
        tay
        bne     @sec
        txa
        bne     @sec
        ldy     #0                      ; a hole: zeros
        tya
:       sta     (secp),y
        iny
        bne     :-
        beq     @take                   ; (always)
@sec:   jsr     rdsecc
        bcs     @rts
@take:  jsr     take
        bcs     @rts
        lda     done
        bne     @end
        inc     pidx
        inc     pidx
        bne     @pair
        ldy     #1                      ; the next list
        lda     (tsp),y
        sta     ft
        iny
        lda     (tsp),y
        sta     fs
        ora     ft
        bne     @list
        lda     #E_READ                 ; the file runs short
        sec
@rts:   rts
@end:   lda     need
        sta     t1_len
        lda     need+1
        sta     t1_len+1
        clc
        rts

; Takes the 256 bytes at secp: the header first, then the data, until the
; file's length (done). C = 1: A = E_BIG.
take:   ldy     #0
@b:     lda     hcnt
        cmp     #4
        bcs     @data
        tax
        lda     (secp),y
        sta     hdr,x
        inc     hcnt
        cpx     #3
        bne     @next
        lda     hdr+2                   ; the length: within t1_max
        sta     need
        lda     hdr+3
        sta     need+1
        lda     t1_max
        cmp     need
        lda     t1_max+1
        sbc     need+1
        bcc     @big
        lda     need
        ora     need+1
        bne     @next
        beq     @full                   ; (an empty file)
@data:  lda     (secp),y
        sty     t0dos
        ldy     #0
        sta     (op),y
        ldy     t0dos
        inc     op
        bne     :+
        inc     op+1
:       inc     got
        bne     :+
        inc     got+1
:       lda     got
        cmp     need
        bne     @next
        lda     got+1
        cmp     need+1
        beq     @full
@next:  iny
        bne     @b
        clc
        rts
@full:  inc     done
        clc
        rts
@big:   lda     #E_BIG
        sec
        rts

; rdsec, counted: more than MAXSEC sectors in a chain is damaged.
rdsecc: inc     cnt
        bne     :+
        inc     cnt+1
:       lda     cnt+1
        cmp     #>(MAXSEC + 1)
        bcc     rdsec
        bne     :+
        lda     cnt
        cmp     #<(MAXSEC + 1)
        bcc     rdsec
:       lda     #E_READ
        sec
        rts

; Sector (X, Y) to secp. C = 1: A = E_READ. T < 35 and S < 16 on both
; paths: in an image, track 35 would be the .2MG's trailer or bytes past
; the 140K, read as data.
rdsec:  cpy     #16
        bcs     @bad0
        cpx     #35
        bcs     @bad0
        lda     mode
        bne     @unit
        txa                             ; mark = base + 4096 T + 256 S
        lsr
        lsr
        lsr
        lsr
        sta     t0dos                   ; T >> 4
        txa
        asl
        asl
        asl
        asl
        sta     markp+3
        tya
        ora     markp+3                 ; (T << 4 | S) & $FF
        clc
        adc     base+1
        sta     markp+3
        lda     t0dos
        adc     base+2
        sta     markp+4
        lda     base
        sta     markp+2
        jsr     setmark
        bcs     @rts
        lda     #0
        jsr     rdblk                   ; 256 bytes
        bcs     @rts
        lda     #0
        sta     secp
        rts
@bad0:  jmp     @bad
@unit:  lda     htab,y                  ; block 8 T + (H >> 1), half H & 1
        sta     t0dos
        lsr
        sta     rblkp+4
        lda     #0
        sta     rblkp+5
        txa
        asl
        rol     rblkp+5
        asl
        rol     rblkp+5
        asl
        rol     rblkp+5
        ora     rblkp+4
        sta     rblkp+4
        lda     unit
        sta     rblkp+1
        jsr     MLI
        .byte   $80                     ; READ_BLOCK
        .word   rblkp
        bcs     @bad
        lda     t0dos
        and     #1
        clc
        adc     spare
        adc     #4
        sta     secp+1
        lda     #0
        sta     secp
        clc
        rts
@bad:   lda     #E_READ
        sec
@rts:   rts

; SET_MARK markp.
setmark:
        lda     openp+5
        sta     markp+1
        jsr     MLI
        .byte   $CE
        .word   markp
        bcs     ioerr
        rts

; READ A bytes (0: 256) to the block buffer; exactly that many.
rdblk:  sta     readp+4
        ldx     #0
        cmp     #0
        bne     :+
        inx
:       stx     readp+5
        lda     openp+5
        sta     readp+1
        jsr     MLI
        .byte   $CA
        .word   readp
        bcs     ioerr
        lda     readp+6
        cmp     readp+4
        bne     ioerr
        lda     readp+7
        cmp     readp+5
        bne     ioerr
        clc
        rts
ioerr:  lda     #E_READ
        sec
        rts

; -- ProDOS files ---------------------------------------------------------------
; The path of t1_name: the directory, then the name A2 File Cmd gives it.
namepath:
        ldy     dlen
        beq     :++
:       lda     cmd,y
        sta     (pp),y
        dey
        bne     :-
:       ldx     #0                      ; first 15 characters, upper case,
        ldy     dlen                    ; letters and digits, '.' otherwise,
@c:     cpx     t1_name                 ; a letter first ('X')
        beq     @end
        cpx     #15
        beq     @end
        lda     t1_name+1,x
        and     #$7F
        cmp     #'a'
        bcc     :+
        cmp     #'z' + 1
        bcs     :+
        and     #$DF
:       cmp     #'A'
        bcc     :+
        cmp     #'Z' + 1
        bcc     @keep
:       cpx     #0
        bne     :+
        lda     #'X'
        bne     @keep                   ; (always)
:       cmp     #'0'
        bcc     :+
        cmp     #'9' + 1
        bcc     @keep
:       lda     #'.'
@keep:  iny
        sta     (pp),y
        inx
        bne     @c
@end:   txa
        bne     :+
        iny                             ; an empty name: "X"
        lda     #'X'
        sta     (pp),y
:       tya
        ldy     #0
        sta     (pp),y
        rts

; Reads the ProDOS file at pp into t1_dest, t1_max bytes at most: OPEN,
; READs of 256 bytes into the block buffer until the end of the file
; ($4C), CLOSE. C = 1: A = the error.
rdprodos:
        jsr     popen
        bcc     :+
        rts
:       lda     t1_dest
        sta     op
        lda     t1_dest+1
        sta     op+1
        lda     #0
        sta     got
        sta     got+1
@read:  lda     #0
        sta     readp+4
        lda     #1
        sta     readp+5
        lda     openp+5
        sta     readp+1
        jsr     MLI
        .byte   $CA
        .word   readp
        bcc     @some
        cmp     #$4C                    ; the end of the file
        beq     @end
        lda     #E_READ
        bne     @fail                   ; (always)
@some:  lda     readp+6                 ; got + count <= t1_max
        clc
        adc     got
        sta     got
        lda     readp+7
        adc     got+1
        sta     got+1
        lda     t1_max
        cmp     got
        lda     t1_max+1
        sbc     got+1
        bcs     :+
        lda     #E_BIG
        bne     @fail                   ; (always)
:       ldy     #0
        ldx     readp+6
        lda     readp+7
        bne     :+                      ; 256 bytes (X = 0)
        txa
        beq     @read                   ; (nothing: read on)
:       lda     (secp),y
        sta     (op),y
        iny
        dex
        bne     :-
        lda     readp+7
        beq     :+
        inc     op+1
        bne     @read                   ; (always)
:       tya
        clc
        adc     op
        sta     op
        bcc     @read
        inc     op+1
        bne     @read                   ; (always)
@end:   jsr     pclose
        bcs     @rerr
        lda     got
        sta     t1_len
        lda     got+1
        sta     t1_len+1
        clc
        rts
@fail:  pha
        jsr     pclose
        pla
        sec
        rts
@rerr:  lda     #E_READ
        sec
        rts

; OPEN the path at pp. C = 1: A = E_NOTFOUND (no such file, directory or
; volume, or a bad path) or E_READ.
popen:  lda     pp
        sta     openp+1
        lda     pp+1
        sta     openp+2
        jsr     MLI
        .byte   $C8
        .word   openp
        bcc     @rts
        cmp     #$40                    ; bad path
        beq     @nf
        cmp     #$44                    ; path, volume, file not found
        bcc     @rd
        cmp     #$47
        bcs     @rd
@nf:    lda     #E_NOTFOUND
        sec
        rts
@rd:    lda     #E_READ
        sec
@rts:   rts

; CLOSE our file. C = 1 on an error.
pclose: lda     openp+5
        sta     closep+1
        jsr     MLI
        .byte   $CC
        .word   closep
        rts

        .segment "HIDATA"
openp:  .byte   3
        .word   0               ; path
        .word   0               ; I/O buffer
        .byte   0               ; ref_num
readp:  .byte   4, 0
        .word   0, 0, 0
markp:  .byte   2, 0
        .byte   0, 0, 0
rblkp:  .byte   3, 0
        .word   0               ; buffer
        .word   0               ; block
closep: .byte   1, 0
hdr:    .res    4
t0dos:  .res    1
htab:   .byte   0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15
smagic: .byte   "2IMG"
s2mg:   .byte   $0E, $12, "MG"          ; ".2MG" & $DF
smovie: .byte   .strlen("THE MOVIE"), "THE MOVIE"
