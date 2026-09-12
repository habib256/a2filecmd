# Changelog

Changes in upcoming and published releases. See the [README](README.md) for features,
downloads and installation.

## Unreleased

## [0.8.0] - 2026-09-12

- Prepare the 0.8.0 candidate and update the English manual and distribution
  names. Image validation checks the launcher's embedded release version and
  compares the shipped ProDOS and BASIC.SYSTEM bytes with their source files.
- PT3 channel-volume audit exercises the complete decoder and VIA output on
  both CPUs, with and without clock conversion; channel levels are preserved.

- Release CI rejects tags that disagree with the configured build version.
  Release notes derive the overlay count from the package inventory and keep
  current artifact names on branch builds even when Unreleased is empty.

- Deep recursive operations check actual C-stack headroom before directory I/O.
  Directory deletion preflights its tree before removing files; oversized trees
  are refused instead of corrupting resident memory.

- Directory read/close errors now invalidate incomplete panels and stop
  recursive operations. ProDOS image chains validate their backward links.
- DOS 3.3 rejects invalid track/sector coordinates, failed seeks and incomplete
  catalogs; cyclic deleted catalog chains terminate with an error.
- Media navigation refuses to restore a cursor outside a reread directory.
- Release CI refuses cancelled emulator jobs. The complete-session bench now
  tests foreground MB1 without AUX loss; its 140K fixture and dedicated archive
  fixtures fit again. Image mutation coverage includes MGTK, Print Shop and LZ4FH.

- Left/Right now browse tunes of the same type and files handled by the same
  specialized picture viewer, including across large-directory windows.
  At either end the current media stays open. Existing AUX consent remains.
- PT3 displays bounded, sanitized title/artist fields and credits Vince Weaver
  with the A2FC adapter; the 4,608-byte module limit is unchanged.
- Escape and Return on .. find the child directory in the parent's full listing,
  restoring its selection even beyond the first 139-entry window.

- MUSIC now contains the complete foreground MB1 player. P pauses/resumes,
  Escape returns, and natural end restores the panels. The 4 KB stream stays
  in main RAM; playback preserves /RAM and no player IRQ remains resident.
- Preferences use exclusive temporary creation, complete readback and a
  retained backup through replacement; errors preserve recovery files.
- Directory navigation moves into internal NAV; internal BATCH orchestrates
  MOVE on marked files with an exclusive verified destination manifest,
  stopping on errors and restoring pending source marks by name.

- The ! menu now opens task categories, then alphabetically sorted tools;
  Escape returns one level and Left/Right still move six rows. Its MAIN-only
  catalog holds 64 entries instead of 52, keeping all current tools visible.
- Questions on line 22 use inverse video, including confirmations, input and
  conversion/disk choices. Plain information remains normal.
- VOLINFO moves to DISKTOOLS to keep the 140 KB BOOT floppy within capacity.

- Added foreground PT3 playback on the Mockingboard: Return on `.PT3`, P to
  pause/resume, Escape to stop, and automatic stop at song end. The module
  and decoder use main RAM only (4,608-byte module limit). Card detection
  is separated from MB1's AUX reader installation. Runtime pointer guards,
  bounded command processing and checked input closure protect malformed
  modules. See the manual for tracker-feature limits.

- Return now opens Integer BASIC (`$FA`) files with INTBASIC. Return and I
  select three new MEDIA viewers: LZ4FH for FOT `$8066` (DIP.CHIPS), PRINTSHOP
  for monochrome 88x52 clip art (BBROS.MINI), and FONTVIEW for MGTK `$07`
  fonts. All three keep graphics in main RAM and preserve auxiliary RAM.
  Input bounds, stream errors and closure are checked before showing the image.
  Added host regressions and a native corpus bench for the 52 sample fonts.

- Successful real-hardware validation on Apple //c, enhanced Apple IIe and
  unenhanced Apple IIe confirmed by the maintainer on September 12, 2026.
  Updated the compatibility documentation and stabilization record.

- In the overlay menu, Left/Right now moves six lines, stopping at the
  first or last entry. The footer shows the six-line step.

