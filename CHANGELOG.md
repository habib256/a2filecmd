# Changelog

Changes in upcoming and published releases. See the [README](README.md) for features,
downloads and installation.

## [Unreleased]

No new format. Two bug hunts of the whole program, nine then six
reviewers, and their corrections; the demonstration folder tidied; the
documentation brought back in line with the code.

## Unreleased in detail

### Fixed: data safety

- REPAIR no longer takes a damaged pointer's word. A subdirectory key that
  named a file's index block was walked as a directory, "repaired", and the
  real directory freed; a volume-directory link into a free block had its
  back-pointer written there and every entry past it freed (295 blocks); an
  entry whose storage nibble read as deleted had its count lowered and its
  blocks freed -- all three ended with `rescan clean: repaired.` REPAIR now
  enters a block as a directory only on evidence (header `$E/39/13`, a
  matching back-pointer, the volume directory at blocks 2 to bitmap-1),
  gives lost blocks back only when nothing else is wrong with the tree and
  no file block is marked free, and otherwise writes nothing: `Lost blocks
  may hold a damaged file: nothing written. See FIXIT.` Fourteen sibling
  shapes (moved keys, zeroed index blocks, changed storage types, cut links,
  fork keys) follow the same rules; 20,000 fuzz cases hold the new invariant
  "no block the healthy volume owned is freed". A wrong back-pointer inside a
  subdirectory, and a bitmap with both lost and wrongly-free blocks, are now
  refused instead of rebuilt (`docs/FIXIT.md` section 5).
- FIXIT and `tools/prodos_check.py` no longer report `ENT_ACCESS` for the
  GS/OS "invisible" bit (bit 2): bits 4 and 3 only.
- IMGPUT no longer trusts the image's bitmap: before any block is chosen,
  every block the image's directories and files name must be marked used
  (`src/plugins/prodos_claims.h` walks chains, key, index and master blocks,
  both forks of extended files, and refuses loops, bad pointers, unknown
  storage types, unreadable blocks and a depth over 16). An image that fails
  gets nothing written: `Image damaged: nothing written. Run FIXIT.` Before, a
  referenced data block marked free was given to the new file, and the key
  block of the directory being added to, marked free, was overwritten.
