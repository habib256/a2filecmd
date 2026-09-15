; mini.inc -- shared layout for A2FC Mini DOS 3.3, pure 6502.
;
; Apple II+ 48 KB, NMOS 6502, DOS 3.3 resident. No language card, no
; auxiliary bank, no ProDOS, no overlays. BRUN loads at $1000 (editor
; and delete). The resident program lives in $4000-$95FF; hi-res page
; one is the shared working area; DOS, its buffers and RWTS stay where
; DOS put them.
;
; Zero page: ONLY $80-$9F, saved on entry and restored on exit, because
; Applesoft keeps its pointers there and HELLO must survive the BRUN.
; RWTS and DOS own the rest of page zero; never borrow from it.

MINI_MAX        = 105           ; catalog entries kept per panel
SIDE_STRIDE     = MINI_MAX      ; per-panel stride in the entry arrays
NAME_LEN        = 30            ; DOS name characters kept per entry
NAME_STRIDE     = 32            ; power of two: index*32 needs no multiply
ENT_CAT_TRACK   = NAME_LEN      ; the stride's two spare bytes say where the
ENT_CAT_SLOT    = NAME_LEN+1    ; entry was read: track, then sector<<3 | slot
PANEL_ROWS      = 19            ; visible file rows per panel
SCREEN_CELLS    = 960           ; 24 rows of 40 columns, composed off-screen
TAG_BYTES       = 14            ; 105 marks, one bit each, per panel

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

; delete() status. Locked files are refused before any write.
DEL_OK          = 0
DEL_READ        = 1
DEL_INVALID     = 2
DEL_LOCKED      = 3
DEL_CHANGED     = 4
DEL_UNCERTAIN   = 5
DEL_NOT_READY   = 6
REN_EXISTS      = 7             ; rename: the new name is already live
DEL_PROTECTED   = 8             ; RWTS refused before the first write
REN_SAME        = 9             ; rename: the disk already holds that name

; DOS 3.3 file type bits, lock aside.
TYPE_TEXT       = $00
TYPE_INTEGER    = $01
TYPE_APPLESOFT  = $02
TYPE_BINARY     = $04

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
CLR80STORE      = $C000         ; IIe write: 80STORE off so $400 is main
KBDSTROBE       = $C010
CLR80VID        = $C00C         ; IIe write: 40 columns; ignored on a II+
ALTCHAROFF      = $C00E
TXTCLR          = $C050
TXTSET          = $C051
MIXCLR          = $C052
MIXSET          = $C053
LOWSCR          = $C054
HISCR           = $C055
LORES           = $C056
HIRES           = $C057
SCREEN          = $0400         ; 40-column text page 1
RWTS_ENTRY      = $03D9         ; DOS 3.3 RWTS, A/Y = IOB
DOS_WARM        = $03D0         ; DOS 3.3 warm start: the prompt
COUT            = $FDED         ; character out, through DOS's hook
CURLIN_HI       = $76           ; Applesoft CURLIN high byte, $FF at the prompt
BRUN_PAGE       = $0300         ; B: the stub and its DOS command, run at exit
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

; ---------------------------------------------------------------------
; The 8 KB working area, and why it is where it is.
;
; Measured on the machine rather than assumed: Applesoft's HIMEM under
; this DOS is $9600, so free RAM ends at $95FF. Between $0800 and $95FF
; the only 8 KB blocks are the two hi-res pages, and $0800-$1FFF holds
; the Applesoft HELLO that BRUN came from and has to survive. So the
; program itself lives at $4000-$95FF and hi-res page one doubles as the
; one working area.
;
; Exactly one owner at a time, and the owners never overlap in time:
;   - the copy engine's sector batch,
;   - a hi-res picture being shown,
;   - the text editor's buffer.
; Nothing here is cleared at startup and nothing may be expected to
; survive a return to the panels.
SCRATCH         = $2000
SCRATCH_SIZE    = $2000

; Sectors moved between the drives in one go. The copy engine reads a
; whole batch from one drive before touching the other, so a 48-sector
; file costs a handful of changes of drive instead of two hundred. A
; batch is the whole working area: 32 sectors, two tracks' worth.
BATCH_SECTORS   = SCRATCH_SIZE / 256

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