- Return and I now select the correct picture viewer on both CPUs: Extasie
  ($F2), packed FOT ($08/$4000–4001), packed 816/Paint ($06/$E001–E002),
  and lo-res pages ($0400). Packed metadata takes priority over raw-page
  sizes; the raw/RLE album skips specialized formats. AUX-loss consent and
  explicit H for hex remain. DGR and HGRR/DHRR headers are also recognized
  without type or name hints; I opens unmarked small BIN/FOT screens and
  sprites in DGRVIEW. Probe read/close errors stop dispatch. OPEN.PLG is a
  small internal BOOT dependency.

- Floppies now use 6502 only: BOOT plus FILES, MEDIA, DISKTOOLS and DEVTOOLS,
  replacing EXTRA/EXTRA2. XL remains available for both 6502 and 65C02.
  A shared package manifest checks complete coverage, and every companion
  carries MENU and the catalog with the correct named disk prompts.

- BOOTBLK now reads both source and original boot blocks before any write,
  verifies each write and restores both originals after an installation error.
  Failed restoration is reported explicitly. Its main-memory backup leaves
  `/RAM` untouched but cannot recover a power cut. Fault-injection tests cover
  errors before and after physical writes, corruption and restoration failures.

- Data safety is now an explicit repository requirement in AGENTS.md, with a
  documented audit and recovery limits. Copies and editor saves preserve old
  files and verify results; extraction exclusively creates new files. TXTCONV
  and IMGCONV stage replacements, MOVE restores metadata after reported write
  failures, WIPE F validates live allocation, and DISKIMG rejects malformed
  sources and self-targeting. Destructive AUX use requires prior RAM-loss
  consent. Fault-injection and native emulator regressions accompany the fixes.
  The editor now holds 5,104 bytes; COPY.PLG is an internal BOOT dependency.

- Fixed: IMGCONV trusted 2MG data offsets and block counts without checking
  that the data lay outside the header and within the source file. Invalid
  offsets could convert header bytes, and truncated input could destroy an
  existing destination before failing. Range checks now run before destination
  access, using subtraction to avoid overflow. Tests cover invalid ranges,
  valid padding and trailing metadata, and preservation of existing outputs.

- Fixed: the host ProDOS image reader returned boot bytes for sparse data
  blocks and misread missing tree indexes, sometimes shortening file contents.
  It now returns zero-filled holes while preserving file offsets and EOF.
  Regression tests cover sapling and tree holes, missing indexes, and partial
  final blocks.

- Fixed: mkvolume.py allowed distinct host names to produce duplicate ProDOS
  directory entries after case normalization and type-suffix removal (for
  example, SMALL.TXT and SMALL.BIN both became SMALL). It now refuses these
  collisions within each directory and identifies both source names. Existing
  output images remain untouched on refusal; identical names in different
  directories remain valid. Tests cover suffixes, explicit type metadata,
  nested directories and file/directory collisions.

- Fixed: WIPE F trusted invalid bitmap locations, allowing boot/header bytes
  to be treated as allocation bits or erasing blocks before discovering that
  later bitmap pages were outside the volume. It now validates the bitmap's
  start and complete extent before confirmation or writes. Host tests verify
  malformed pointers cause no changes and a valid bitmap erases only its
  free block. This validates location, not the correctness of allocation bits.

- Fixed: same-volume MOVE bypassed file locks because raw directory writes
  never reached ProDOS's deletion access check. It now checks the on-disk
  source entry's destroy-enable bit before any write, for files and
  directories. Host tests assert locked entries leave the disk unchanged;
  POM2 locks a file through L, verifies refusal, then unlocks and moves it.

- Fixed: TXTCONV could bypass overwrite confirmation when a destination
  existed but could not be opened for reading. It now checks ProDOS metadata,
  refuses lookup errors, and exclusively creates destinations reported absent.
  Existing destinations still require explicit overwrite confirmation. Host
  tests inject failed reads and metadata errors and verify both files survive.

- Fixed: TXTCONV's accent conversion consumed ASCII characters or new UTF-8
  lead bytes after a broken sequence and silently dropped incomplete final
  sequences. These now emit `?`, with the following byte processed normally.
  Host tests cover two-, three- and four-byte sequences and 256-byte chunk
  boundaries; the POM2 bench verifies the converted file byte for byte.