- IMGPUT reads and counts the source before its question; the entry's length
  is what the file holds, not the panel's size (a stale size gave an EOF of
  0, 600 or 1,000 for 512, 1,024 or 900 real bytes). Blocks are chosen after
  the question from the bitmap as it then reads; a bit already clear is
  refused; the destination key must read as the head of a live directory (an
  entry used to be planted inside a file's data block).
- IMGPUT, PASCALW, CPMW and BLKEDIT refuse a .2MG whose header flags say
  write protected (bit 31). PASCALW's room test `tail + blocks > vblocks`
  wrapped at 16 bits on the machine; it is `blocks <= vblocks - tail`.
- BLKEDIT, BOOTBLK and WIPE no longer write to a disk swapped in after it
  was chosen. BLKEDIT signs block 2 at open and again after ERASE and keeps
  the edit until the right disk is back; BOOTBLK checks the volume names on
  the disks before its question and compares block 2 of target and source
  byte for byte after it; WIPE keeps block 2 as read before the question,
  requires the name the question shows, reads it again after the answer and,
  for F, once more right before the first write. A difference or a read
  error writes nothing: `Disk changed or unreadable: /NAME. Nothing
  written.` Measured before: W with another disk at the ERASE prompt zeroed
  all 280 blocks of that disk. Not covered: a disk whose block 2 is
  byte-identical, and a swap once the writes have begun.
- Tags no longer come back on other files. A tag is a bit by entry index,
  set aside while a big overlay covers the entry tables and given back
  afterwards -- unconditionally until now: after MOVE dropped a file into
  the other panel, GOTO or FIND changed the directory, an extraction or the
  editor created a file, or Left/Right in a viewer crossed the 139-entry
  window of a large folder, the old bits marked other files, and D asks for
  tagged files by their number. A panel gets its tags back only when it
  shows the same names and types at the same indexes under the same path (a
  16-bit fingerprint, made non-linear by the second hunt: swapping two
  entries eight places apart, or "AB" becoming "CA", passed the first one);
  otherwise it comes back untagged.
- V or C on a directory no longer writes into the source tree. Only a target
  inside the source was refused; with the directory A of /V/A moved to /V,
  the subdirectory /V/A/A/A was copied into /V/A/A -- the source -- and the
  move then deleted what it had just copied there. A directory is refused
  both ways, into itself and onto one of its own ancestors.
- D no longer leaves a tree half deleted. The count before a delete checked
  the paths of directories only; a file whose path does not fit stopped the
  delete after the entries before it were gone. The count checks every
  file's path and the tree is refused whole, before anything is erased.
- Ctrl-Reset from inside a viewer that writes the auxiliary bank (DHGR
  pictures, ARLEQUIN, EXTASIE, PACKFOT, MACPAINT, PURPLE, UNSHRINK...) now
  rebuilds /RAM empty on the way out, as a normal return does. It used to
  quit with /RAM on line, its directory intact over overwritten blocks.
- VDrive no longer takes over the slot of a SmartPort or ProFile unit: it
  compared whole DEVLST bytes, and only a Disk II has a low nibble of 0.
- UNSHRINK and UNSQ refuse a record typed $0F with a data thread: it created
  a plain file every panel takes for a folder. UNSHRINK says what it leaves
  out: `N file(s) extracted, M part(s) skipped.` for a resource fork, an
  unsupported compression or a type ProDOS cannot hold, where a resource
  fork was dropped silently and one unsupported member replaced the count.
- SCIIBIN makes the name in a BinSCII header a legal ProDOS name (it joined
  `SUB/EVIL` to the destination and wrote into the subfolder). A last line
  padded with non-zero bytes no longer makes the read-back remove a good
  file.
- DOCVIEW: a `_DB` or `_EN` inside a block no longer recurses (130 of them
  wrapped the processor stack: wild execution); a decimal tab beyond the
  right margin no longer hangs, and nothing is written past row 21 any more
  (a long field or footer went into the screen holes where the slot firmware
  keeps its state); an exponent past 1E38 is refused instead of a wrong
  number; `%$` page numbers go to 255 (100 read `:0`, 128 forced a break).
- VISICALC: Escape stops the reading and the recalculation (`Stopped.`,
  /RAM rebuilt if used); a worksheet of nested `@NPV` ranges took an hour
  and a half at 1 MHz with no way out. `Sheet too big` says `over 255
  values in one column` for repeated cells, and names the auxiliary bank's
  room when that is what did not suffice.
- TAKE1.SYSTEM: a T/S pair past track 34 in a .DSK/.2MG movie is a read
  error, no longer bytes of the 2MG trailer decoded as data.
- Mini: B refuses a name DOS could not read back from a typed line -- a
  comma, or a raw catalog byte below $A0 or equal to $FF: a FLASH or
  inverse name could run another file of the same visible name. Lower-case
  names ($E0-$FE) still run.

### Fixed: data safety, the second hunt

- A key typed during a long phase (VISICALC's read, IMGPUT's walk) no
  longer answers the next question: every row-22 question clears the
  keyboard strobe first. A Y typed ahead answered the /RAM question before
  it was shown and /RAM was rebuilt empty.
- A2FILE.CFG and GOTO paths are upshifted and lose a trailing slash:
  "/workhd/dir" and "/WORKHD/DIR" in the two panels let V move a file onto
  itself and then delete the only copy. V now says "Both panels show the
  same directory."
- Two volumes of one name on line: WIPE W on the panel showing a floppy
  /TWIN zeroed the 1600-block /TWIN of the other drive. WIPE, BOOTBLK,
  BLKEDIT, RESCUE, VOLINFO, FIXIT and REPAIR refuse a path whose volume name
  two drives carry ("Two volumes named /X: pick it in the volume list."),
  BLKVIEW and UNDELETE refuse it too, MOVE copies through ProDOS instead of
  moving entries. ON_LINE tables end at their zero byte.
- FORMAT rebuilds /RAM and finds the volume it runs from over the whole
  device list, not the nine units it shows (with eleven units and /RAM last,
  a Disk II format left /RAM's old directory over overwritten blocks); tells
  two DOS 3.3 or CP/M floppies apart by their catalog tracks before the
  first write; tests the write protection before borrowing the auxiliary
  bank; reads all 280 blocks back; refuses a name already on line.
- NIBCOPY names the target's volume in its confirmation, refuses the
  volume A2 File Cmd runs from, and stops before writing to a target that
  no longer holds the track it has just verified.
- REPAIR lists the lost blocks it would give back and asks a second word,
  FREE, before FIX: a file pointer moved onto an already-lost block looks
  exactly like an interrupted delete. FIXIT and REPAIR take the /RAM
  consent through the core (no question when /RAM is empty; Ctrl-Reset
  mid-scan rebuilds /RAM, seen on POM2). Lost blocks beside blocks in use
  marked free say to copy the files off and write nothing.
- The editor refuses a file longer than its stale panel size instead of
  truncating it to 5,104 bytes on save. A directory copy is counted against
  the destination paths too. The one-drive DISKIMG copy refuses the source
  at the first TARGET prompt instead of writing its mark there. Output
  reservation is a single CREATE: a failed OPEN no longer leaves an empty
  A2FC.COPY that blocks every later copy.
- IMGPUT no longer honours Escape between the bitmap and the entry, refuses
  a file pointing at the directory it writes, says "Image changed" for a
  directory deleted since the panel read it, and checks an index block a
  bitmap page at a time (11.4 to 4.2 million cycles on a scattered sapling).
- The Mini keeps an unsaved text after a failed or declined save and goes
  back to the editor; its second half used to be overwritten by the catalog.
- BLKEDIT's disk identity is the CRC-32 of block 2 (running sums missed
  swapped bytes); a 1- or 2-block image is identified by its block 0.

### Fixed, the second hunt

- DOCVIEW froze on an `_` that is no command inside a header or footer
  block (since 0.9.5); a block is skipped to its `__XX` and its commands no
  longer change the body.
- VDrive's receive loop ran at 100 cycles a byte, more than the 88.6 a byte
  takes at 115,200 bps: a real serial port overran and VDrive could not
  mount. It runs from page 3 at 33 cycles a byte; late replies are drained;
  the serial port is set up only once a slot is free ("VDrive: no free
  slot." when none is). Not yet tried on real hardware.
- Tags survive leaving an album's first window of a large folder and
  coming back; E on a new file no longer clears the other panel's tags.
- VISICALC says "Close error." when CLOSE fails; UNSQ counts past 255;
  MDVIEW, INTBASIC, AWDATA and the text viewers read again after a read
  error; BINARY2 skips phantom and squeezed records; the `!` menu describes
  the media overlays; a Fantavision backdrop must be 8,192 or 8,184 bytes;
  TREE counts forked files; VOLINFO's F and E leave the audit's figures
  alone; plugins' key waits ignore mouse clicks.

### Fixed

- A folder of more than 139 entries inside a disk image: Down past the last
  entry reread the same entries under a rising `139+`, `278+` header. An
  image folder shows its first 139 entries and is not paged.
- FIND said "complete" after a directory block it could not read; it says
  "some paths skipped". MDVIEW, INTBASIC and AWDATA show a read error as
  such, no longer as the end of the file; the text viewers (T, the BASIC
  lister, the AppleWorks reader) show `(READ ERROR)` and, at their eightieth
  page, `(page limit)`. INTBASIC pages a listing of any length (it stopped
  at page 40).
- `make BOTH_EDITIONS=1 disk` no longer recurses forever.

### DEMO, tidied

- One file per format: HGR.RAW (the album shows raw pages), DHGR.RLE,
  PACKFOT.D, the hi-res 816/Paint twin and TINY.2MG left the folder.
- PICTURES/CARDS holds the two colour cards in every picture format, the
  name being the format; elsewhere a name says what the file is, then its
  format: LETTRE.EPISTOLE, NOTE.PAPYRUS, HOUSE.GMAGIC, APPLE.PRINTSHOP,
  HELLO.BA3, PURPLE.FOTO1/2, MOVIEMAKER.SHP.
- A file for the 0.9.5 formats that had none, all generated:
  MEMO.BANKSTREET, FLOWER.LOGO and FLOWER.PICT (Terrapin Logo),
  PICTR.BALLOON (KoalaPad), ITALIC.FONT (Beagle Bros), WIDE.SCREEN (80
  columns, MouseText), BN.DEMO.NEWS, DISKS/CLIPART.DSK for NRCLIP, and
  MOVIES/TAKE1.DSK, a Take 1 movie on its DOS 3.3 disk.

### Documentation

- Three passes over every document against the code: the manual (87
  overlays, 80 text pages, the archive suffixes Return opens, MOVE's marked
  directories, BLKEDIT, PASCALW, CPMW, DISKCMP, the Mini's F key), the help
  page (Q, F says ERASE), DATA-SAFETY (the copy through A2FC.COPY, every
  write path named), FILE-SERVICES (who uses which helper), MEMORY-BUDGETS
  (one current table of every reserve, the ceilings explained), FIXIT, the
  SDK (`dir_close` hands back the directory-error flag; 51-character menu
  line; every overlay and window listed), the format specifications, CREDITS
  (the system software on the disks, NufxLib behind UNSHRINK, Fantavision),
  the roadmap.

### Room

- MAIN 65C02/6502: 12/392 bytes free (11/420 in 0.9.5), LC 21/19.
  REPAIR 77/13, FIXIT 276/243, IMGPUT 28/75, WIPE 50/79, DOCVIEW 42/41,
  DISKIMG 51/4, VISICALC's fixed part 156/153 (65C02/6502); the Mini 3
  bytes under DOS. docs/MEMORY-BUDGETS.md has the full table.

## [0.9.5] - 2026-10-04

New formats with a viewer:

- VisiCalc worksheets, recalculated as VisiCalc shows them
- The Graphics Magician pictures (Penguin Software)
- Take 1 movies (Baudville)
- Fantavision movies (Broderbund)
- The Newsroom photos, banners and clip-art disks (Springboard)
- Movie Maker backgrounds and shape sheets
- Epistole, Papyrus and HomeWord documents, with Epistole's calculations
- Bank Street Writer documents
- Saved text screens, 40 and 80 columns
- HRCG fonts (DOS Tool Kit `.SET`, Beagle Bros `.FONT`)
- Terrapin Logo procedures and pictures
- KoalaPad / Micro-Illustrator pictures

## 0.9.5 in detail

### Fixed
- FANTA.SYSTEM at the original speed: a frame the original player takes
  65,536 cycles or more longer to draw (large solids) froze the movie for
  about 16 seconds, keys unread. The wait was clipped whenever byte 2 of
  its 32-bit length was set, not only byte 3. `tools/test_fanta_wait.py`
  runs the routine from `fanta.s` under sim65 and counts its cycles.
  FANTA.SYSTEM: 34 bytes free under `$BF00`.
- DOCVIEW: a margin moved in the middle of a row (`_MG`, `_MI`) followed
  by a word that wraps copied that word to the new left edge whole, past
  the 80-byte row buffers, and printed a row of up to 147 characters over
  the lines below it. The row is now cut where it is full in that case.
  Screen only: nothing is written. `tools/test_docview.py` covers it.
- FANTA.SYSTEM: a backdrop found by the start of its name (M.CHECKER,
  CHECKERBOARD) in a directory deep enough made a path over 64 characters,
  written past its buffer; it is now not used. Out of reach from A2 File
  Cmd (46-character commands), not from another launcher. And the way on
  now asserts at link time that FANTA.SYSTEM's own reading ends below the
  command it keeps (`cmdbuf`). `tools/test_fantavision.py` covers the path.

### Epistole's calculations, headers and footers
- DOCVIEW computes Epistole's fields as Epistole prints them (checked
  against its own print output, captured under POM2): `#:X=…]` sets a
  variable, never set it is 0; `#:?…]` shows the value with `_ND` decimals
  (2 by default), a decimal comma, BASIC's exponent kept (`1E+10,00`), no
  minus sign when there are decimals; `_TDn` is a decimal tab, the comma at
  column n and in force on the lines that follow. `+ - * / ^`, comparisons,
  parentheses, SIN COS TAN ATN LOG EXP SGN ABS SQR INT, `1,5E2`.
- The arithmetic is the Applesoft ROM's, called with the language card off,
  the zero page $50-$FF saved around it; its errors (division by zero,
  overflow, LOG of a negative number) are caught by ONERR through CHRGOT
  and leave the field as written, in inverse -- they would have left for
  BASIC. `#*X=]`, typed at print time, prints nothing and leaves X
  unknown. The values at a page's top are replayed from the assignments
  before it.
- Headers `_EN…__EA` and footers `_DB…__BA` are no longer shown where they
  are written (one empty row each, as printed): the footer, `%$` its page
  number, ends each `_SP` page and the document, the header opens the
  next page. Letters with bit 7 set (underlined in print) show in inverse.
- A read error on a document says "(read error)", never "(end)"; a file
  over 64 KB is refused (the programs kept their documents in memory).
- cc65 2.19 dropped a structure member's offset in
  `((unsigned*)&p->size)[1]`: with it, the 65C02 edition refused every
  document as too long. Found by running the cc65-built DOCVIEW under sim65.
- DOCVIEW is now a larger overlay, code in `$1B00-$3D5F` and its scratch in
  `$3D60-$3FFF`; it remembers 16 pages back (was 64). Its evaluator is in
  assembly (`src/plugins/docview.s`).
- Tests: `tools/test_docview_calc.py` (the arithmetic and its trapped
  errors on a real Apple II ROM under sim65), `tools/test_docview_sim.py`
  (the cc65-built DOCVIEW under sim65: Epistole's demonstration documents
  line for line as it prints them), `tools/test_docview.py` (headers,
  footers, read errors), `bench/docview.py` 16/16 on both editions.

### The Newsroom photos and banners
- NEWSROOM shows The Newsroom's (Springboard, 1984) user pictures: photos
  `PH.*` and banners `BN.*`, DOS 3.3 B files at $4000 that become BIN $4000
  once copied to ProDOS. Return and I recognise them by name and type;
  Left/Right go to the neighbouring one. Centered on a black hi-res page,
  main bank only: `/RAM` is untouched and nothing is written.
- The format is documented in `docs/NEWSROOM-FORMAT.md`, a first: the
  bitmap is the last L bytes, since the clip history before it can hold
  $FF. Any failed check or I/O error refuses the file before it is shown.
- Tests: `tools/newsroom_ref.py` (reference), `tools/test_newsroom.py`
  runs the whole overlay under sim65 on both processors, including 125 real
  files when their disks are present. XL and 800K: 83 overlays.

### Movie Maker backgrounds and shape sheets
- IMAGE opens Movie Maker's (Interactive Picture Systems, 1984) shape
  sheets `.SHP`: BIN $1DF0 of 8,720 bytes, a 528-byte header then a hi-res
  page. Its backgrounds `.BKG` already opened as raw pages; both join the
  Left/Right album. Checked under POM2 on files from the original disks
  (`bench/moviemaker.py`). Films `.MVM` and animations `.ANI` are not read.

### Epistole, Papyrus and HomeWord documents
- DOCVIEW lays out the documents of three French and American word
  processors as they print: Epistole (Version Soft; ProDOS text with `_MG10`
  margin, `_CE` centring, `_IG` bold... commands and `#NOM]` mail-merge
  variables) and Papyrus (Ediciel), the French HomeWord (Sierra; DOS 3.3
  high-bit text with `$FF` codes). Margins, indents, tab stops, centring and
  page breaks are applied, bold and variables shown in inverse, printer-only
  commands hidden. Their ISO 646-FR accents (`{` for e acute...) show as
  plain letters on a US character set, as stored with A. Return opens it on
  a text that starts with a command or a code; the ! menu on any other.
- `tools/test_docview.py` renders synthetic documents and every document of
  the Epistole and Papyrus disks when present; `bench/docview.py` opens
  them by Return under POM2 on both editions. XL and 800K: 84 overlays.

### Room to recognise more formats
- OPEN, the overlay that decides which viewer a file opens in, had 4 bytes
  left on the 6502 after this release's formats. Its classifier is now
  written in assembly, with the same rules in the same order: 168/173
  bytes free (65C02/6502), room for several more formats. The former C is
  kept as the specification: `tools/test_file_viewers.py` runs the
  assembly under sim65 on both processors and requires the same answer on
  every expected route and 300 random cases, I/O failures included.

### Fantavision movies
- Return on a Fantavision movie (Broderbund, 1985: `M.*`, BIN $8400) plays
  it in FANTA.SYSTEM, a player of our own that A2FC launches with the
  movie's path and that brings A2FC back when it ends (800K and XL).
  Written in clean room from `docs/FANTAVISION-FORMAT.md` alone -- the
  format and the original player's behaviour as observed on 144 movies;
  none of Broderbund's code or tables is used. Its drawing is its own:
  within a few percent of the original's screen bytes, frame for frame.
- Two speeds, switched by Tab: accelerated (the default: about twice the
  original on dots and lines, 1.7-1.9x on solid shapes, simulated) and the
  original's, from a cycle model of the original player fitted on 6,787
  timed frames (median error 10 %). Space pauses, 1-9 add a delay, Escape
  returns. Main memory only: /RAM untouched, nothing written to disk.
- Backdrops: the hi-res picture marked in the movie's folder, or else the
  picture `NAME` beside `M.NAME` (as on Fantavision's own disks), is the
  background the movie plays on.
- A damaged tail is cut: all 144 real movies of the study play, three of
  them up to their damage. A movie with no whole first frame is refused
  with its reason.
- Tests: `tools/test_fantavision.py` runs the engine under sim65 on both
  processors against `tools/fantavision_ref.py` byte for byte, damaged
  movies included; `bench/fantavision.py` plays it on three machines under
  POM2; `bench/fanta_a2fc.py` goes from A2FC's Return to the movie and back.
- The original speed is now the default (Tab for the accelerated one).
  A movie always starts again: a counted one stays two seconds on its last
  frame, then plays from the start (with a backdrop, read again from the
  disk, since Background objects are drawn into it).
- S starts the slideshow: each movie plays once round and the next movie of
  its folder follows, in directory order, round and round until Escape.
  FANTA.SYSTEM relaunches itself with the next movie, the speed and the
  slideshow in its command; a movie refused on the way is shown three
  seconds, then skipped.
- Backdrops: a picture whose name begins with `NAME` is used for `M.NAME`
  when there is no `NAME` itself: `M.CHECKER` now plays on `CHECKERBOARD`.
- The movie's directory is read once, as the movie is loaded; anything but
  its clean end (an error, a short block, a malformed header) and it is
  not used. `tools/test_fantavision.py` checks the scan, the relaunch
  command and the backdrop by prefix under sim65 with a fake MLI, errors
  included.

### The title page stays for the whole first loading
- A2FC's main() called videomode(), whose 80-column firmware call ($C300,
  a PR#3) cleared the launcher's title page as soon as A2FILE.CODE began:
  the configuration and the panels were read on a blank screen. It is now
  called only when 80 columns are not already on, so the page stays, with
  "Reading directory..." at the bottom, until the panels are drawn.
- It then stays about two seconds more: from a hard disk or an emulator the
  whole loading takes a blink. A key cuts it short and is not taken for a
  command. `tools/test_startup_screen.py` holds main() to it.
  MAIN 65C02/6502: 57/469 bytes free.

### DEMO: a file for every viewer
- The XL disk's `DEMO/` now holds at least one file for each viewer:
  Extasie, Arlequin, PackFOT (hi-res and double), 816/Paint (both),
  LZ4FH, Purplesoft, Movie Maker sheet, lo-res and double lo-res, Print
  Shop, Newsroom, two Fantavision movies in a new MOVIES folder (one on a
  backdrop), a PT3 module, Epistole and Papyrus documents, Markdown and
  Magic Window, Integer and Business BASIC programs, squeezed and ACU
  archives, Apple Pascal and CP/M disks, an MGTK font.
- All generated by `tools/mkdemo_viewers.py`: the pictures are the same
  colour cards in every format, so a wrong decoding shows at once;
  nothing is borrowed but two fonts drawn from CiderPress II's STANDARD:
  MGTK.FONT, STANDARD laid out the MGTK way, and BOLD.SET, STANDARD made
  bold.
- `tools/test_file_viewers.py` stages DEMO and requires that the real
  classifier (C reference, and `open.s` under sim65 on both processors)
  sends every viewer at least one file; `tools/test_demo_viewers.py` runs
  each new file through its viewer's own test harness and compares the
  screen with the card or the reference decoder.

### Mini DOS 3.3: Caps Lock as the DOS master says it
- The start screen (HELLO, then the Mini's own splash, at the same place)
  says `BE SURE CAPS LOCK IS DOWN` in inverse video, the words of Apple's
  DOS 3.3 System Master, instead of `CAPS LOCK ON IS NEEDED`.

### Slideshows in the picture viewers
- S in any picture viewer (IMAGE's HGR/DHGR album, DGRVIEW, EXTASIE,
  ARLEQUIN, MACPAINT, PACKFOT, LZ4FH, PAINT816, PURPLE, PRINTSHOP,
  NEWSROOM, FONTVIEW) starts a slideshow: the next picture comes after
  about five seconds at 1 MHz, round the folder without end. S again or
  any other key stops it, and that key acts as usual.
- Right on the last picture of a folder now goes round to the first.
- It only ever sends Right: the viewers' checks and the /RAM consent given
  for the browsing session are unchanged; a picture that cannot be read
  ends the slideshow with its message. The music viewers keep S as an
  ordinary key.
- MAIN 65C02/6502: 93/503 bytes free (203/609 before); 57/469 with the
  title page's changes below.

## [0.9.4] - 2026-09-26

### Disks named for their system, and a DEMO sorted by kind
- ProDOS images are now `A2FILECMD-PRODOS-140K`, `-PRODOS-800K`,
  `-PRODOS-XL` and `-PRODOS-XL-65C02-enhanced` (formerly
  `A2FILECMD-65C02-enhanced-mouse-XL`), beside `A2FILECMD-DOS3.3`. The
  enhanced XL is for an enhanced IIe, a //c or a IIgs; every other ProDOS
  image runs on any IIe.
- The XL DEMO folder is sorted by kind (DOCUMENTS, PICTURES with the HGR
  album, MUSIC, ARCHIVES, DISKS, PROGRAMS, FONTS.SHAPES) with a README; the
  CiderPress II samples join the folder of their kind.
- Revised README and guide cover (the 80-column panels at 560 x 384); the
  guide names Dazzle Draw and credits David Schmidt for ADTPro.

### Room, and a frozen ABI for 1.0
- 494 bytes free in the 65C02 resident instead of 82 (6502: 885 instead of
  485), with no behaviour change; the language card, twelve overlays and
  the 140K disk gain room too.
- The overlay ABI (API version 5, 54 services) and the `A2FILE.CFG` layout
  are frozen: new services are only appended with a new version
  (`tools/test_abi_freeze.py`).

### Large directories: faster pages, and Up no longer jumps forward
- Blocks wholly before the shown window are only counted, not validated:
  the last page of 1,500 entries takes 4.0 s instead of 5.8/6.4 s at 1 MHz.
  Nothing is cached, so a disk swap or a changed directory shows what the
  disk now holds; a read error is still an error.
- Fix, 65C02 edition: Up or Left near the top of a window with another after
  it loaded the next window (cc65 2.19 compiled a signed comparison as
  unsigned).

### Both compilers now read every sign alike
- All C units of both editions were audited for comparisons cc65 2.19 and
  cc65 master sign differently (768 sites): only the Up bug above could
  differ with a real disk. `tools/sign_compare.py` now refuses any
  unproven site in `make test`.
- Hardening: AWDATA's column counter is unsigned (a crafted row could read
  a label width from outside its table). Fix, 6502 edition: IDENT named a
  packed Extasie picture of 32 KB or more wrongly.

### VDrive leaves the printer alone
- VDrive no longer touches slot 1 (the //e printer SSC, the //c printer
  port): it tries slot 2, then 3 to 7. A VDrive host on a slot-1 card must
  move to slot 2.
- In slots 2 to 7, it first reads the SSC's mode switches, with no side
  effect, and takes the card only in communications mode: a printer-mode
  SSC is no longer reprogrammed nor sent envelopes. On a //c, port 2 is
  used as before.

### DOS 3.3 edition (Mini)
- The hex preview shows eight bytes a row with their characters, in two
  halves switched by Left/Right, `-`/`+` or `<`/`>`.
- The activity cell turns during a format (once a track) and during RWTS's
  retries on an unformatted diskette: the longest still screen falls from
  18 s to under 3 s, and from 4.8 s to 1.4 s on such a read. The borrowed
  DOS hooks are checked first and restored at once; writes never run with
  them.

## [0.9.3] - 2026-09-22

### Visible progress in long operations
- Every tool that can work for more than a few seconds at 1 MHz now moves
  something on screen. A progress bar is added to squeezed and ACU archives,
  AppleSingle/MacBinary, BinSCII, disassembly export, the image conversion
  check, cross-volume moves, file synchronisation, deleted file recovery,
  copies into ProDOS, CP/M, Pascal and DOS 3.3 images, the DOS 3.3 image
  clone and checks, Binary II and image extractions, and the zero-filling of
  a new disk image. Verification passes restart the bar instead of leaving
  it full.
- Where no bar fits, the activity cell (row 21, last column) turns: CRC,
  VERIFY, FIXIT, REPAIR, VOLINFO, text search, block search and
  extraction, the WIPE allocation check, dating and renaming tagged files,
  COMPARE, SEARCH, ShrinkIt threads skipped, the tools menu, drive scans,
  bitmap writing while formatting, picture viewers while they decode, and
  the scan for a picture's neighbours.
- The file counter at the start of the bar no longer shows another
  operation's count ("4/3") in tools, and a moved directory no longer
  inflates it for the files after it.
- DOS 3.3 copies reserve their sectors in one pass instead of a
  quadratic one, a silent pause of seconds after the confirmation.
- Bar labels fit the 15 characters shown, keeping their escape key.
- DOS 3.3 edition: every sector read or written turns the last cell of the
  key bar, the question leaves the screen as soon as it is answered, and a
  copy shows its empty bar before its first reads. RWTS's own format of a
  disk (about 18 s) still cannot show anything but its message.

### Faster ProDOS startup and panels
- Place the launcher and frequently used overlays together on distribution
  disks; load the resident program in larger reads without an extra buffer.
- Use compact native routines for panel labels and tag counts. Skip metadata
  decoding for directory entries before the visible page, retaining read and
  name validation. Count tags once per image extraction operation.
- Measured on POM2's NMOS 6502 / Disk II: startup takes 19% fewer cycles,
  cursor movement 15% fewer and scrolling 21% fewer than 0.9.1.
  See [method, results and limits](docs/PERFORMANCE-0.9.2.md).

### Recovery instructions and readable help
- Include `RECOVER` at the root of each ProDOS distribution disk. Explain
  backup and temporary names, ambiguous states, working on a duplicate and
  verifying recovered copies without overwriting surviving candidates.
- Point copy recovery messages to help and help to the guide. Document the
  limits of recovery after a power failure; no automatic recovery is promised.
- Space the last help row within 80 columns and give the return-to-panels
  footer a readable label. Move editor shortcuts onto a separate line.
- Reorganize the 0.9.2 user guide around installation, everyday operations,
  incident recovery and reference chapters. Refresh the PDF cover and linked
  contents; keep numbered steps separate and headings with their text.
- Condense the user guide to 11 pages including its cover, with 12 contents
  entries and unchanged text size. Preserve full attribution in `docs/CREDITS.md`.
- Introduce DOS3.3 before the expanded ProDOS workflow in both the guide and
  README. Add current 0.9.2 panel captures; keep the cover image compact.

### Qualification
- Complete automated qualification: 100/100 scenarios in the consolidated
  result, including four reruns after test fixture updates; 1,168 host tests.
  All five images pass inventory checks and all four ProDOS volumes pass
  filesystem audits. See [results and remaining limits](docs/QUALIFICATION-0.9.2.md).

## [0.9.1] - 2026-09-20

### Mockingboard 4c on Apple //c
- Wake the card before probing its VIA timers, only after identifying a //c
  from its ROM. Temporarily expose firmware and restore Language Card RAM
  before returning to the caller. A plain //c still reports no card.
- When the 4c masks the //c mouse ROM, stop calling that firmware and keep
  keyboard navigation. Mouse support remains available on a plain //c.
- Both CPU editions exercise MB1/PT3 playback, pause and end-of-song cleanup
  on disposable POM2 volumes, checking source files and AUX byte for byte.

### Visible phases during long operations
- ProDOS directory scanning, volume probes and sorting show an activity
  indicator. Counting files and loading tools announce their phase.
- COPY distinguishes copying from verification: the verification byte counter
  restarts at zero and advances during readback. Result/error messages keep
  their own row. Blocking disk calls can still pause the indicator.

### Five self-contained images
- Replace BOOT/FILES/MEDIA/DISKTOOLS/DEVTOOLS with one essential 140K
  ProDOS disk, one complete 800K ProDOS disk, XL 6502, XL
  **65C02-enhanced-mouse**, and DOS 3.3 (`A2FILECMD-DOS3.3-<version>.dsk`). The enhanced image requires
  both the processor and enhanced ROM; mouse support is optional.
- 140K includes text editing and MOVE, with space for preferences. Its menu
  no longer advertises absent category disks; unavailable shortcuts return
  a missing-tool message. 800K contains all 82 overlays and both BASIC
  runtimes without the XL demo corpus.
- Build and verify Mini as part of `make disk`; its DOS boot tracks come
  from the previously distributed Mini 0.9.0. Release checksums and uploads
  include exactly the five images and manual.

### The 65C02 edition checks the processor, not only the ROM
- On an enhanced IIe with a 6502 put back in, the 65C02 edition passed the
  ROM check and ran on the wrong processor. The launcher now tests the
  processor too and says which is missing (*THIS EDITION NEEDS A 65C02
  PROCESSOR: USE THE 6502 EDITION.*). Raised by transwarp2 on the forum.
- `tools/test_machine_check.py` runs the check under sim65 on both
  processors; `bench/machine.py` plays it in POM2 (`--preset iie_nmos`).
- README and manual: the 65C02 edition needs a 65C02 **and** the enhanced
  ROM; XL 6502 runs everywhere.

## [0.9.0] - 2026-09-19

### Writing into disk images
- **IMGPUT** (DISKTOOLS, XL) puts a file into a mounted ProDOS image; **C**
  with the image in the other panel runs it. Data and index blocks first, then
  the bitmap, then the directory entry: a cut costs at most lost space. Files
  above 128 KB (tree) are refused.
- **PASCALW** and **CPMW** (DEVTOOLS, XL) put the files of a ProDOS directory
  into an Apple Pascal or CP/M volume. A name already there is skipped, never
  overwritten. Pascal files go after the last used block (no gap filling) and
  keep their date; CP/M is limited to one 16 KB extent, and an empty CP/M
  volume is refused because its sector order cannot be told.
- **DOS33W** (DISKTOOLS, XL) deletes and renames a file on a real DOS 3.3
  disk, after a full audit of the volume, repeated after the question;
  **DOSREPL** replaces a file, the old copy staying readable until one catalog
  write switches to the new one.
- The ProDOS image writer no longer trusts a bitmap that marks the boot
  blocks, the volume directory or the bitmap itself as free.

### Reading more formats
- **PASCAL** and **CPM** (DEVTOOLS, XL) extract every file of an Apple Pascal
  or Apple CP/M volume into a ProDOS directory; the image is never written.
  Checked byte for byte on real Asimov disks (46 Pascal files, 27 CP/M files).
- **Return** opens `.QQ` and `.ACU` archives (UNSQ) and Business BASIC
  (`.BA3`, type `$09`, BASLIST).
- AWDATA shows AppleWorks spreadsheets as a grid with their column widths;
  **F** switches to the cell-by-cell view with formulas.
- `tools/lzc_ref.py`, the reference for NuFX LZC threads. 16-bit LZC (192 KB
  table) and NuFX SQueeze threads will not be supported.

### Interface
- A tagged or locked directory shows its mark on its panel line.
- Picture viewers show only the name being loaded, from the first picture on:
  the panels no longer flash between or before pictures.

### Tests and build
- `bench/all.py` holds all 93 benches; `make qualify` plays them and
  `tools/test_bench_inventory.py` refuses a bench left out.
- `tools/check_warnings.py` refuses new compiler warnings;
  `tools/test_cc65_traps.py` scans every unit for the known cc65 miscompiles.
- `docs/HARDWARE-CHECKLIST.md` and `tools/hw_media.py` prepare a session on a
  real Apple II.
- 190 bytes regained in the resident (MAIN 466 bytes free on 65C02, 865 on
  6502), with no change in behaviour.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.8.9...v0.9.0)

## [0.8.9] - 2026-09-17

### SQueeze and ACU (FILES)
- UNSQ extracts SQueezed files (`.QQ`, BLU's; the squeezed members BINARY2 takes out of a `.BQY` archive) and AppleLink ACU archives, with their names and types, following the file-service contract: a taken name is skipped, a damaged stream or failed write removes the file, every file is read back. `tools/squeeze_ref.py` (decoder and encoder) is the reference, checked on CiderPress II's samples: the `.QQ` of its Binary II archive decodes to the plain copy stored next to it. `tools/test_unsq.py` runs the real entry point on synthetic and real files.
- CRC and IDENT move from FILES to DEVTOOLS, where the menu already lists them under Programming: FILES had 5 blocks left.

### Business BASIC and Magic Window
- T (and BASLIST from the menu) lists the Apple ///'s Business BASIC programs (BA3, `$09`) with CiderPress II's token tables; `tools/busbasic_ref.py` is the reference.
- MDVIEW skips the 256-byte header of a Magic Window document (`.MW`, starting `$8D`) and reads its high-bit text. Teach documents are extended files: ProDOS 8 cannot open them, so they are not supported.

### Fixed
- A DOS 3.3 disk image inside a `.2MG` opened as "Not a ProDOS disk image (or DOS 3.3)": cc65 compiled `img_dsk = copy_buf[0x0C] == 0;`, written just after `if (copy_buf[0x0C] > 1)`, into a `booleq` on the flags of that first comparison, so the sector order read as ProDOS whatever the header said. The order byte is now read into a variable and tested once, and `tools/test_flag_reuse.py` compiles the resident for both editions and refuses a boolean built on a comparison a branch has already used. `bench/dosimage.py` is what caught it; it is back to 20/20 on both processors.

### Menu
- The overlay menu keeps 88 entries instead of 64: with the new overlays the list passed 64 and the last ones read were dropped (WIPE and VOLNAME vanished from Disks). The list now sits at `$2A00`, and `tools/check_layout.py` keeps MENU's code below it.

### Hi-res fonts (MEDIA)
- FONTVIEW also shows the 7 × 8 hi-res fonts of DOS Toolkit and HRCG (96 or 128 glyphs, 768 or 1,024 bytes, FNT or BIN). FONTVIEW is now assembly, entry point included: both formats take 1,127 bytes where MGTK alone took 1,252 in C. `tools/test_fontview.py` runs the whole overlay under sim65 (it replaces FONTVIEW's host harness); an MGTK font of exactly 768 bytes stays MGTK.
- Print Shop borders were not added: neither a specification nor CiderPress II describes their layout, and the sample's bytes do not settle it.

### Applesoft shape tables (MEDIA)
- SHAPES draws a shape table 24 shapes a page on the hi-res screen, each centred in its cell, the page shown in the mixed-mode text; Space and B turn the pages. Its own vector tracer and plotter, in assembly with the entry point, fit the 1,280 bytes below the picture page. Return opens `.SHAPE` files. `tools/shapes_ref.py` is the reference; `tools/test_shapes.py` runs the whole overlay under sim65 with a scripted service table and compares every page byte for byte, CiderPress II's three tables included (shipped in `DEMO/CIDERPRESS/GRAPHICS/SHAPETABLE`).

### File viewers by suffix
- The suffixes that name a viewer on their own (`.MB`, `.PT3`, `.ED`, `.FOTO1/2`, `.MAC`, `.AS`, `.BSC`, `.BSQ`, `.SHAPE`) are one table in OPEN: the new formats fitted with it. `.PNTG` did not: open such a MacPaint file from the **!** menu. A `.MB` file now goes to MUSIC whatever its type; MUSIC checks it. A file that cannot be read to identify it now says "NAME failed (...)".
- MENU texts were shortened to keep MENU.PLG within 7 blocks.

### BinSCII (FILES)
- SCIIBIN decodes BinSCII (`.BSC`, `.BSQ`), the text encoding Apple II files travelled in on Usenet, into the file it carries, with its ProDOS type. A file posted in several parts is decoded from the first one: the files that follow it in the directory are read until the file is complete. Header and data CRCs are checked on the way in, and the file is read back against them; any failure removes it. The CRC runs through a table in assembly (`src/plugins/sciibin.s`). `tools/binscii_ref.py` is the reference; `tools/test_sciibin.py` decodes synthetic files, damaged ones and CiderPress II's real posts -- ShrinkIt and a five-part Z-Link, both in `DEMO/CIDERPRESS/ARCHIVES`.

### AppleSingle and MacBinary (FILES)
- UNWRAP extracts the data fork of an AppleSingle file (versions 1 and 2, as GS/ShrinkIt and Mac OS write them) or a MacBinary file (I, II, III) into the other panel, with its name and ProDOS type: from the ProDOS information when there is some, otherwise converted from the Mac type and creator as AppleShare and the GS/OS FSTs do. It follows the file-service contract: exclusive creation, read-back comparison, removal on failure. Return opens `$E0/$0001` and `.AS` files. `tools/unwrap_ref.py` is the reference; `tools/test_unwrap.py` runs the real entry point on synthetic files and on CiderPress II's samples, three of which ship in `DEMO/CIDERPRESS/ARCHIVES`.

### DiskCopy 4.2 images
- Return opens a DiskCopy 4.2 image (`.DC`, `.DC42`, `.IMAGE`, `.IMG`) as a folder, like a `.PO`: the 84-byte header is checked and skipped. The resident's suffix tests became one table, which paid for it (4 bytes on the 65C02 edition).
- IMGCONV converts to and from DiskCopy (**C**): the output carries the checksum of its blocks and the `$E0/$8005` file type; a DiskCopy source must match its own checksum, checked before anything is created, or the conversion is refused. The checksum is computed in assembly (`src/plugins/imgconv.s`): in C, the 32-bit rotation over an 800K disk would take minutes. `tools/dc42.py` is the reference, checked against a real Apple image; `tools/test_dc42.py` and `bench/diskcopy.py` (11 checks on both processors) test both sides.
- The XL demo folder has `DISK800.DC`, an 800K ProDOS volume in DiskCopy form.

### AppleWorks data bases and spreadsheets (FILES)
- AWDATA reads AppleWorks data bases (`$19`), one record at a time with their dates and times, and spreadsheets (`$1B`), one cell per row: text, number, or formula with the result AppleWorks saved. Return opens them. The layouts follow CiderPress II's converters (`tools/awdata_ref.py`); `tools/test_awdata.py` compares every screen of the C with it on the host.
- Numbers are printed by Applesoft's FOUT from the ROM, after converting AppleWorks' 64-bit doubles to the ROM's 5-byte form in assembly. FOUT needs `$A4` at 0, as BASIC leaves it; any other value prints 0.5 as `.500592008`. A test runs the shipped routine against an Apple II+ ROM under sim65 when one is at hand.
- cc65 master (the 6502 edition) drops the sign extension of `(signed char)f()`: relative cell references printed `#ERR#` on the 6502 edition only, now extended by hand.

### Floppies and samples
- WIPE moves from BOOT to DISKTOOLS: every new overlay adds a 78-byte record to BOOT's command catalog, and BOOT had fallen to 0 free blocks. BOOT has 11 again.
- The XL image carries real files from CiderPress II's test data in `DEMO/CIDERPRESS` (a MacPaint picture, an AppleWorks data base and spreadsheet), from `data/CP2/`. MACPAINT's tests and bench now also read ESCHERWATER.MAC.

### MacPaint pictures (MEDIA)
- MACPAINT shows MacPaint documents (576 × 720 dots, PackBits lines), with or without a MacBinary header, in double hi-res black and white, 560 × 192 at a time; Up and Down scroll by 96 lines. Return opens a `.MAC` file (any other name through the **!** menu), and Left/Right browse them. The whole file is unpacked once before the auxiliary memory is written, noting where every 48th line starts, so each view is drawn from a seek. The overlay is written in assembly, entry point included, to fit its 1,280 bytes; `tools/macpaint_ref.py` is the reference, `tools/test_macpaint.py` runs the decoder under sim65 on both processors.

### Arlequin pictures (MEDIA)
- ARLEQUIN shows the pictures of Le Chat Mauve's ARLEQUIN 1.1 interpreter (1985), ProDOS type `$F8`, in the card's mixed mode: full-screen pictures and windows, centred on black. They are not Purplesoft GRLOAD pairs, which is why PURPLE refused the ones in `/GISTDATA/IMG/PURPLE`. The format was read in ARLEQUIN's own loader and checked against it byte for byte under POM2 with a Féline card (`docs/ARLEQUIN-FORMAT.md`). Return and I open a `$F8` file that carries Arlequin's signature; Left/Right browse the pictures of a folder. The whole file is checked before the auxiliary memory is written, and `/RAM` is rebuilt afterwards.

### File services closed
- Every file A2 File Cmd writes now follows one contract: new files by exclusive creation only, the original kept until its replacement is written, closed and read back, cleanup limited to what the operation created and never reported when it failed, name collisions refused. GOTO, IMGCONV, VOLINFO and MOVE use the shared ProDOS CREATE; saving preferences uses the shared reservation and publication.
- MKIMAGE, UNDELETE, RESCUE and MOVE checked nothing when removing an incomplete file and could say "removed" when it was not; a failed removal now stops the tool and says the incomplete file stays. VOLINFO removes the empty report it could not open.
- COPY refused a brand-new file whenever an old A2FC.BAK lay in the destination, after copying it; A2FC.BAK now matters only when an existing file is replaced, and is checked before writing.
- VOLNAME refuses a name another online volume already has ("Name in use."). ProDOS accepts it, and two volumes then answer to the same path.
- Lock and unlock (L) keep the read, backup and invisible bits. SYNC checks that an existing target may be renamed as well as deleted before copying.
- UNSHRINK checks the master and record header CRCs before writing anything of a record, skips files whose type ProDOS cannot hold and disk images not made of 512-byte blocks, and gives each extracted file its archived lock and modification date after reading it back.
- BLKEDIT and BLKVIEW no longer write 8 bytes past their service-table copy into the resident.

### FIXIT and REPAIR on hard disks
- FIXIT and REPAIR walk a volume's directory tree once, whatever its size. Above 4,096 blocks they used to walk it once per bitmap block, sixteen times on a 32 MB disk: a full FIXIT of a 32 MB hard disk with 690 files took about 69 minutes of a 1 MHz machine, REPAIR about three times as long. The blocks reached are now recorded in auxiliary memory, one bit each: the same FIXIT takes about 2 minutes 15 seconds, a REPAIR that writes about 7 minutes (measured under POM2).
- Auxiliary memory holds the /RAM disk: above 4,096 blocks both tools first ask "ALL /RAM files will be LOST. Continue?", once per run, and rebuild /RAM empty on the way out. A volume in slot 3, drive 2 is never checked that way. Volumes up to 4,096 blocks (floppies, 800K disks) work as before and ask nothing.
- FIXIT asks how deep to look on such a volume: **Q**, a quick check of the directories alone (about 8 seconds on the same disk, title marked `- QUICK`), or **F**, the full check. `R` asks again. REPAIR always checks in full.
- Escape pressed to stop a long operation stayed in the keyboard: the C that was meant to acknowledge it read `$C010` and threw the value away, and cc65 drops such a read. FIXIT then closed its findings screen at once, and the key reached whatever read the keyboard next, in VOLINFO, REPAIR, VERIFY, TXTCONV, the block and file tools built on `util.h` (DISKCMP, MKIMAGE, RESCUE, SYNC, TREE, UNDELETE, MOVE, NIBCOPY, DISASM, BLKVIEW, the DOS writers) and the content search. The strobe is now written, which clears it too; `tools/test_strobe.py` refuses the old form.
- FIXIT, REPAIR, VOLINFO and FIND copied the whole 106-byte service table below `$4000` and overwrote the first 8 bytes of the resident, its start-up code; nothing ran them again before the next load, so nothing showed. They now copy the 98 bytes they read.

## [0.8.8] - 2026-09-17

### FIXIT and REPAIR (DISKTOOLS)
- FIXIT checks a ProDOS volume and writes nothing: 30 checks over the header, the directory chains and back-links, every entry's storage type, name, access bits and pointers, file and directory counters, index blocks, extended forks, cross-linked blocks and the allocation bitmap (blocks used but marked free, lost blocks, reserved blocks marked free, padding bits). Findings are listed one check a line with their count and first block, 18 a page; `R` scans again. A pass cut short (loop, depth, read error, Escape) reports no lost blocks at all, since a block nobody claims may belong to the part not reached. Every check is compared to a host reference checker (`tools/prodos_check.py`) on 26 named corruptions (`tools/corrupt_prodos.py`); the published images all check clean.
- REPAIR runs the same pass, shows the plan, asks for the word `FIX`, reads the header again before the first write, then rewrites the bitmap pages recomputed from the walk and seven directory repairs (file counts, blocks used, directory EOF, header and parent back-links, back pointers of a chain). Each block is kept in main RAM, written, read back into another buffer and compared; on any error the original is written back and checked, and a block that could not be restored is named. A second pass must come back with nothing for the note to say `repaired`. Cross-linked files are never arbitrated: a cross-link refuses the whole plan, bitmap page and counter alike, because a block two things claim may be the one a counter repair rewrites while a file holds it as data. Lost blocks are not freed while a broken entry remains; an invalid header, an incomplete pass or the volume the program runs from refuse the whole plan. Originals do not survive a power cut. `tools/fuzz_prodos.py` is a sanitizer-backed mutation campaign over the same C, judged case by case against the host oracle: 15 000 images over three seeds, seven invariants, and it is what found the cross-link hole above. Both live in the `!` menu under Disks, on the DISKTOOLS disk and the XL image.

### A2FileCmd Mini DOS3.3
- Disk access follows DOS 3.3's 2:1 interleave: the copy reserves and writes its target sectors from 15 down within a track (as DOS allocates), the format visits tracks 0–2 the same way, and the disk builder lays the shipped files down that way, so chains are read two slots apart instead of fourteen. RWTS moves sectors straight to and from the working area, the progress bar moves once per batch, and the screen holes are no longer saved around every call. A batch is written, then read back and compared even indices first, then odd; a file is still published only after every sector read back. The batch is verified one track at a time, the first batch is read before the target's VTOC is touched (one change of drive fewer), the destination catalog and the panels' catalog chain are read straight into their buffers, the panel read staging its chain in the working area and parsing afterwards. Copying `A2FC` (90 sectors) drops from 67.9 s to 25.0 s at 1 MHz, a full 105-file catalog reads in 1.8 M cycles instead of 4.3 M, and the format writes its 15 catalog sectors as one batch read back afterwards, the VTOC still last (45.8 M → 35.6 M cycles); `bench/mini33_time.py` now traces every RWTS call.
- Delete audits the disk once per batch instead of once per file (about 16 s on a full disk); rename scans for a collision once, at the prompt, and holds the VTOC and slot sector to that scan before writing; lock and rename patch the panel entry instead of rereading the catalog.
- The format shows a progress bar, filled between its disk phases; after Y, N or Escape the last row shows the main keys again instead of the question. `bench/mini33_format.py` also formats a blank drive 2, copies every file of drive 1 onto it and boots the result.
- A tagged copy no longer stops at the first file that does not fit: that file is skipped, smaller ones after it land, and the result says `DISK OR CATALOG FULL`. A write-protect tab flipped after a copy's VTOC went down is reported as an uncertain write, since sectors are reserved and the fault is latched, instead of `DISK IS WRITE PROTECTED`.
- A tagged delete or a lock on a write-protected disk answered `1 DELETED` or `LOCKED` and painted the change on the panel although RWTS had refused before writing: the engines returned the refusal with the zero flag set and the batch loops tested the flag. They now report `DISK IS WRITE PROTECTED` and reread the disk (found by adversarial key sequences in POM2).
- A key typed while a copy, delete or format runs no longer answers the next question: the keyboard is cleared before every Y/N/ESC prompt.
- The editor types I, J, K and L as letters; moving is Ctrl-K/Ctrl-J and the arrows, as its key bar now says.
- On a disk formatted without DOS whose tracks 1–2 had filled up, every file there read as invalid and, since a delete audits every file, nothing on the disk could be deleted; the boot sector now decides whether tracks 1–2 are DOS's or files' (found by fuzzing the engines).
- A new text saved under a name that exists asks for another name instead of losing the text; the format's refusal message no longer takes a read error of the boot disk for the absence of DOS, and a VTOC write refused by a write-protect tab after the format reports a failure instead of latching an uncertain write.
- The help page shows every key in inverse video, like the key bar, and lists Q.
- The loading screen says `CAPS LOCK ON IS NEEDED` in the middle, with the licence line moved to the bottom row; HELLO and the program's own splash draw the same layout.
- The Mini reproduces itself: a blank diskette in drive 2, F, then every file of drive 1 marked and copied, gives a second bootable Mini disk (manual, "Making another Mini disk").
- F formats the active panel's drive as a bootable DOS 3.3 disk: RWTS formats the 35 tracks (volume 254), the 48 DOS sectors of tracks 0–2 are copied from the boot drive, then an empty catalog and the VTOC as `INIT` leaves them. The boot disk is read in full before anything is written and is never written; the boot drive, a latched fault and a boot disk without a DOS 3.3 boot sector are refused untouched; write protection is sensed by writing the target's VTOC sector back as it was, since RWTS's FORMAT does not report it; every target write is read back. The engine runs from `$0200–$03CF`; the splash and the start-up code moved into the working area to make room. Under sim65 the assembler now really sees `SIM65`, which `cl65 -D` never passed on.

### Distribution
- The BOOT floppy keeps 3 free blocks again. Naming FIXIT and REPAIR in the menu had cost it one, and with 2 left, preferences saved once and every later quit warned and kept the old file: A2FILE.TMP made ProDOS extend the full A2FILE directory with the last free block. Two menu strings are shorter; `tools/check_images.py` now refuses a bootable image without room to save A2FILE.CFG twice.
- Benches: `bench/run.py --xl 6502|65C02` plays the full session on the published XL images, rebuilt byte for byte with the work files at their root.

## [0.8.7] - 2026-09-15

### Data preservation
- UNSHRINK wrote ShrinkIt runs of 130 to 256 identical bytes as a single byte and still reported the file verified (the read-back decoded it the same way). Runs are decoded in full; malformed streams (codes outside the table, oversized chunks, lengths that do not add up) are refused instead of hanging or writing into I/O space; the LZW/1 stream CRC and the NuFX v3 thread CRC are checked; /RAM is recognised by its driver, not its name; a verified file is kept when only the archive tail is damaged. The real assembly core now runs under sim65 in the host tests.
- DOSGET keeps sparse random-access text files and every sector of S, R and new A/B files (no header stripped). IMGFS reads the storage type from the directory entry. DISKIMG reads non-ProDOS floppies, recognises a Disk II by its slot ROM, checks the disk at every one-drive swap and names the disk that will really be erased; W accepts real image names only.
- COMPARE and SEARCH report read and close errors instead of "Identical" or "not found"; BINARY2 skips folder records; a failed image panel read no longer mixes stale entries with volumes; the editor asks before saving converted text and leaves an unchanged file alone; tagged deletes say when directories go with their contents.
- MOVE reads and compares everything again after the confirmation (a disk swapped during the question writes nothing), bounds directory walks, never takes a read error for a free name, and allows moves at the program volume's root. BLKEDIT refuses the running volume from a subdirectory, writes into images and refuses locked ones. RESCUE really retries and uses the fresh size; UNDELETE walks a volume root and recovers empty files; VOLNAME keeps image panels consistent; TXTCONV, IMGCONV and DOSWRITE tell a refused install (nothing changed, temporary removed) from a failed one.
- PAINT816 and EXTASIE never touch /RAM for a refused picture; DISKCMP never compares a disk with itself; FIND reports unreadable files; VERIFY verifies every tagged volume; VOLINFO skips directory headers; MDVIEW and INTBASIC lose no text at a page end, and INTBASIC reads past 64 KB.

### Disks, VDrive and launch
- FORMAT identifies the target again just before the first write: a disk swapped during the prompts is left untouched. The language card is always restored after a direct driver call.
- VDrive: a send that never completes (no cable) returns an I/O error instead of freezing; STATUS no longer claims 65,535 blocks, so a blank host image is refused by FORMAT; the interrupt handler starts with CLD; both drive vectors are restored on exit.
- The launcher refuses a truncated A2FILE.CODE; the page-3 chain closes its file on every path.
- BIN launch uses the file's own load address and type, not the panel's.

### A2FileCmd Mini DOS3.3
- One write-fault latch for every command; the destination panel is reread after a failed copy; copies never allocate on tracks 1–2; `$8D` line ends in the editor; a full 8 KB text is refused rather than cut; batch results count what was done and skipped; renaming to the same name says so; delete refuses a cross-linked disk.

### A2FileCmd Mini DOS3.3 disk, replaced after the tag
- Stray characters no longer appear in column 8 during disk access (a letter missing from `COPY 5 MARKED?`, a lone letter lower on the screen). Around every RWTS call the Mini saved and restored the Disk II screen holes at `$0478+slot×16`, which are visible cells, instead of `$0478+slot`, where DOS 3.3 keeps each drive's current track.
- RETURN on a binary runs it: a 32–34 sector binary still opens as a hi-res picture, any other binary asks `BRUN NAME?` and, after Y, A2FC Mini leaves and DOS runs it from the panel's drive. B does the same on any binary. The command runs from page 3, so nothing of the Mini runs after the program, which may load over it; a name DOS could not read back (a comma, an unprintable character) is refused.
- A simpler footer: panels show 19 files, the status and file name lines move down one row, and the last row lists fewer, clearer keys, each in inverse with its action attached (TAB PAN, C OPY, D EL, B RUN, / DRV, ? HELP, Q UIT): a label that starts with its key's letter does not repeat it, so questions read Y ES, N O, ESC ANCEL. An operation's result takes the file name line until the next key.
- Return opens a file by its content, not by type and size alone. It reads the first data sector and picks the text viewer, the hi-res viewer, hexadecimal or `BRUN NAME?`. A binary whose DOS header matches its size is a picture when it loads 8 KB at `$2000` or `$4000`, hexadecimal when it cannot run (empty, below `$0800`, reaching DOS's buffers at `$9600`), text when its bytes are text, and otherwise a program; a binary without such a header is a raw picture at 32–34 sectors, otherwise hexadecimal; a T file that is not text opens in hexadecimal. A 33-sector game is no longer shown as a picture, and the text viewer skips a binary's 4-byte header.
- The program is named `A2FC` on the disk, so `BRUN A2FC` starts it from DOS 3.3; HELLO runs it under that name.

### Distribution
- The BOOT floppy and the bench floppies keep 3 free blocks, what saving A2FILE.CFG needs: messages that no test checks were shortened and duplicated code folded where fixes had pushed overlays over a block boundary.
- Benches: VOLINFO waits for its disk prompt and runs from the bench floppy; data_safety uses a real image name.

### Validation
- 731 host tests in 62 suites, each new test first seen failing on 0.8.6. POM2 benches on both CPUs, the complete session 73/73.

### Earlier in this cycle
- Mini: copying a panel (`=` and the boot duplicate) now includes the catalog slot, so a mirrored view is a full identity. After a write, only panels showing that disk are reread; two views share one catalog instead of paying it twice. The copy engine still does not borrow the name tables. Host tests cover the slot, a namelist without one, and names left intact after execute.
- Every extraction now reads its output back. DOSGET, BINARY2, IMGFS (a disk image opened as a folder) and UNSHRINK reopen the closed file and compare it byte for byte with the source read a second time: the DOS sectors, the archive record, the image blocks, or the ShrinkIt thread decoded again from its start; the file must end where the data ends. A wrong byte, an unreadable output, a short read or a source lost during the second pass fails the extraction and removes the owned file. Host tests inject each fault.
- To make room, IMGFS is a big overlay (its entries come from the snapshot) and UNSHRINK keeps its state at $3E00 with its code allowed up to $3BFF; the unused `new_output` wrapper leaves the resident. 65C02 resident headroom: 429 bytes. The BOOT floppy keeps 3 blocks free.
- A tool-sequence bench (`bench/sequences.py`, both CPUs, in CI): picture, music, then a marked copy; a cancelled 300 KB copy, the same copy completed, then moved; a floppy swapped in drive 2 under an open panel, the volume list reread, a copy from each disk. Every byte is checked on the volumes after exit.
- The archive benches run on the 6502 bench floppy too (`make benchfloppy ARCH=6502`, `A2FC_BUILD=build-6502 A2FC_IMG=A2FILECMD-full`).

## [0.8.6] - 2026-09-14

### Files
- Directories can be tagged. Marked MOVE takes them: entry rewritten on the same volume; across volumes, copied and read back file by file, the source deleted only once everything arrived. MOVE on a selected directory across volumes does the same.
- The tree walks behind copy, move and delete no longer recurse: bounded frames, explicit refusals (path over 64 characters, over 213 entries along one path, unreadable directory) before any write. A 20-level tree is deleted and copied as far as ProDOS paths allow.
- The launch confirmation spells out the way back, e.g. `Run HELLO? Back: -/A2FC6502/A2FILE.SYSTEM`; the demo's HELLO points to `BYE` and the ProDOS selector.

### Distribution
- VOLNAME moves from BOOT to DISKTOOLS; BOOT has four blocks free again. The floppy launcher's title page is a line shorter.
- The DOS 3.3 catalog and disk-image directory readers live in a CATALOG overlay (BOOT and XL); a read requested while another overlay runs is deferred and settled by the main loop. 65C02 resident headroom: 299 bytes (was 23).

### Manual
- A2FileCmd Mini DOS3.3 has its own section, clearly apart from the ProDOS edition: keys, disk writes, limits and speed; the download list separates its disk from the ProDOS images.

### Validation
- 653 host tests in 72 suites. POM2 benches on both CPUs, with the test host now writing the emulated hard disk back so byte comparisons are real; the 73-check session passes, BASIC return included.

## [0.8.5] - 2026-09-13

### Two editions, one version number
- A2FC Mini now carries the release number of the ProDOS edition, from the single `A2FC_VERSION` line of the Makefile; `A2FC-MINI-DOS33-0.8.5.dsk` ships with the release files.
- Mini 0.8.5, pure 6502: 40-column boot splash, tags, hi-res viewer, exclusive TXT creation and editor, DEL, LOCK/UNLOCK and RENAME as verified catalog-only writes, one inverse key bar, results on the footer.
- Mini file-system bug hunt: every write goes back to the catalog slot the panel read, so a swapped or renamed disk is refused as `DISK CHANGED`; looping catalog chains, mismatched T/S lists and write-protected disks are refused before any write; the DOS UNDELETE mark is placed as DOS does. Disks formatted without DOS may use tracks 1–2.

### Music and pictures
- New DUET overlay (MEDIA/XL) plays Electric Duet songs (`$D5`/`$D0E7` type or `.ED` name, legacy `M.*` BIN files): speaker player transcribed cycle for cycle, Mockingboard when present, 1/2 switch outputs, D pulse width, P pause, Left/Right browse. The demo disk gains `CANON.ED`.
- Browsing lo-res and double lo-res pictures with Left/Right keeps the current picture on the air until the next one is drawn; no text-page flash or panel redraw between neighbours.

### Files and DOS 3.3 from ProDOS
- Copy ProDOS TXT/BIN/BAS/INT files to real DOS 3.3 disks (DOSWRITE) and into DOS-order DSK/DO/2MG images (DOSIMAGE/DOSPUT): allocations audited, VTOC reserved first, data read back, catalog entry published last, source kept; existing names and protected disks refused. The real Disk II slot is used, slot 5 included.
- DOSGET (FILES/XL) extracts DOS files with exact metadata: BIN keeps its load address, BIN/BAS/INT drop sector padding; cycles, bounds, I/O and cleanup are checked and Escape cancels.
- IDENT recognises DUET, PT3, font and specialised picture families and reports read errors; FIXTYPES validates DUET candidates, proposes `$D5/$D0E7` without renaming, and confirms every attribute change with metadata reread first.
- The `!` menu's category page shows how many overlays each category holds and what they are for.

### Data preservation
- UNSHRINK, BINARY2, DISKIMG, COPY, EDIT, BATCH, GOTO, SYNC, TXTCONV and IMGCONV own their output reservations through failed closes, report a failed cleanup by naming the retained file, and keep originals, recovery files and unsaved buffers on every failure and retry.
- COPY and editor saves publish through the shared verified-temporary installation with recoverable renames; a destination stream error is refused even when the write count is complete.
- UNSHRINK reads skipped threads and padding exactly, refuses truncated or inconsistent headers, stops on stream or close errors and cancels between blocks. Binary II refuses truncated headers, data and padding.
- Overlay loading refuses read errors, empty or oversized payloads, restores the panels after a failed large load, and clears the menu result so a missing menu cannot replay an old command.
- DOS image installs are refused when a write changed bytes outside the intended sectors or the validated 2MG header changed during confirmation; returning to the volume list resets image/DOS mode.

### Memory and validation
- Private editor, menu and archive messages live in their overlays (127 resident bytes back); DISKIMG, SYNC and COPY finalisation trimmed. Ceilings and the 192-byte C stack are unchanged; API v5 adds the active-entry snapshot without moving service offsets.
- 650 host tests in 70 suites, including 66 sim65 runs of the Mini modules with injected faults and the real 6502 under sim65 for the ProDOS services; POM2 benches on both CPUs for DUET, DOS writes, DOS images, overlay faults and the Mini disk. Seven release images verified; a page-aligned indexing bug in cc65 2.19 was found and worked around.

## [0.8.0] - 2026-09-12

### Navigation and interface
- Overlay menu organized by category; prompts displayed in inverse video.
- Return or I automatically selects the appropriate image viewer.
- Left/Right browses pictures and music of the same type within a directory.
- Leaving a folder restores its selection, including in large directories.

### Pictures and music
- New foreground Mockingboard PT3 player with pause, title, artist and player credits (4,608-byte modules).
- MB1 playback moves into a foreground overlay; both music players preserve /RAM.
- New viewers for MGTK fonts, Print Shop clip art and LZ4FH images.
- Improved Extasie, 816/Paint and DGR handling; direct opening of Integer BASIC listings.

### Data preservation
- Safer copy, move, save, conversion and extraction, with verified writes and recoverable originals.
- Explicit confirmation before destructive use of /RAM; safer preference saving and batch moves.
- Fixed malformed-file handling, incomplete directory reads, catalog loops and recursive stack overflow.

### Distribution and validation
- Five universal 6502 floppies: BOOT, FILES, MEDIA, DISKTOOLS and DEVTOOLS.
- Complete XL images for 6502 and 65C02, with 59 overlays; updated English PDF manual.
- 396 host tests, 7,140 mutation cases and 219 POM2 checks passed; seven release images verified.

## [0.7.5] - 2026-09-09

- Added six service overlays on EXTRA and XL for both CPUs: UNDELETE recovers deleted ProDOS file candidates to another volume; DISKCMP compares volumes and PO/DSK/2MG images; MKIMAGE creates formatted data images; RESCUE extracts readable data with retries and a missing-block log; SYNC copies missing/newer files recursively; TREE shows cumulative directory sizes.
- Recovery leaves source volumes unchanged. UNDELETE recognizes index halves swapped by ProDOS DESTROY and refuses ambiguous or reused blocks. SYNC reads back temporary copies before replacing older files, with rollback backups. DISKCMP supports exact single-drive comparison with prompts naming the expected disk and slot/drive.
- Added VOLINFO to BOOT and XL: free space, fragmentation, a paginated bitmap, shared/lost blocks, used blocks marked free and count checks. Incomplete scans never present a lost-block verdict.
- Replaced FORMAT.SYS with FORMAT.PLG, returning directly to the panels. Kept ERASE confirmation and protection of the running program. Physical Disk II formatting preserves resident memory, including on errors, and explicitly warns that /RAM is cleared.
- Published separate 6502 and 65C02 BOOT/EXTRA 140 KB floppies and complete XL 2mg images. Each XL has all 42 overlays, BASIC.SYSTEM, DEMO and IMGHGR; BOOT and EXTRA share a 41-command catalog. The two CPU families never share an EXTRA disk. Missing-disk prompts support selecting drive 1 or 2 and returning the source disk after an overlay loads.
- Added fifteen other service overlays: TXTCONV, DATE, VERIFY, TAGPAT, VOLNAME, WIPE, FIXTYPES, GOTO, FIND, CRC, IDENT, MDVIEW, RENAME, IMGCONV and BOOTBLK. See the [manual](docs/MANUAL.md#find-and-maintain-files) for their controls and limits.
- Fixed floppy sorting, jump-by-letter and marking differences after other overlays run. Expanded the paginated overlay menu to 80 columns and added the program configuration path to service API version 2.
- Included a printable English PDF manual with a clickable contents page and bookmarks.
- Added CPU-specific POM2 benches and host tests covering malformed allocation, real file deletion, reversed and partially processed indices, image bitmaps, failed writes, rollback, cancellation and memory bounds. Source comments and the SDK guide are in English.

## [0.7](https://github.com/habib256/a2filecmd/releases/tag/v0.7) — 2026-09-09

- Changed the title page: each build names itself (`- 65C02`, *ENHANCED Apple IIe* / `- 6502`, *UNENHANCED Apple IIe*, no mouse) so one knows which build booted.
- Fixed the HGR viewer leaving an RGB card (Le Chat Mauve, Video-7) in a mode it never asked for: raising AN3 clocked the card's mode latch with 80COL off, so two HGR pictures in a row drifted it to BW560; it is now clocked to COL140, its power-on state.
- Fixed both DHGR viewers on machines where a directory read shares memory ProDOS does not promise to leave alone (an Apple //c, seen on POM2): a raw DHGR page was refused as `not an image` and a packed one (`.RLE`) hung the viewer, because their auxiliary plane was filled with `$2000-$3FFF` routed to the auxiliary bank; both now decode in main memory and move the plane across with `AUXMOVE`.
- Fixed a phantom mouse click at start-up: the first reading of the mouse reported the button held down at the top-left corner, which the viewer took for an Escape and, at the root, dropped to the volume list. The launcher now primes the mouse once so the false press is discarded. Most visible on an Apple //c and on any machine with an AppleMouse, where every picture and menu bounced back to the volumes.

## [0.6.8](https://github.com/habib256/a2filecmd/releases/tag/v0.6.8) — 2026-09-09

- Added a 6502 build for the unenhanced Apple IIe (`A2FILECMD-6502.*`, `make disk ARCH=6502` with cc65 master): the same program, keyboard only — no mouse driver. Both builds are made and published together.
- Added `IMGHGR/` at the root of the `.2mg`: nine HGR pictures from POM1, to leaf through with the arrows.
- Added Left/Right in the overlay menu, five entries at a time.
- Changed the panels: a directory name ends with `/`, like Ammonoid; a volume row reads `/VOL/`.
- Changed the volume list to ProDOS's own `ON_LINE` enumeration, so that every unit ProDOS knows is listed, mirrored SmartPort units included.
- Changed SPACE: tagging a file no longer moves the cursor down.
- Fixed VDrive on a //c picking the printer port: slot 2 (the modem port) is probed first, then 1, 3 to 7.
- Fixed the DHGR test card in `DEMO/`: twelve of its sixteen bands showed as vertical stripes (a repeated byte is not a solid colour); the bench now checks the rendered picture, not only memory.
- Fixed the Binary II extractor leaving the other panel stale: the extracted files now appear in it at once.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.6.7...v0.6.8)

## [0.6.7](https://github.com/habib256/a2filecmd/releases/tag/v0.6.7) — 2026-09-08

- Added VDrive: two ProDOS volumes served over a Super Serial Card (or a //c's port 2) at 115 200 bps by ADTPro, `veserver.py` or surl-server, with the ADTPro VSDrive protocol; installed for the session, like Ammonoid. The driver (`src/vsdrive.s`) lives in the language card behind a page-3 thunk; its buffer accesses go through page 3 with bank 1 switched in, because ProDOS's `GBUF` targeted by `ON_LINE` is in bank 1 (the remote volume used to appear under the floppy's name); and it installs a ProDOS interrupt handler (`ALLOC_INTERRUPT`) so a DCD drop behind a real modem no longer ends in `RESTART SYSTEM - $01`. `bench/vdrive.py` runs it on POM2 (`pom2_playtest --ssc`, six checks).
- Added a full-width progress bar to copy, move and delete (forty cells, a counter and the byte count, redrawn only when it changes); ESC interrupts them (the partial file is removed and `Interrupted: x of y` is shown), and the panels update file by file without rereading the disk (`drop_entry`). To make room, the string literals of the EDIT, MUSIC, MENU, IMGFS, DOS33, DELETE and ATTR overlays became named arrays in their own segment, returning about 600 bytes to the resident. `bench/ops.py`, seven checks.
- Fixed a blank screen on unsupported machines: the launcher now requires an Enhanced IIe, //c or IIgs with 128 KB and 80 columns, and says so before returning to ProDOS.
- Fixed ShrinkIt extraction after viewing HGR/DHGR images: the LZW dictionary no longer overwrites main memory through the graphics banking switches.
- Fixed extraction progress: show each file from the start, with its archive position, progress bar and extracted byte count.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.6.6...v0.6.7)

## [0.6.6](https://github.com/habib256/a2filecmd/releases/tag/v0.6.6) — 2026-09-08

- Added ShrinkIt (`.SHK`, stored/LZW/1/LZW/2) extraction (`UNSHRINK.PLG`, the LZW core in assembly running from auxiliary memory) and Binary II (`.BNY`) extraction (`BINARY2.PLG`) with the ProDOS file attributes.
- Added readable Applesoft listings (`BASLIST.PLG`), an AppleWorks word-processing viewer (`AWP.PLG`), byte comparison (`COMPARE.PLG`) and text search (`SEARCH.PLG`): six more overlays built on the SDK model, each with its own bench (`bench/shk.py`, `bny.py`, `awp.py`, `find.py`).
- Added the bare floppy and the bootable 32 MB `.2mg` (`/A2FILEHD`) with a complete `DEMO/` collection; floppy images now carry the program without demos, and `tools/mkvolume.py` writes ProDOS tree files.
- Fixed launching and returning from a program installed in any directory: the launcher keeps the prefix (or rebuilds it from the path ProDOS leaves at `$0280`), and the formatter and `RUN` start from the program's own directory (`bench/subdir.py`). A `.2MG` whose size is not a multiple of 512 bytes now opens as a directory.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.6.1...v0.6.6)

## [0.6.1](https://github.com/habib256/a2filecmd/releases/tag/v0.6.1) — 2026-09-08

- Fixed DOS 3.3 volume rows overflowing into the neighbouring panel and leaving white squares.
- Fixed file-info, attribute and launch failures reporting a stale ProDOS error.
- Added plain-language ProDOS error messages and an English manual.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.6...v0.6.1)

## [0.6](https://github.com/habib256/a2filecmd/releases/tag/v0.6) — 2026-09-08

- Added floppy image tools (`W`, `DISKIMG.PLG`): write a `.PO`/`.DSK`/`.DO`/`.2MG` to a floppy, read a floppy into a new image, and copy floppy to floppy on a single drive by swapping disks at each pass. Blocks go through `READ_BLOCK`/`WRITE_BLOCK` with buffers in main (`$3400`) and auxiliary (`$2000`) memory, so `/RAM` is rebuilt afterwards; typing `ERASE` guards every write.
- Added read-only disk-image browsing (`IMGFS.PLG`): RETURN on a `.PO`/`.2MG`/`.DSK`/`.DO` opens it as a directory (subdirectories, `..`, leaving it), and `C` extracts the tagged files to the ProDOS directory of the other panel. The resident block reader (`img_read_block`) handles the DOS 3.3 sector interleave of a `.DSK` and the `.2MG` header; seedling and sapling files (up to 128 KB) are extracted, the rare tree files are refused.
- Added DOS 3.3 catalog reading and extraction, from an image (`.DSK`/`.DO`/`.2MG`) or from a real disk in a drive (`dos_read_sector` reads the matching ProDOS half-block with `READ_BLOCK`). A DOS 3.3 disk without a ProDOS volume is listed under `/`, recognised by its VTOC; RETURN opens it as a flat directory and `C` extracts (`DOS33.PLG`), stripping the DOS header of Applesoft, Integer and binary files.
- Changed the resident: the editor, music, launcher, attributes, delete, menu and disk-image commands moved out into on-demand `A2FILE/*.PLG` overlays, returning close to 3.5 KB to the main window (`$4000-$ADC2` instead of `$4000-$BADF`). A big overlay (`OVERLAY_BIG` in the header) may also take `$2000-$3FFF`; the core saves the tags, calls the entry point and rereads both panels on return.
- Added the service table `struct A2fcApi` (`src/a2fc_plugin.h`): the stable ABI a third-party overlay receives at its entry point (`fopen`, `message`, `confirm`, `prompt`, `dir_open`/`dir_next`, `read_panel`, `mli`...). The `sdk/` example (`hello.c`, `build.sh`, `plugin.cfg`) is linked outside the tree, without crt0 or `A2FILE.CODE`, and `bench/plugin.py` checks it appears in the menu and runs.
- Added the overlay menu (`!`, `MENU.PLG`), listing `A2FILE/*.PLG` with the one-line description of each header, so a new command needs neither a key nor a rebuild.
- Added the digits `1`..`0` as function keys for the ten buttons of the key bar, Ctrl-T / Ctrl-N to tag or untag everything, and Ctrl-R to reread both panels.
- Fixed relaunching A2FileCmd from Applesoft (`-A2FILE.SYSTEM`) freezing on a black screen right after the switch to 80 columns. Two causes: crt0, seeing `BASIC.SYSTEM` resident, put the C stack on its `HIMEM` (about `$9600`), in the middle of the code being loaded up to `$BE40`; the stack is now always at `$BF00` (`src/crt0.s`, `src/crt0_loader.s`). And `BASIC.SYSTEM` clears the ProDOS prefix when launching a SYS; the launcher now restores it (`src/loader_mli.s`), so A2FileCmd reopens on its panels instead of the volume list.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.5...v0.6)

## [0.5](https://github.com/habib256/a2filecmd/releases/tag/v0.5) — 2026-09-07

- Introduced the bootable two-panel ProDOS file manager with batch operations, recursive directory copy, sorting and file attributes.
- Included text and hex viewers, an 8 KB editor, HGR/DHGR picture browsing and Mockingboard playback.
- Included mouse navigation, program launching and the ProDOS disk formatter.
- Fixed issues in the editor, launchers, large directories and shared auxiliary-memory handling.

[Source at v0.5](https://github.com/habib256/a2filecmd/tree/v0.5)
