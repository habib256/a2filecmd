; mini.inc -- shared layout for A2FC Mini DOS 3.3, pure 6502.
;
; Apple II+ 48 KB, NMOS 6502, DOS 3.3 resident. No language card, no
; auxiliary bank, no ProDOS, no overlays. Code and data live in
; $2000-$7FFF; DOS, its buffers and RWTS stay where DOS put them.
;
; Zero page: ONLY $80-$9F, saved on entry and restored on exit, because
; Applesoft keeps its pointers there and HELLO must survive the BRUN.
; RWTS and DOS own the rest of page zero; never borrow from it.

MINI_MAX        = 105           ; catalog entries kept per panel
SIDE_STRIDE     = MINI_MAX      ; per-panel stride in the entry arrays
NAME_LEN        = 30            ; DOS name characters kept per entry
NAME_STRIDE     = 32            ; power of two: index*32 needs no multiply
PANEL_ROWS      = 18            ; visible file rows per panel
SCREEN_CELLS    = 960           ; 24 rows of 40 columns, composed off-screen

; catalog() and preview() status, unchanged from the C edition.
CAT_OK          = 0
CAT_READ        = 1
CAT_BAD         = 2

; copy engine status, unchanged from the C edition: the UI maps these to
; messages and the host tests assert on these exact numbers.
COPY_OK         = 0
COPY_READ       = 1
COPY_INVALID    = 2
COPY_EXISTS     = 3
COPY_FULL       = 4
COPY_SAME       = 5
COPY_PROTECTED  = 6
COPY_CHANGED    = 7
COPY_UNCERTAIN  = 8
COPY_NOT_READY  = 9

; ---------------------------------------------------------------------
; Zero page. Scratch only: anything that must survive a call to another
; module lives in BSS instead.
; ---------------------------------------------------------------------
ptr             = $80           ; 2, general pointer
ptr2            = $82           ; 2, second pointer (compare/copy)
num             = $84           ; 2, 16-bit accumulator (numbers, offsets)
t0              = $86
t1              = $87
t2              = $88
t3              = $89
t4              = $8A
t5              = $8B
row             = $8C           ; screen cursor, as in the C edition
col             = $8D
inverse         = $8E
iob             = $8F           ; 2, RWTS IOB pointer
w0              = $91           ; 2, 16-bit scratch
w1              = $93           ; 2
w2              = $95           ; 2
t6              = $97
t7              = $98
bidx            = $99           ; allocation bitmap byte index
bmsk            = $9A           ; allocation bitmap bit mask
s0              = $9B           ; copy engine scratch, hot paths only
s1              = $9C
s2              = $9D
s3              = $9E
s4              = $9F
; The whole $80-$9F block is saved on entry and restored on exit.
ZP_FIRST        = $80
ZP_COUNT        = 32

; ---------------------------------------------------------------------
; Apple II+ hardware and DOS 3.3 entry points
; ---------------------------------------------------------------------
KBD             = $C000         ; key, bit 7 set when one is waiting
KBDSTROBE       = $C010
TXTCLR          = $C050
TXTSET          = $C051
MIXCLR          = $C052
MIXSET          = $C053
LOWSCR          = $C054
SCREEN          = $0400         ; 40-column text page 1
RWTS_ENTRY      = $03D9         ; DOS 3.3 RWTS, A/Y = IOB
RWTS_LOCATE_IOB = $03E3         ; returns Y = IOB low, A = IOB high
IOB_SLOT        = 1             ; slot * 16
IOB_DRIVE       = 2
IOB_VOLUME      = 3
IOB_TRACK       = 4
IOB_SECTOR      = 5
IOB_BUFFER      = 8             ; low, then high
IOB_COMMAND     = 12            ; 1 = read, 2 = write
IOB_RETURN      = 13
RWTS_READ       = 1
RWTS_WRITE      = 2
RWTS_PROTECTED  = $10           ; return code for write protection

; ---------------------------------------------------------------------
; DOS 3.3 on-disk layout
; ---------------------------------------------------------------------
CATALOG_TRACK   = 17
TS_PER_LIST     = 122           ; data pairs in one T/S list sector
CAT_ENTRIES     = 7             ; file entries per catalog sector
CAT_ENTRY_LEN   = 35
CAT_FIRST       = 11            ; first entry offset in a catalog sector
VTOC_BITMAP     = $38           ; four bytes per track, big-endian pair
MAX_DATA        = 491           ; data sectors one file may occupy here
MAX_LISTS       = 5             ; (491 + 121) / 122

; Sectors moved between the drives in one go. The copy engine reads a
; whole batch from one drive before touching the other, so a 48-sector
; file costs a dozen changes of drive instead of two hundred. 16 is one
; track's worth, which is also the unit DOS interleaves for.
BATCH_SECTORS   = 16

        .macpack        longbranch

; SETPTR ptr, label -- load a zero page pointer with a constant address
        .macro  SETPTR  p, addr
        lda     #<(addr)
        sta     p
        lda     #>(addr)
        sta     p+1
        .endmacro

; PRINT "text" -- the string travels inline after the call, which costs
; no address setup and no label at each of the many message sites.
        .macro  PRINT   str
        jsr     inline_text
        .byte   str, 0
        .endmacro

; KEYBAR row, "TAB Panel,RET Open" -- likewise for the bottom bars
        .macro  KEYBAR  yy, str
        lda     #yy
        jsr     keys_bar_inline
        .byte   str, 0
        .endmacro