- Fixed: same-volume MOVE followed any named entry as a directory, including
  regular files and resource-fork files. A stale panel path or damaged entry
  could make it rewrite file data as directory records. Every path component
  must now have directory storage type before traversal proceeds. Host tests
  cover invalid source and destination components and assert no disk writes.
  Lookup names reuse buffers that are idle until the move starts so both
  CPU overlays retain their memory limits.

- Fixed: IMGCONV validated only the low byte of the 32-bit 2MG format and
  silently truncated the 32-bit block count to 16 bits. It now refuses
  unsupported formats and oversized counts before seeking or creating output.
  Header parsing reuses the idle track buffer so the additional checks fit
  both CPU overlays. Host tests cover every discarded byte; the POM2 bench
  checks refusals and a valid 2MG-to-DSK conversion byte for byte.

- Fixed: IMGCONV ignored failed seeks to DSK sectors and to the data in a
  2MG input. It could convert bytes from the wrong position and report
  success. Failed seeks now report a read failure; an incomplete output is
  removed, and a failed initial 2MG seek leaves the destination untouched.
  Host tests inject failures into either DSK sector seek across two tracks
  and verify the normal sector ordering, plus refusal before destination
  access when the initial 2MG seek fails.

- Fixed: SYNC could accept a matching prefix as a verified copy, install a
  truncated file when the cached source size was stale, and remove the old
  destination backup. Verification now requires EOF in both streams before
  either destination rename. Host regressions cover stale sizes, unexpected
  output bytes and successful replacement with an empty file.

- Fixed: an in-place TXTCONV conversion could replace the original with
  a truncated or empty result after a source read error. The converter now
  requires the byte count recorded by the panel before replacing the source;
  an incomplete read or changed size reports "Read failed" and discards the
  temporary result. Host tests inject zero-byte and partial reads and cover
  empty files and exact 256-byte boundaries.
  In-place conversion also refuses an existing `TXTCONV.TMP` using exclusive
  ProDOS CREATE, preserving a previous recovery result and preventing a
  source with that name from being used as its own temporary file.

- Fixed: cross-volume MOVE treated a failed destination read-open as proof
  that the name was unused, allowing an existing file to be overwritten.
  It now uses exclusive ProDOS CREATE after confirmation and touches no
  destination on a creation error. Host fault tests cover the failed probe
  and failed creation; the POM2 bench also moves a file into /RAM and reads
  its contents back. Existing buffers are reused and unused Pascal-path
  storage is omitted from service overlays that do not need it.

- Fixed two MOVE directory-growth bugs. A damaged parent reference is now
  rejected before any write, preventing unrelated entry corruption,
  out-of-bounds buffer writes and partial growth on an unreadable parent.
  On a full volume larger than 61,440 blocks, allocation now stops before
  its 16-bit counter wraps to zero. Regression tests cover damaged parent
  references and bitmap boundaries; the allocator also runs under sim65
  when cc65 and sim65 are available to catch target-only integer overflow.

- Fixed: cross-volume MOVE could delete a longer source after copying and
  verifying only the size cached by the panel. Verification now checks that
  both files end at that size before removing the source. A size mismatch
  keeps the original and removes the incomplete copy; regression tests cover
  stale sizes, including zero, and a successful move of an empty file.

- Fixed: the second tool floppy was not in the release. `tools/check_images.py`
  still demanded that every service overlay be on EXTRA, so it failed on the
  ten that had moved to EXTRA2 -- and it runs in CI. The CI's own file globs
  (`A2FILECMD-*-EXTRA-*.dsk`) did not match `EXTRA2` either, so the disk would
  have been left out of the checksums and the published release. The checker
  now reads the split from the Makefile's `XPLUGINS_EXTRA2`, so the two cannot
  drift, and asserts that the three floppies partition the set of overlays
  with MENU the one deliberate overlap. README, the manual and the release
  notes describe four media per CPU, and the counts they quote (19 overlays
  on BOOT, 22 plus the menu on EXTRA, 10 on EXTRA2, 51 on XL) are the ones
  the images actually hold.

