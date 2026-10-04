; nrclip.s -- NRCLIP: the pages of a Newsroom clip-art disk, saved as
; hi-res pictures (see nrclip.c and docs/NEWSROOM-FORMAT.md).
;
; The disk is read by DOS 3.3 sector, three streams through one sector
; cache (the core's copy_buf, low half):
;   I  the index, track 34 sectors 0-1: "SSI CLIP", the page count at
;      $1B, the page names from $1C, each ended by $00;
;   T  the location table, track 34 sectors 6-15: for each page, its
;      pieces as (track, sector, offset), then $FF;
;   D  the pieces, track 0 sector 1 to track 33, track 17 sectors 0-1
;      skipped.
; A file image is read with fseek/fread (DOS order, after a 2IMG header
; for a .2MG); a real disk with READ_BLOCK on its ProDOS unit, the sector
; being one half of a block (src/a2fc.c, dos_read_sector).
;
; The index and the whole table are checked before anything is drawn or
; written (newsroom_ref.clip_index and clip_table). Then each page is
; drawn on hi-res page 1, its pieces' white dots added in table order
; (clip_page), and saved in the other panel's directory: exclusive CREATE,
; fopen "wb", one fwrite of the 8,192 bytes, the stream's error flag,
; fclose. A name taken is "already there"; a damaged page (clip_piece
; refuses one of its pieces) is counted and never gets a file; a failed
; write or close removes the file just created and stops; a read error
; stops; Escape stops between pages. Nothing else is written: no AUX, no
; disk but the new files.
;
; Memory (sdk/nrclip.cfg). The file is loaded at $1B00 and runs from
; three places:
;   $1B00-$1FFF  header, CODE, RODATA, DATA: in place;
;   $0C00-$0FFF  NRLOW and the BSS: copied there at entry. It is the
;                ProDOS buffer of a SECOND open file (iobuf-0800, see
;                src/a2fc.cfg MAPRAM), so this overlay never has two files
;                open: the image is closed before a page is saved, and
;                opened again for the next page;
;   $2000-       COLD: the entry and the checks, run in place before the
;                first page is drawn over them.
;
; Failures deep in the decoder unwind to the entry's stack level (errsp):
; a read error ends the run, a malformed piece ends the page, and nothing
; is pushed on the C stack at that moment (every service call has
; returned before its result is tested).
;
; Plain 6502 throughout: the 6502 edition assembles this file too.
; tools/test_nrclip.py runs all of it under sim65, on both processors.

        .macpack longbranch
        .export _plugin_entry
        .import pushax, pusha, pusha0, pusheax, jmpvec
        .import __NRLOW_LOAD__, __NRLOW_RUN__, __NRLOW_SIZE__
        .importzp ptr1, ptr2, tmp1, sreg

; The service table and the panel (checked by nrclip.c).
API_PANELS  = 2
API_ACTIVE  = 4
API_OFULL   = 8
API_CBUF    = 12
API_MLI     = 44
API_FOPEN   = 46
API_FREAD   = 48
API_FWRITE  = 50
API_FCLOSE  = 52
API_FSEEK   = 54
API_REMOVE  = 56
API_SPRINTF = 60
API_STRCPY  = 80
API_NOTE    = 92
PAN_FS      = 94
PAN_IMGLEN  = 95
PAN_KEY     = 96
PAN_SIZE    = 98
SEEK_SET    = 2
FS_DOS33    = 2
FERROR      = 4                         ; cc65's FILE: f_flags (+1), _FERROR

KBD         = $C000
STROBE      = $C010
INDEX       = 34*16                     ; track 34 sector 0, as t * 16 + s
TABLE       = 34*16+6
SKIPPED     = 17*16                     ; the VTOC and the notice: 17/0, 17/1

; The streams, X = 0 (I), 1 (T), 2 (D): sector t * 16 + s, offset.
SI = 0
ST = 1
SD = 2

        .segment "BSS"
pan:    .res    2                       ; the active panel
oth:    .res    2                       ; the other one
cbuf:   .res    2                       ; copy_buf
img:    .res    2                       ; the image's FILE*, 0 = closed
out:    .res    2                       ; the page's FILE*
base:   .res    4                       ; where track 0 starts in the image
ilen:   .res    1                       ; the image path's length, 0 = a drive
ctag:   .res    2                       ; the sector in the cache ($FFxx: none)
cs:     .res    2                       ; the sector being read
slo:    .res    3
shi:    .res    3
sof:    .res    3
blk:    .res    6                       ; READ_BLOCK: 3, unit, buffer, block
cnt:    .res    3                       ; saved, already there, damaged
npg:    .res    1                       ; pages left
emode:  .res    1                       ; 0 checking, 1 a page, 2 skipping it
errsp:  .res    1
pend:   .res    1                       ; the page's $FF is read
nloc:   .res    1
li:     .res    1
locs:   .res    48                      ; 16 pieces' (track, sector, offset)
hdr:    .res    4                       ; x2, x1, y2, y1 (read backwards)
X2 = hdr
X1 = hdr+1
Y2 = hdr+2
Y1 = hdr+3
h:      .res    1
nstr:   .res    1
lmask:  .res    1
mask:   .res    1
q:      .res    1
sh:     .res    1
row:    .res    1
rc:     .res    1
run:    .res    1                       ; copies left in a run
rv:     .res    1                       ; their value
lob:    .res    1
hib:    .res    1
nlen:   .res    1
nlast:  .res    1
name:   .res    16
pfx:    .res    2
nmp:    .res    2
llo:    .res    1
lhi:    .res    1

        .segment "DATA"
; The CREATE request, laid out as struct Create of file_create.h (the
; overlays' one CREATE): 7 parameters, the Pascal path (copy_buf + 256,
; filled in at entry), access $C3, BIN, aux $2000, a seedling, no date.
crt:    .byte   7
crtp:   .word   0
        .byte   $C3, $06
        .word   $2000
        .byte   1
        .word   0, 0

; ---------------------------------------------------------------------------
        .segment "COLD"

; void plugin_entry(const struct A2fcApi* api)
_plugin_entry:
        sta     fl1+1                   ; field reads the table from there
        stx     fl1+2
        sta     fl2+1
        stx     fl2+2
        lda     #<__NRLOW_LOAD__      ; NRLOW to $0C00
        sta     ptr1
        lda     #>__NRLOW_LOAD__
        sta     ptr1+1
        lda     #<__NRLOW_RUN__
        sta     ptr2
        lda     #>__NRLOW_RUN__
        sta     ptr2+1
        ldx     #>(__NRLOW_SIZE__+255)
        ldy     #0
lc1:    lda     (ptr1),y
        sta     (ptr2),y
        iny
        bne     lc1
        inc     ptr1+1
        inc     ptr2+1
        dex
        bne     lc1
        tsx
        stx     errsp
        lda     #0
        ldx     #7
zero:   sta     img,x                   ; img, out, base: 0
        dex
        bpl     zero
        sta     cnt
        sta     cnt+1
        sta     cnt+2
        sta     emode
        lda     #$FF
        sta     ctag+1
        lda     #3
        sta     blk
        ldy     #API_CBUF
        jsr     field
        sta     cbuf
        stx     cbuf+1
        sta     cbr+1                   ; the cache, read by get
        stx     cbr+2
        sta     hcd+1
        stx     hcd+2
        sta     blk+2
        stx     blk+3
        sta     crtp
        sta     hcs+1
        inx
        stx     hcs+2                   ; copy_buf + 256: the upper half
        stx     crtp+1                  ; and the Pascal path

        ; The two panels.
        ldy     #API_ACTIVE
        jsr     field
        sta     ptr1
        stx     ptr1+1
        ldy     #0
        lda     (ptr1),y
        sta     tmp1
        ldy     #API_PANELS
        jsr     field
        sta     pan
        stx     pan+1
        sta     oth
        stx     oth+1
        clc
        adc     #PAN_SIZE
        bcc     pn1
        inx
pn1:    ldy     tmp1
        beq     pn0
        sta     pan
        stx     pan+1
        jmp     pn2
pn0:    sta     oth
        stx     oth+1

        ; The other panel: a ProDOS directory (not the volume list).
pn2:    jsr     othp
        ldy     #PAN_FS
        lda     (ptr1),y
        bne     nodest
        tay
        lda     (ptr1),y
        bne     dosp
nodest: lda     #<m_dest
        ldx     #>m_dest
        jmp     plain

        ; The active panel: a DOS 3.3 disk, an image or a real drive.
dosp:   jsr     panp
        ldy     #PAN_FS
        lda     (ptr1),y
        cmp     #FS_DOS33
        bne     nodos
        iny                             ; PAN_IMGLEN
        lda     (ptr1),y
        sta     ilen
        bne     image
        iny                             ; PAN_KEY: the ProDOS unit
        lda     (ptr1),y
        sta     blk+1
        jmp     check

image:  jsr     openimg
        jeq     readerr
        jsr     panp                    ; ".2MG" at the end of the image path?
        ldy     ilen
        ldx     #3
isf:    dey
        lda     (ptr1),y
        cmp     s2mg,x
        bne     check
        dex
        bpl     isf
        ; The 2IMG header: DOS order (format 0), 143,360 bytes of data.
        lda     #64
        ldx     #0
        jsr     rdimg
        jne     readerr
        lda     cbuf
        sta     ptr1
        lda     cbuf+1
        sta     ptr1+1
        ldx     #11
ihd:    ldy     h2off,x
        lda     (ptr1),y
        cmp     h2val,x
        bne     nodos
        dex
        bpl     ihd
        ldy     #$18                    ; the data offset
        ldx     #0
iba:    lda     (ptr1),y
        sta     base,x
        iny
        inx
        cpx     #4
        bne     iba
        beq     check                   ; always
nodos:  lda     #<m_dos
        ldx     #>m_dos
        jmp     plain

        ; The index: "SSI CLIP", $00 (bit 7 ignored) ...
check:  jsr     rewind
        lda     #0
        sta     sof+SI
        sta     li
ck1:    ldx     #SI
        jsr     get
        and     #$7F
        ldy     li
        cmp     ssi,y
        beq     ck2
        lda     #<m_noidx
        ldx     #>m_noidx
        jmp     plain
ck2:    inc     li
        lda     li
        cmp     #9
        bne     ck1
        ; ... the page count at $1B, at least one page ...
        lda     #$1B
        sta     sof+SI
        ldx     #SI
        jsr     get
        sta     npg
        jeq     badidx
        ; ... each name ended by $00 before track 34 sector 2 ...
        sta     li
ck3:    ldx     #SI
        jsr     get
        bne     ck3
        dec     li
        bne     ck3
        ; ... and the table: every page ended by $FF, every piece on a
        ; data sector, before track 35.
        lda     npg
        sta     li
ck4:    ldx     #ST
        jsr     get
        cmp     #$FF
        beq     ck5
        sta     lob
        ldx     #ST
        jsr     get
        sta     hib
        ldx     #ST
        jsr     get
        lda     lob
        ldx     hib
        jsr     mklin
        bcc     ck4
        jmp     badidx
ck5:    dec     li
        bne     ck4
        jmp     pages                   ; never back: the page covers this

m_dest: .asciiz "Other panel: not a ProDOS directory."
m_dos:  .asciiz "Active panel: not a 140K DOS 3.3 disk."
m_noidx: .asciiz "No SSI CLIP index: not a Newsroom clip-art disk."
ssi:    .byte   "SSI CLIP", 0
s2mg:   .byte   ".2MG"
h2off:  .byte   0, 1, 2, 3, $0C, $0D, $0E, $0F, $1C, $1D, $1E, $1F
h2val:  .byte   "2IMG", 0, 0, 0, 0, $00, $30, $02, $00

; ---------------------------------------------------------------------------
        .segment "CODE"

; The pages: the names from $1C, the table from its start.
pages:  jsr     rewind
        lda     #$1C
        sta     sof+SI
        jsr     show

page:   lda     KBD                     ; Escape between two pages
        bpl     pg0
        sta     STROBE
        cmp     #$9B
        bne     pg0
        lda     #<m_esc
        ldx     #>m_esc
        jmp     fin

pg0:    lda     ilen                    ; the image, closed by the last save
        beq     pg1
        lda     img
        ora     img+1
        bne     pg1
        jsr     openimg
        jeq     readerr

        ; The file name, as the core names a DOS 3.3 file: trailing
        ; blanks cut (one character kept), 15 characters, letters and
        ; digits upper case, anything else '.', a letter first.
pg1:    lda     #0
        sta     emode                   ; a failure here: the index
        sta     nlen
        sta     nlast
        sta     name
nm1:    ldx     #SI
        jsr     get
        beq     nm4
        and     #$7F
        tax                             ; the character, for the blank test
        cmp     #'a'
        bcc     nm2
        cmp     #'z'+1
        bcs     nm2
        sbc     #31                     ; carry clear: - 32
nm2:    cmp     #'Z'+1
        bcs     nmdot
        cmp     #'A'
        bcs     nm3
        cmp     #'9'+1
        bcs     nmdot
        cmp     #'0'
        bcs     nm3
nmdot:  lda     #'.'
nm3:    ldy     nlen
        cpy     #15
        bcs     nm1b
        sta     name,y
nm1b:   cpx     #' '
        beq     nm1c
        iny
        sty     nlast                   ; up to 16: a blank later is cut
        dey
nm1c:   cpy     #15
        bcs     nm1
        inc     nlen
        bne     nm1                     ; always
nm4:    ldy     nlast
        bne     nm5
        iny                             ; one character at least
nm5:    cpy     #16
        bcc     nm6
        ldy     #15
nm6:    lda     #0
        sta     name,y
        lda     name
        cmp     #'A'
        bcc     nm7
        cmp     #'Z'+1
        bcc     draw
nm7:    lda     #'X'
        sta     name

        ; The page: black, then its pieces, 16 table entries at a time.
draw:   jsr     clear
        lda     #1
        sta     emode
        lda     #0
        sta     pend
chunk:  lda     #0
        sta     nloc
cl1:    ldx     #ST
        jsr     get
        cmp     #$FF
        bne     cl2
        inc     pend
        bne     pcs                     ; always
cl2:    ldy     nloc
        sta     locs,y
        ldx     #ST
        jsr     get
        ldy     nloc
        sta     locs+1,y
        ldx     #ST
        jsr     get
        ldy     nloc
        sta     locs+2,y
        iny
        iny
        iny
        sty     nloc
        cpy     #48
        bne     cl1
pcs:    lda     #0
        sta     li
pc1:    ldy     li
        cpy     nloc
        beq     pc2
        lda     locs+2,y
        sta     sof+SD
        ldx     locs+1,y
        lda     locs,y
        jsr     mklin
        jcs     damaged
        lda     llo
        sta     slo+SD
        lda     lhi
        sta     shi+SD
        jsr     piece
        lda     li
        clc
        adc     #3
        sta     li
        bne     pc1                     ; always (48 at most)
pc2:    lda     pend
        beq     chunk

        ; The page is whole. One file open at a time: the image first.
        jsr     closeimg
        jne     readerr
        ; Saved as other->path "/" name: the C path in other_full, the
        ; Pascal one in copy_buf + 256.
        jsr     othp
        jsr     ofull
        sta     ptr2
        stx     ptr2+1
        ldy     #0
sv1:    lda     (ptr1),y
        beq     sv2
        sta     (ptr2),y
        iny
        bne     sv1
sv2:    lda     #'/'
        ldx     #$FF
sv3:    sta     (ptr2),y
        iny
        inx
        lda     name,x
        bne     sv3
        sta     (ptr2),y
        lda     crtp
        sta     ptr1
        lda     crtp+1
        sta     ptr1+1
        tya
        ldy     #0
        sta     (ptr1),y
        tay
sv4:    dey
        lda     (ptr2),y
        iny
        sta     (ptr1),y
        dey
        bne     sv4
        lda     #$C0                    ; CREATE: exclusive, a taken name fails
        jsr     pusha
        lda     #<crt
        ldx     #>crt
        ldy     #API_MLI
        jsr     call
        cmp     #0
        beq     sv5
        cmp     #$47                    ; duplicate file name
        bne     sv9
        inc     cnt+1
        jmp     next
sv9:    lda     #<m_create
        ldx     #>m_create
        jmp     fin
sv5:    jsr     ofull                   ; ours now: fopen(path, "wb")
        jsr     pushax
        lda     #<wb
        ldx     #>wb
        ldy     #API_FOPEN
        jsr     call
        sta     out
        stx     out+1
        ora     out+1
        beq     wgone
        lda     #0                      ; fwrite($2000, 1, 8192, out)
        ldx     #$20
        jsr     pushax
        lda     #1
        ldx     #0
        jsr     pushax
        lda     #0
        ldx     #$20
        jsr     pushax
        lda     out
        ldx     out+1
        ldy     #API_FWRITE
        jsr     call
        cmp     #0
        bne     wbad
        cpx     #$20
        bne     wbad
        lda     out
        ldx     out+1
        jsr     ferror
        bne     wbad
        jsr     closeout
        bne     wgone
        inc     cnt
        jmp     next
wbad:   jsr     closeout                ; failing anyway: its result is moot
wgone:  jsr     ofull                   ; remove the file this run created
        ldy     #API_REMOVE
        jsr     call
        stx     tmp1
        ora     tmp1
        bne     wleft
        lda     #<m_write
        ldx     #>m_write
        jmp     fin
wleft:  lda     #<m_left
        ldx     #>m_left
        jmp     finn

; A malformed piece: the page is damaged, its table entries are skipped.
; In the checks, or if the table fails while being skipped, the index is.
damaged:
        ldx     errsp
        txs
        lda     emode
        cmp     #1
        bne     badidx
        inc     cnt+2
        inc     emode
        lda     pend
        bne     next
dm1:    ldx     #ST
        jsr     get
        cmp     #$FF
        beq     next
        ldx     #ST
        jsr     get
        ldx     #ST
        jsr     get
        jmp     dm1

next:   dec     npg
        jne     page
        lda     #<m_done
        ldx     #>m_done
        jmp     fin

badidx: lda     #<m_badidx
        ldx     #>m_badidx
        jmp     fin

readerr:
        lda     #<m_read
        ldx     #>m_read

; The end: api->note = prefix A/X then the counts (fin), or the file name,
; the prefix and the counts (finn). The image is closed first; a failed
; close is a read error when the run had nothing else to say.
fin:    ldy     #<empty
        sty     nmp
        ldy     #>empty
        bne     fn1                     ; always
finn:   ldy     #<name
        sty     nmp
        ldy     #>name
fn1:    sty     nmp+1
        jsr     unwind
        jsr     closeimg
        beq     fn2
        lda     pfx
        cmp     #<m_done
        bne     fn2
        lda     pfx+1
        cmp     #>m_done
        bne     fn2
        lda     #<m_read
        sta     pfx
        lda     #>m_read
        sta     pfx+1
fn2:    jsr     notep
        lda     #<fmt
        ldx     #>fmt
        jsr     pushax
        lda     nmp
        ldx     nmp+1
        jsr     pushax
        lda     pfx
        ldx     pfx+1
        jsr     pushax
        lda     cnt
        jsr     pusha0
        lda     cnt+1
        jsr     pusha0
        lda     cnt+2
        jsr     pusha0
        ldy     #API_SPRINTF
        jsr     field
        sta     jmpvec+1
        stx     jmpvec+2
        ldy     #14                     ; variadic: the bytes pushed
        jmp     jmpvec

; A precondition is missing: api->note = A/X, nothing done.
plain:  jsr     unwind
        jsr     closeimg
        jsr     notep
        lda     pfx
        ldx     pfx+1
        ldy     #API_STRCPY
        jmp     call

; pushax(api->note)
notep:  ldy     #API_NOTE
        jsr     field
        jmp     pushax

; pfx = A/X; back to the entry's stack level, returning to the caller.
unwind: sta     pfx
        stx     pfx+1
        pla
        tay
        pla
        ldx     errsp
        txs
        pha
        tya
        pha
        rts

; fclose(img) if it is open; Z clear if that failed. img is 0 after.
closeimg:
        lda     img
        ldx     img+1
        beq     ci1                     ; the image is never in page 0
        ldy     #0
        sty     img
        sty     img+1
        ldy     #API_FCLOSE
        jsr     call
        stx     tmp1
        ora     tmp1
ci1:    rts

ofull:  ldy     #API_OFULL
        ; fall through

; A/X = the word at offset Y of the table.
field:
fl1:    lda     $FFFF,y
        pha
        iny
fl2:    lda     $FFFF,y
        tax
        pla
        rts

; The service at offset Y of the table, A/X its last argument.
call:   pha
        txa
        pha
        jsr     field
        sta     jmpvec+1
        stx     jmpvec+2
        pla
        tax
        pla
        jmp     jmpvec

panp:   lda     pan
        ldx     pan+1
        bne     pp1                     ; always: the panels are not in page 0
othp:   lda     oth
        ldx     oth+1
pp1:    sta     ptr1
        stx     ptr1+1
        rts

; Full-screen hi-res page 1, forty columns, main bank, page cleared.
show:   lda     #0
        sta     $C000                   ; 80STORE off
        sta     $C002                   ; RAMRD main
        sta     $C004                   ; RAMWRT main
        sta     $C00C                   ; 40 columns
        sta     $C054                   ; PAGE2 off
        sta     $C057                   ; HIRES
        sta     $C052                   ; full screen
        jsr     clear
        sta     $C050                   ; graphics
        rts

        .segment "RODATA"
elo:    .byte   <(INDEX+2), <(TABLE+10), <INDEX
ehi:    .byte   >(INDEX+2), >(TABLE+10), >INDEX
thirds: .byte   0, 40, 80
masks:  .byte   $01, $03, $07, $0F, $1F, $3F, $7F
rb:     .asciiz "rb"
wb:     .asciiz "wb"
fmt:    .byte   "%s%s %u saved, %u already there, %u damaged."
empty:  .byte   0                       ; fmt's end, and the empty string
m_badidx: .asciiz "Clip-art index damaged:"
m_read: .asciiz "Read error:"
m_esc:  .asciiz "Stopped:"
m_done: .asciiz "Clip art:"
m_create: .asciiz "Create failed:"
m_write: .asciiz "Write failed, file removed:"
m_left: .asciiz " left incomplete!"

; ---------------------------------------------------------------------------
        .segment "NRLOW"

; fclose(out), Z clear if that failed.
closeout:
        lda     out
        ldx     out+1
        ldy     #API_FCLOSE
        jsr     call
        stx     tmp1
        ora     tmp1
        rts

; The image: its path is the first ilen characters of the active panel's,
; copied into other_full and opened. Z set on a failure.
openimg:
        jsr     ofull
        sta     ptr2
        stx     ptr2+1
        jsr     panp
        ldy     #0
oi1:    lda     (ptr1),y
        sta     (ptr2),y
        iny
        cpy     ilen
        bne     oi1
        lda     #0
        sta     (ptr2),y
        lda     ptr2
        ldx     ptr2+1
        jsr     pushax
        lda     #<rb
        ldx     #>rb
        ldy     #API_FOPEN
        jsr     call
        sta     img
        stx     img+1
        ora     img+1
        rts

; The streams I and T at the index and the table, offsets as they are.
rewind: lda     #<INDEX
        sta     slo+SI
        lda     #>INDEX
        sta     shi+SI
        sta     shi+ST
        lda     #<TABLE
        sta     slo+ST
        lda     #0
        sta     sof+ST
        rts

; Z set unless the error flag of the FILE* A/X is set.
ferror: sta     ptr1
        stx     ptr1+1
        ldy     #1
        lda     (ptr1),y
        and     #FERROR
        rts

; The next byte of a piece's bitmap: $00 n v is n copies of v (n, v not 0).
nsb:    lda     run
        beq     nb1
        dec     run
        lda     rv
        rts
nb1:    ldx     #SD
        jsr     get
        bne     nb2
        ldx     #SD
        jsr     get
        beq     pdmg
        sta     run
        ldx     #SD
        jsr     get
        beq     pdmg
        sta     rv
        dec     run
nb2:    rts
pdmg:   jmp     damaged

; A piece at the D stream: its header, then its strips of seven dots.
piece:  ldy     #3
ph1:    sty     rc
        ldx     #SD
        jsr     get
        ldy     rc
        sta     hdr,y
        dey
        bpl     ph1
        lda     Y2                      ; y1 <= y2 <= 191
        cmp     #192
        bcs     pdmg
        sec
        sbc     Y1
        bcc     pdmg
        adc     #0                      ; carry set: + 1
        sta     h
        lda     X2                      ; x1 <= x2 <= 251
        cmp     #252
        bcs     pdmg
        sec
        sbc     X1
        bcc     pdmg
        jsr     div7                    ; strips = (x2 - x1) div 7 + 1
        inx
        stx     nstr
        tax
        lda     masks,x                 ; the last strip's dots
        sta     lmask
        lda     X1                      ; dot x1 + 14 = byte q, bit sh
        jsr     div7
        sta     sh
        inx
        inx
        stx     q
        lda     #0
        sta     run
ps1:    lda     #$7F
        ldx     nstr
        dex
        bne     ps2
        lda     lmask
ps2:    sta     mask
        lda     Y1
        sta     row
        lda     h
        sta     rc
ps3:    jsr     nsb
        and     mask
        beq     ps5
        ldx     #0                      ; the seven dots shifted by sh,
        stx     hib                     ; over bytes q and q + 1
        ldy     sh
        beq     ps4
psl:    asl     a
        rol     hib
        dey
        bne     psl
ps4:    asl     a
        rol     hib
        lsr     a
        sta     lob
        lda     row
        jsr     hrow
        clc
        adc     q
        sta     ptr2
        txa
        adc     #0
        sta     ptr2+1
        ldy     #0
        lda     lob
        ora     (ptr2),y
        sta     (ptr2),y
        iny
        lda     hib
        ora     (ptr2),y
        sta     (ptr2),y
ps5:    inc     row
        dec     rc
        bne     ps3
        inc     q
        dec     nstr
        bne     ps1
        lda     run                     ; a run past the piece
        jne     damaged
        rts

; A = A mod 7, X = A div 7.
div7:   ldx     #0
dv1:    cmp     #7
        bcc     dv2
        sbc     #7
        inx
        bne     dv1                     ; always
dv2:    rts

; llo/lhi = track A * 16 + sector X, carry set unless a data sector:
; track 0-33, sector 0-15, not 0/0, 17/0, 17/1.
mklin:  cmp     #34
        bcs     ml9
        cpx     #16
        bcs     ml9
        stx     tmp1
        pha
        asl     a
        asl     a
        asl     a
        asl     a
        ora     tmp1
        sta     llo
        pla
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     lhi
        bne     ml1
        lda     llo
        beq     ml9
ml8:    clc
        rts
ml1:    cmp     #>SKIPPED
        bne     ml8
        lda     llo
        and     #$FE
        cmp     #<SKIPPED
        bne     ml8
ml9:    sec
        rts

; A = the next byte of stream X (Z set by it). Past the stream's end the
; piece or the index is malformed; X is kept.
get:    lda     slo,x
        cmp     elo,x
        lda     shi,x
        sbc     ehi,x
        jcs     damaged
        lda     slo,x
        cmp     ctag
        bne     gt1
        lda     shi,x
        cmp     ctag+1
        beq     gt2
gt1:    txa
        pha
        lda     slo,x
        ldy     shi,x
        jsr     readsec
        pla
        tax
gt2:    ldy     sof,x
cbr:    lda     $FFFF,y                 ; copy_buf
        pha
        inc     sof,x
        bne     gt3
        inc     slo,x                   ; the next sector
        bne     gt4
        inc     shi,x
gt4:    lda     slo,x
        cmp     #<SKIPPED
        bne     gt3
        lda     shi,x
        cmp     #>SKIPPED
        bne     gt3
        lda     #<(SKIPPED+2)
        sta     slo,x
gt3:    pla
        rts

; Sector A + 256 * Y (t * 16 + s) into copy_buf; a failure ends the run.
readsec:
        sta     cs
        sty     cs+1
        lda     #$FF
        sta     ctag+1
        lda     ilen
        beq     rblk
        lda     img                     ; fseek(img, base + 256 * cs, SEEK_SET)
        ldx     img+1
        jsr     pushax
        lda     cs
        clc
        adc     base+1
        tax
        lda     cs+1
        adc     base+2
        sta     sreg
        lda     #0
        adc     base+3
        sta     sreg+1
        lda     base
        jsr     pusheax
        lda     #SEEK_SET
        ldx     #0
        ldy     #API_FSEEK
        jsr     call
        stx     tmp1
        ora     tmp1
        bne     rderr
        lda     #0
        ldx     #1
        jsr     rdimg
        beq     rdok
rderr:  jmp     readerr
rblk:   lda     cs                      ; the half of block t * 8 + code / 2
        and     #15                     ; holding sector s: code = 15 - s
        beq     rb1                     ; but for sectors 0 and 15
        cmp     #15
        beq     rb1
        eor     #15
rb1:    sta     tmp1
        lda     cs+1
        lsr     a
        sta     blk+5
        lda     cs
        ror     a
        and     #$F8
        lsr     tmp1
        php                             ; carry: the upper half
        ora     tmp1
        sta     blk+4
        lda     #$80                    ; READ_BLOCK
        jsr     pusha
        lda     #<blk
        ldx     #>blk
        ldy     #API_MLI
        jsr     call
        plp
        tax
        bne     rderr
        bcc     rdok
        ldy     #0
hcs:    lda     $FFFF,y                 ; copy_buf + 256
hcd:    sta     $FFFF,y                 ; copy_buf
        iny
        bne     hcs
rdok:   lda     cs
        sta     ctag
        lda     cs+1
        sta     ctag+1
        rts

; fread(copy_buf, 1, A/X, img): Z set when all came and the stream's
; error flag is clear.
rdimg:  sta     lob
        stx     hib
        lda     cbuf
        ldx     cbuf+1
        jsr     pushax
        lda     #1
        ldx     #0
        jsr     pushax
        lda     lob
        ldx     hib
        jsr     pushax
        lda     img
        ldx     img+1
        ldy     #API_FREAD
        jsr     call
        cmp     lob
        bne     ri1
        cpx     hib
        bne     ri1
        lda     img
        ldx     img+1
        jmp     ferror
ri1:    rts

; Page 1 black.
clear:  lda     #0
        sta     ptr1
        tay
        ldx     #$20
cr1:    stx     ptr1+1
cr2:    sta     (ptr1),y
        iny
        bne     cr2
        inx
        cpx     #$40
        bne     cr1
        rts

; A/X = the address of hi-res row A (0-191) on page 1.
hrow:   pha
        and     #7
        asl     a
        asl     a
        ora     #$20
        sta     ptr1+1
        pla
        pha
        and     #$38
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        ora     ptr1+1
        sta     ptr1+1
        pla
        pha
        and     #8
        beq     hr1
        lda     #$80
hr1:    sta     ptr1
        pla
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        tax
        lda     thirds,x
        clc
        adc     ptr1
        ldx     ptr1+1
        rts