- MOVE no longer stops at a full target directory. It allocates a block from
  the volume bitmap, links it onto the end of the directory's chain and tells
  the directory's own entry that it is a block longer -- after asking, and
  saying what it is about to do: "Its directory must grow a block." The block
  is taken before anything points at it, so an interruption leaks a block,
  which VOLINFO reports, rather than leaving a directory pointing at one the
  volume thinks is free.

  The volume directory is still refused: its four blocks are fixed and it has
  no entry of its own to rewrite. Covered on the host against a volume built
  by mkvolume.py, and in the emulator with VOLINFO as the judge -- it reads
  the whole volume back and counts blocks used but marked free, shared
  references, invalid pointers, wrong counts and lost blocks. MOVE had no
  emulator bench at all until now; it has one.

- Added the INTBASIC service overlay: an Integer BASIC listing, ProDOS type
  `$FA`. BASLIST served the `$FC` and nothing served the `$FA`, which fell to
  the hex viewer or to the text reader, both of which show its tokens as the
  control characters they are -- and Integer BASIC is what the Apple II
  shipped with, and what Woz's own Breakout is written in.

  A line is `[length][number][ ... ][$01]`, the length counting its own byte,
  so the next line starts that many bytes on. A byte under $80 is one of 128
  tokens, several values sharing one text; a byte above is a character with
  the high bit set; and a byte in $B0-$B9 that does NOT follow a letter or a
  digit is the leading digit of a constant whose value is the next two bytes.
  That last test is the corner that matters: inside a string or after a REM
  everything is characters, and reading a $B5 there as a constant turns
  "WITH 5 BALLS" into "WITH 49824ALLS". The spacing is the interpreter's own
  -- a space before a keyword that begins with a letter, one after a keyword
  that ends with one, none around the punctuation -- which is what makes
  ": GR : PRINT : INPUT" out of bytes that hold no space at all.

  Pages with SPC, B and R like the other readers. **T** on a `$FA` opens it,
  as T on a `$FC` opens BASLIST and on a `$1A` opens AWP; it is also in the
  ! menu like every other service overlay. Checked against the rule written
  out in the tests, and in the emulator against the first lines of Breakout
  read off the screen.

- The resident is 110 bytes smaller, which is what paid for that T. The T
  and H cases of the main switch each wrote `pan->e[pan->cursor]` three
  times, and an entry is 29 bytes, so every mention cost a multiplication:
  the entry is taken once into a pointer now. Without it the 65C02 link went
  22 bytes past its ceiling -- it had one byte of room, and the language card
  reserve had one as well.

- Fixed: the smoke bench still looked for "A2 FILE CMD 0.7.5" in the status
  bar and had been failing since the version bump. It reads the version from
  the Makefile now, like the rest of bench/pom2.py.

- IDENT names two more families it used to call binary: the 816/Paint packed
  pictures (`$06` with auxtype `$E001`/`$E002`) and the Extasie `$F2`
  pictures, which open with their own length.

- Added the PAINT816 service overlay: the pictures 816/Paint saves packed,
  its own default -- ProDOS type `$06` with auxtype `$E001` for a hi-res page
  and `$E002` for a double hi-res one. 816/Paint is what most Apple II double
  hi-res art was drawn with, and a packed file is any size at all, so the
  core's image viewer, which claims a `$06` on its SIZE, never saw one: they
  fell through to the hex viewer.

  Nothing documents the format. It was read off twelve chosen-plaintext pairs
  -- raw pages written to a disk, packed by 816/Paint itself, the two
  compared -- and it is: one `$FF` a plane, then records whose tag carries a
  count in bits 6-2 (0 meaning the count is the next byte) and a pattern
  length of 1, 2, 4 or 8 in bits 1-0, the pattern repeating cyclically to
  make `count` BYTES; a tag with bit 7 clear is a literal run of `tag` bytes.
  It decodes COLUMN BY COLUMN, the rightmost first. A double hi-res file
  opens with the auxiliary plane's first eight bytes again, which the stream
  also carries, and every file ends with the Pascal string `816PATT` and 64
  bytes of fill patterns. All thirteen sample files -- twelve probes and a
  real picture, TWOSTEVESTITLE, 6,130 bytes for a 16 KB screen -- come back
  byte for byte, and the emulator bench reads the graphics page back to
  check the geometry the shipped 6502 lays down.

- Fixed: the Extasie `$F2` viewer decoded the wrong format. It read the
  stream into ONE hi-res page, row by row, with a count of 0 meaning 256; an
  Extasie picture is DOUBLE hi-res, 15,360 bytes read column by column -- the
  leftmost first, the auxiliary plane's forty columns then the main one's --
  and a count of 0 is 128. That is what makes all ten pictures on the
  original disks decode to exactly 15,360 bytes; the old reading produced a
  scrambled half-page. The picture now goes up in the Le Chat Mauve card's
  MIXED mode, 560 dots in black and white beside 140 cells of sixteen
  colours, which is what the format exists for -- Extasie's own title screen
  says so. A truncated stream is reported rather than shown, and the two
  planes are decoded as one stream, so a record crossing the boundary is not
  cut in two.

- There are now TWO tool floppies, EXTRA and EXTRA2. The extras stopped
  fitting 140 KB -- 313 blocks for 280 -- so EXTRA keeps BASIC.SYSTEM, the
  program's own overlays and the everyday file tools, and EXTRA2 carries the
  disk and block surgery: BLKVIEW, BLKEDIT, DISASM, SYNC, MOVE, DISKCMP,
  UNDELETE, RESCUE, TREE and MKIMAGE. A new overlay lands on EXTRA, which is
  the one with room left. The XL edition is unchanged and needs neither.

- Fixed: a raw page eight bytes short was refused. `page_size` knew 8,184 as
  well as 8,192 for a single hi-res page but only 16,384 for a double one,
  so a 16,376-byte double hi-res -- what 816/Paint writes uncompressed, the
  last screen hole dropped -- answered "not an image". It now takes 16,376
  too, and the second plane may come up eight bytes short like the first.
  Checked against the file itself in the emulator: both banks byte for byte.

- Fixed: the text reader wrote "Back" over the top left of every file. Its
  key bar is laid down from column 52 and "SPC Next,B Prev,R First,ESC Back"
  is 32 columns wide, so it ran to column 83; conio carried the four columns
  past 79 round to the start of the screen. It now reads ",ESC" like the
  BASLIST and AppleWorks bars, 28 columns, ending at 79. It was the only bar
  of the twelve that overflowed.
- DGRVIEW recognises what tools actually write: ProDOS auxtype $0400, the
  address of the text page, which is what bmp2dhr puts on its lo-res output.
  Testing the size for equality would have refused the very files it is for
  -- .SLO is 962 bytes and .DLO 1,922, not 1,024 and 2,048. A file larger
  than 1,024 is two halves of half its size, the auxiliary one first.
- DGRVIEW also reads a header this project proposes, since no signature for
  lo-res exists anywhere: `'D' 'G' 'R'` and a version byte, then the width
  and height in pixels, then a flag saying whether the auxiliary half is
  present. The picture follows as rows of forty bytes WITHOUT the screen
  holes -- 1,928 bytes for 80 x 48, 968 for 40 x 48, and a file that says
  what it is instead of being guessed at by its length.

- Added the DGRVIEW service overlay: lo-res and DOUBLE lo-res pictures, the
  mode whose memory is the text page rather than the graphics page, which
  A2FC could not show at all. 1,024 bytes is a 40 x 48 screen, 2,048 a
  80 x 48 one -- the auxiliary half of the page first, then the main half,
  the order A2FC's raw DHGR files already use. Anything else is taken for an
  a2dgrx pixmap (one byte a pixel, the colour in the low nibble, the high
  nibble a mask that leaves the background alone when it is zero) and its
  width is asked for. It has to be asked: a2dgrx
  (https://github.com/iolo/a2dgrx) is a drawing library, not a file format --
  its sprites carry no header, no signature, no dimensions and no ProDOS
  type, and are `.byte` directives assembled into the program rather than
  files on a disk. So DGRVIEW decides by size, and asks when size is not
  enough.

- Added the MOVE service overlay: a file or a whole directory changes
  directory WITHOUT being copied, on the same volume, by rewriting its
  directory entry -- a tree of four hundred blocks moves in the time it takes
  to write three. ProDOS 8's RENAME cannot do this (asked to rename
  /VOL/A/X to /VOL/B/X it answers $40, measured in the emulator, not
  assumed), so the entry is carried by hand: its header pointer, a moved
  subdirectory's own parent pointer, parent entry number and entry length,
  and the live-entry count of both directories. The target entry is written
  first and the source cleared after, so an interrupted move leaves the file
  listed twice -- which VOLINFO reports and which loses nothing -- rather
  than in no directory at all. Every block written is read back and compared.
  Across two volumes no entry can point from one to the other, so there MOVE
  falls back to what a move has always been: the file is copied, read back
  and compared in full, and only then removed -- a move that loses the file
  to a short copy is not a move. That fallback takes a file; a whole tree
  across volumes is still what V walks and copies.
  Refused: a directory into its own subtree, a name already taken, a target
  with no free entry, and anything in the program's own A2FILE directory.
  One entry per run, the one under the cursor: a big overlay's code covers
  the entry tables, so the tags -- indexes into them -- can no longer be
  turned into names.

- Added the BLKEDIT service overlay: a block editor beside BLKVIEW's
  read-only explorer. Hex cursor on either half of a block, hex digits
  change a byte, T and Y follow the block number under the cursor (the
  consecutive pair ProDOS writes everywhere, or an index block's split low
  and high halves), and W writes the block back. Nothing reaches the disk
  until a byte was changed AND the word ERASE was typed in full; the block
  is then read back and compared byte for byte, so a drive that accepts the
  write and keeps its old contents is reported as a failure. The volume A2FC
  runs from is refused. Leaving a changed block asks first.
  BLKVIEW is untouched and stays strictly read-only: it had nineteen bytes
  left in its window, and the tool one reaches for to inspect a suspect disk
  is better off unable to write to it.
- `struct Source` gained `source_write`, the mirror of `source_read`: one
  normalized block back to a device or into a .PO/.HDV/.DSK/.DO/.2MG
  container, the DOS 3.3 sector order undone the same way it is applied.

- Added the PACKFOT service overlay: packed ProDOS `$08` pictures, auxtype
  `$4000` (hi-res) and `$4001` (double hi-res), are decoded from Apple's
  PackBytes and shown full screen. The two planes of a double hi-res are one
  stream, so a packet straddling them is carried across the bank move; the
  auxiliary plane costs the `/RAM` volume, which is rebuilt and reported.
  Verified in POM2 against a reference decoder, byte for byte, in both banks.
- Fixed: a `$08` file that was not a raw page was announced as an image and
  then refused with "not an image", with no fallback at all -- not even the
  hex viewer every other unknown type gets. `looks_like_image` now claims a
  `$08` only when it holds a raw page.
- Fixed: EXTASIE could never read a single byte. `have` is a byte and a
  256-byte read cast to one is zero, so the decoder saw an end of file at the
  first byte and every picture answered "Extasie image truncated".
- Fixed: EXTASIE was declared a small overlay on 65C02 builds while writing
  the whole graphics page, which holds the two panels' entry tables. From the
  `!` menu it wrecked both panels and left the screen stuck on hi-res.
- Fixed: an empty overlay menu let the page keys walk to entry 255 and the
  letter search divide by zero.
- Fixed: a mouse click that A2FC had already acted on was refused as a write
  to a read-only disk image.
- Fixed: a DOS 3.3 catalog name of thirty blanks left the name unterminated,
  handing the panel whatever followed it in memory.
- Fixed: `=` carried a path across to the other panel without the file system
  that goes with it, so a panel left inside a disk image read the new path
  with a stale image length.
- The plugin ABI is version 3: `api->ram_format` rebuilds the ProDOS `/RAM`
  volume, which any overlay writing to the auxiliary bank destroys.
- IDENT tells a raw FOT from a packed one (`$4000`, `$4001`) and from LZ4FH
  (`$8066`) by its auxtype, instead of calling them all "Hi-res picture".

- Added the EXTASIE service overlay: ProDOS `$F2` Extasie/Chat Mauve streams
  are decoded from their original count/repeat format and shown as HGR on
  every Apple II. On 6502 builds, selecting an `$F2` entry and pressing `I`
  opens it directly; 65C02 builds expose the same viewer from the plugin menu.
- The English manual is now ten pages and includes a credits/inspirations
  list with URLs for external projects, authors and adapted code lineage.
- DELETE now expands its progress total as directory contents are discovered,
  so recursive deletions show each file and directory instead of remaining at
  a top-level count.
- SEARCH now polls ESC between files during long scans. Already tagged files
  remain tagged and the completion message reports the partial count.
- The built-in TEXT reader adds R to return directly to its first page.
- BASLIST and the AppleWorks reader now also accept R to return to their first
  rendered page after paging.
- Their key bars now advertise the R shortcut alongside the existing page
  controls.
- GOTO also rejects relative paths, empty components, trailing slashes and
  ProDOS path components longer than 15 characters before showing favourites.
  Malformed entries therefore cannot be selected as delayed jump targets.
- GOTO refuses configuration files over 2000 bytes, paths over 63 characters, embedded NUL bytes and more than nine favourites. It reports the invalid configuration before offering actions, preventing truncated paths or partial lists from being used or saved over the original.

- HEX adds G to jump to the page containing a seven-digit hexadecimal file offset, R for the first page and E for the last. Out-of-file offsets are reported without moving; cancelling preserves the position and empty files remain bounded. CPU addresses remain a separate 16-bit concept, and the reader still fits the small overlay on both CPUs.
- DISASM now accepts seven-digit file offsets with G for XL files; its load
  address remains a four-digit 16-bit CPU address.

- GOTO reads favourites from CR, LF or CRLF configuration files, including mixed line endings, blank lines and a final line without a terminator. Files edited on a host no longer merge favourites or retain stray line-feed bytes in paths; saves keep the native CR format.

- MDVIEW prefers valid UTF-8 over its Apple II high-bit heuristic, fixing mostly non-ASCII text. An initial UTF-8 BOM is skipped so Markdown headings work, including after R restarts. Detection handles sequences split at the 2 KB read boundary; accents remain transliterated and unsupported characters display as question marks.

- MDVIEW no longer repeats earlier text when a single logical line wraps beyond 255 screen rows. Wrapped-row positions use 32-bit counters, preserving forward/back navigation and restart for very long lines without changing the 64-page history.

- IDENT recognizes valid UTF-8 sequences of two, three and four bytes, including BOM-prefixed and non-ASCII-only text. It rejects overlong encodings, surrogates and out-of-range sequences as UTF-8, while retaining Apple II high-bit text detection. A sequence split by the 512-byte sample boundary is handled without confusing its bytes with line endings or controls.

- MDVIEW continues beyond page 64 using a rolling history of 64 page starts. Up revisits retained pages, R restarts at page 1, and page numbers no longer wrap at 255. Markdown fence state is preserved across the history boundary.

- GOTO saves through an exclusively created GOTO.TMP, closes it successfully before moving the old list to GOTO.BAK, and restores the original if installation fails. Existing recovery files are never overwritten; failed rollback retains both files and reports recovery instructions.
- GOTO adds M to move a favourite to a chosen numbered position while preserving the order of the others. ESC or unavailable positions cancel; choosing the same position does not rewrite the file. Saving favourites now checks short writes and close errors.
- GOTO adds P to open a directly typed absolute ProDOS directory path without saving a favourite. Supports lowercase input, Delete/Left editing and trailing slashes; invalid paths or ESC preserve the active panel. Input is bounded to 63 characters.
- CRC displays tagged-file checksums in pages of 20 instead of scrolling earlier results away. A key continues; ESC returns to the panels without processing the remaining files. Exact multiples of 20 finish without an empty page, and tags are preserved.
- DATE rejects impossible calendar dates (including non-leap February 29 and day 31 in 30-day months), preserving the previous system date/time. Leap years from 1940 through 2039, including 2000, remain supported.
- FIND adds V on text results to browse every occurrence with hexadecimal byte offsets and excerpts, including overlapping and cross-read matches. N/Space continues by 20; ESC restores the selected result and pending search page. Setup code now shares the future directory queue to preserve the resident memory budget.
- FIND adds optional ProDOS type and inclusive modification-date filters (TAB, then T/D; A clears). Filters combine with name/content searches and persist across result pages; invalid dates are rejected and cancelling an edit preserves the previous range.
- FIND continues with N beyond the first 20 matches, preserving traversal state and showing cumulative result ranges. A lookahead avoids empty pages at exact multiples of 20. Fixed skipped late subdirectories and the 8-bit directory-position limit in content search; unreachable/overlong paths and queue limits are reported.

- DISASM can export a text listing from the current offset to EOF, with the chosen CPU/load address, source path, offsets and raw bytes. New files are created exclusively in the other panel; errors/cancellation retain partial output and returning to the viewer preserves its position.

- Added DISASM on EXTRA and XL for both CPUs: read-only BIN/SYS disassembly, selectable 6502 or 65C02 (including Rockwell/WDC extensions), instruction-aligned pages, file-offset jumps and load-address override. Unknown or truncated instructions remain visible as data bytes; short reads are reported. Opcode tables adapted from cc65 da65 (notice retained in source).

- Extended BLKVIEW with four-byte hexadecimal search, overlapping/cross-block matches, find-next and bounded block extraction to a new binary file in the other panel. Extraction normalizes PO/DSK/2MG order, refuses existing names and writes device copies to another volume; cancellation/read/write errors retain partial output.

- Fixed TREE falsely reporting an incomplete XL root scan despite correct totals: ProDOS GET_FILE_INFO returns volume allocation for a root directory. TREE and SYNC now count its linked directory blocks, with bounded reads and error/cancellation handling.

- DISKIMG automatically reads back every block written to a device, stops at the first mismatch/read error and reports its block number. Single-drive copy prompts name the source volume and slot/drive; readback needs no additional swaps.
- VERIFY reads tagged files, skips tagged directories and reports processed files and read errors. Escape interrupts files as well as volumes, preserving the tags. Single-file results now use the same compact summary as batches.
- VOLINFO lists selected-file data/index/master/extended blocks, and exports its scan and file block list as a new text report in the other panel. Existing names are never overwritten; interrupted/error reports remain visibly partial. Lost-block counts are explicitly unconfirmed after incomplete scans.
- Added read-only BLKVIEW on EXTRA and XL: device and PO/DSK/DO/2MG/HDV image blocks, hex/ASCII, explicit directory/index interpretations, paging and four-digit hexadecimal block selection.
- The 0.7.6 source builds keep separate CPU families: 43 overlays on XL, a 42-command shared catalog, DSK floppies and versioned filenames. Updated the eight-page English manual with the current two-panel screenshot.

## [0.7.5] - 2026-09-09

- Added six service overlays on EXTRA and XL for both CPUs: UNDELETE recovers deleted ProDOS file candidates to another volume; DISKCMP compares volumes and PO/DSK/2MG images; MKIMAGE creates formatted data images; RESCUE extracts readable data with retries and a missing-block log; SYNC copies missing/newer files recursively; TREE shows cumulative directory sizes.
- Recovery leaves source volumes unchanged. UNDELETE recognizes index halves swapped by ProDOS DESTROY and refuses ambiguous or reused blocks. SYNC reads back temporary copies before replacing older files, with rollback backups. DISKCMP supports exact single-drive comparison with prompts naming the expected disk and slot/drive.
- Added VOLINFO to BOOT and XL: free space, fragmentation, a paginated bitmap, shared/lost blocks, used blocks marked free and count checks. Incomplete scans never present a lost-block verdict.
- Replaced FORMAT.SYS with FORMAT.PLG, returning directly to the panels. Kept ERASE confirmation and protection of the running program. Physical Disk II formatting preserves resident memory, including on errors, and explicitly warns that /RAM is cleared.
- Published separate 6502 and 65C02 BOOT/EXTRA 140 KB floppies and complete XL 2mg images. Each XL has all 42 overlays, BASIC.SYSTEM, DEMO and IMGHGR; BOOT and EXTRA share a 41-command catalog. The two CPU families never share an EXTRA disk. Missing-disk prompts support selecting drive 1 or 2 and returning the source disk after an overlay loads.
- Added fifteen other service overlays: TXTCONV, DATE, VERIFY, TAGPAT, VOLNAME, WIPE, FIXTYPES, GOTO, FIND, CRC, IDENT, MDVIEW, RENAME, IMGCONV and BOOTBLK. See the [manual](docs/MANUAL.md#more-tools-in-the--menu) for their controls and limits.
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
