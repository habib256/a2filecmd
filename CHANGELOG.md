# Changelog

Changes in upcoming and published releases. See the [README](README.md) for features,
downloads and installation.

## [Unreleased]

### Return opens SQueezed files, ACU archives and Business BASIC
- **Return** on a name ending in `.QQ` or `.ACU` opens UNSQ, which extracts
  the archive into the other panel as **!** already did; on a `.BA3`, or on a
  file of ProDOS type `$09`, it opens BASLIST and lists the Apple ///'s
  Business BASIC. BASLIST reads a `.BA3` as Business BASIC whatever type the
  file arrived with: a program brought from a host keeps its name, not its
  type, and read as Applesoft the same bytes are another program.
- Room in OPEN first: the classification overlay had **4 bytes free on 6502**
  and a new suffix does not fit in four bytes. `ends` merged into `by_suffix`
  (split in two, the length of each suffix was measured twice) and the tail of
  `file_viewer` -- the ProDOS types that name a viewer on their own -- became a
  table, fourteen bytes of code per type replaced by two of data. OPEN goes
  from 4 to 28 bytes free on 6502 (26 to 43 on 65C02) **with** the three new
  suffixes, the `$09` type and two names in `media_names` already paid for.
- `tools/test_file_viewers.py` runs the real classifier on both editions for
  the new routes and for the names that must not match them (`A.QQX`, `.BA3`
  alone, `A.BA33`), and checks the music album still skips them.
  `bench/squeeze.py` opens a `.QQ` with Return under POM2 and reads back what
  UNSQ wrote, then lists the same Business BASIC program twice -- by T on the
  `$09` file, by Return on the `.BA3` copy typed `$06` -- against
  `tools/busbasic_ref.py`.

### AppleWorks spreadsheets are shown as sheets (FILES, XL)
- AWDATA draws a `$1B` file as a grid: the column letters on the first line, a row of the file a line, each cell in its own column at the width AppleWorks saved for it (header bytes 4-130). Values sit against the right of their column, labels from the left, and a label wider than its column runs into the next ones until a cell writes over it -- so a sentence typed across a row reads as a sentence instead of as twenty three-character cells, one per line. A formula cell shows what the sheet shows: the display string AppleWorks saved, or the result.
- **&lt;** and **&gt;** (or the horizontal arrows) move one screen of columns, **Space**/**B** page through the rows, **R** returns to the top left. **F** swaps to the cell-by-cell view -- a cell a line with its formula spelled out -- and back; that view is where a formula can be read.
- What the grid cost had to come from the same window: the page marks are 16-bit offsets, 42 of them (2,688 records of a data base, 882 rows of a sheet), and a sheet borrows the data base's category names for its column widths. `tools/awdata_ref.py` gained `ss_rows`, `ss_screen` and `ss_next_col`, `tools/test_awdata.py` compares every grid page, the two views and the column windows, and `bench/awdata.py` reads them back from POM2 on both processors.

### Apple Pascal volumes are read (PASCAL, DISKTOOLS and XL)
- **! -> Disks -> PASCAL**, with a disk image under the cursor and a ProDOS directory in the other panel, extracts every file of an Apple Pascal (UCSD) volume into it. A2FC could read ProDOS and DOS 3.3; this is the third filesystem it opens, and the first foreign one it reads out of an image.
- Pascal is the one that fits: two boot blocks, a flat directory of four blocks at block 2, and every file a single contiguous run. The directory is 78 entries of 26 bytes -- first block, the block after the last, kind, name, and how many bytes of that last block are used, so the length is exact and not a multiple of 512. `tools/pascal_ref.py` is the reference and the fixture generator; `tools/test_pascal.py` runs the real overlay over the images it makes and compares every extracted file with what that reference reads out of the same image.
- Nothing is written to the image, ever. What is written follows the file-service contract: created only under a free name, written, closed, **read back against the image a second time**, and removed if anything fails. A directory that does not explain itself -- a volume name with a space in it, a file whose last block precedes its first, two files claiming the same blocks, more entries than a directory holds -- is refused before a single byte comes out, and the test breaks the directory seven ways to check it.
- A Pascal name becomes a ProDOS one; a code file arrives as `$02 PCD`, a text file as `$03 PTX`, a data file as `$05 PDA`. A `.TEXT` file comes out as it lies on the disk, header and page padding included: that format is a conversion, not a reading.
- The overlay reads **one directory entry at a time** rather than holding all four blocks. Holding them left eighteen bytes of window free, which is no margin at all; reading the twenty-six bytes it needs, and the second block when an entry straddles two, leaves 1,697.
- **It reads real disks.** Four Apple Pascal disks from Asimov (`images/programming/pascal`) give up their volumes on the first try -- FORT1, TGP, TK and EXPRESS, 280 blocks each, with `SYSTEM.PASCAL`, `SYSTEM.FILER`, `SYSTEM.APPLE` and the rest -- and all **46 files come out byte for byte identical** to what `tools/pascal_ref.py` reads out of the same images: the shipped overlay C against an independent reading. The fifth disk of the five tried, `PASCAL.BOOT.do`, is refused and should be: its first bytes read `SOS BOOT 1.1` and its block 2 is a ProDOS volume header, which A2FC opens with Return already.

### Writing into an Apple CP/M volume (CPMW, DEVTOOLS and XL)

- The mirror of CPM, with the same two panels and the same contract: **! -> Disks -> CPMW** puts every file of the ProDOS directory opposite into the CP/M volume under the cursor, and a name already there is skipped and counted, never overwritten. `src/plugins/cpm_fs.h` holds the volume layer both share.
- **A CP/M sector is half a ProDOS block.** Every write is therefore a read-modify-write, and the other half belongs to a file that has nothing to do with this one: it is copied out before the write and compared after, along with the sector itself. Losing it would eat a neighbour, silently. `tools/test_cpmw.py` and `bench/cpmw.py` both write a file next to two others and read those two back.
- **CP/M has no bitmap.** What is in use is whatever the live directory entries claim, which means an entry is the only thing that makes a block belong to anyone -- and that the data can go in first, into blocks nothing claims, with the volume none the wiser. The entry is one 32-byte slot in one sector, one write, and that write is the instant the file exists. A cut before it leaves the volume exactly as it was.
- **The sector order is still not guessed**, and that now has a second consequence: an **empty** volume is refused. With every entry free there is nothing to tell one candidate order from another, and writing through the wrong one would put the file where CP/M will never look for it. Refusing is the only honest answer.
- **One extent, so 16 KB at most, and the reason is the window, not safety.** The format documentation is clear that CP/M puts no ordering requirement on extents, so writing them from 0 upwards would leave a run of 0..k after a cut and a file that reads as a clean truncation. What does not fit is the code -- a free slot found per extent, the data looped across them -- in an overlay with a hundred-odd bytes left. A bigger file is skipped, and the roadmap carries the measurement instead of a story. A name that cannot be an eight-and-three is skipped too, not mangled. There is no date to carry over either: a CP/M 2.2 entry has no date field at all.
- Margin left in the window: 163 bytes on 6502, 115 on 65C02, after the twin buffer was made to borrow whichever of the two sector buffers is idle and the two directory scans -- one for the name, one for the free slot -- became one.

### Writing into an Apple Pascal volume (PASCALW, DEVTOOLS and XL)

- The mirror of PASCAL, and it wants the same two panels: the image under the cursor, a ProDOS directory opposite. That one extracts every file of the volume into the directory; **! -> Disks -> PASCALW** puts every file of the directory into the volume, under the same contract -- a name already in the volume is skipped and counted, never overwritten. `src/plugins/pascal_fs.h` now holds the volume layer both share.
- **Where a file may go is the whole design.** A UCSD file is one contiguous run, so there is no bitmap and no index block; there is a placement rule, and this overlay keeps the strict form of it: a new file goes after the last block any file uses, never into a gap between two of them. The Apple Pascal filer can fill those gaps because it knows how to shift the files that follow, and shifting someone else's files is not a thing to do unasked. A volume whose free space is all in the middle is refused with the room it has; K(runch in the filer moves it to the end.
- The order per file is data, then entry, then count. The data blocks land past the last file, where no entry names them; the entry goes at index count+1, past the file count, where no reader looks; the count is written last and that single write is the instant the file exists. When the entry and the count share block 2 -- the first nineteen files -- there is one write and no window at all.
- `tools/test_pascalw.py` (in `make test`) breaks every write in turn against disposable images, with `tools/pascal_ref.py` as an oracle that knows nothing of the overlay. **It found two real defects.** The file count was written four bytes too far along: a UCSD directory has no chaining header, its entries start at byte 0 of the block, and the ProDOS convention put the count inside the volume name. And a directory write that landed *wrong* was reported as "the volume is whole" while a corrupt block sat on the disk -- the old bytes are put back now, and when that fails too the message says so instead.
- The UCSD kind written is the exact inverse of the one PASCAL reads, so a file taken out and put back keeps it: code for `$02`, text for `$03`, data for `$05`, untyped for anything else. A ProDOS TXT file does **not** become a UCSD textfile: that format carries a 1,024-byte header and page padding, and one written without them would be a file the Pascal system reads as text and no reader could use.
- **The date crosses over.** A UCSD entry carries a modification date -- year in bits 9-15, day in 4-8, month in 0-3, where ProDOS keeps year in the same place but month in 5-8 and day in 0-4 -- and a month of zero means no date at all, which is what a zero word wrote at first. It is the source file's own date now, shuffled byte by byte: written on 16-bit values the same three lines cost 227 bytes of a window that had 364, and read straight out of the entry the walk is standing on rather than passed as a fifth argument. Margin left: 168 bytes on 6502, 119 on 65C02.

### Apple CP/M volumes are read (CPM, DISKTOOLS and XL)
- The fourth filesystem A2FC opens, and the second read out of an image. **! -> Disks -> CPM** extracts every file of an Apple CP/M disk into the ProDOS directory opposite, under the same contract as PASCAL: created under a free name, read back against the image, removed on any failure, and the image never written to.
- A CP/M disk keeps three tracks for itself, then 64 directory entries of 32 bytes and blocks of 1,024. One entry is one extent of 16 KB, so a longer file has several, ordered by `EX + 32 * S2`; CPM puts them back in order and takes its length from the record count of the last. `tools/cpm_ref.py` is the reference and the fixture generator, `tools/test_cpm.py` runs the real overlay over its images -- a file spanning more than one extent included.
- **The sector order was measured, not chosen.** CP/M reads the Apple's 256-byte sectors through a skew of its own and the published tables disagree, so the first three the overlay was written with were all wrong -- and it refused every real disk rather than read one wrongly, which is the behaviour it was built for. The right table came from the disks themselves: on images from Asimov, the eight sectors of a directory were found by looking for 32-byte entries that read as entries, and they fell on 0, 6, 12 with the empty tail on 3, 5, 9, 14 and 15. That is `{0, 6, 12, 3, 9, 15, 14, 5, 11, 2, 8, 7, 13, 4, 10, 1}`, and the source records where it comes from.
- **It reads real disks.** `CPM2.2(56k).dsk` gives its 19 files and `CPM MAG #01.DSK` its 8, and all 27 come out **byte for byte identical** to what `tools/cpm_ref.py` reads out of the same images -- the shipped overlay C against an independent reading, on disks neither of them was written for. Two other disks of the four tried are refused: their directories begin elsewhere, and being refused is what should happen to them.
- The overlay keeps trying its orders and keeping the one whose directory explains itself -- user numbers and names in range, no blank name, record counts of at most 128, block numbers inside the disk and claimed once each. `tools/test_cpm.py` proves the mechanism by reading fixtures written in each order without being told which.

### DOS33W: delete and rename on a real DOS 3.3 disk (DISKTOOLS, XL)
- With a real DOS 3.3 disk open in the active panel and the cursor on a file, **! -> Disks -> DOS33W** offers **D** to delete it and **R** to rename it, each after a question naming the file and the drive. Until now A2FC could read a DOS 3.3 disk and copy a file onto one, and nothing else; these are the first two verbs that change what is already there.
- The file is identified by the track and sector of its first track/sector list, which the panel keeps, never by the name on screen: that name is a ProDOS-shaped copy of the DOS name (lower case raised, anything but a letter or a digit turned into a period, fifteen characters at most), so two DOS files can wear one panel name and neither can be found back by it. The link is exact and unique -- two entries sharing it would have failed the audit with the volume.
- Nothing is written before `audit()` has explained the whole volume -- the catalog chain, every track/sector list, the bitmap against the sectors actually in use -- and the same audit runs **again after the question is answered**, because the drive door is open while it waits. A locked file is refused, as DOS's own DELETE and RENAME refuse it; so are a write-protected disk and a controller that is not a standard Disk II.
- Deleting writes the catalog entry first and the bitmap after. A cut between the two leaves the file's sectors marked in use with nothing pointing at them: space lost, which FIXIT names, and no more. The other order would leave, for as long as it lasted, a visible entry pointing at sectors the next file written is free to take. When the bitmap write is the one that fails, the message says the file is gone and its sectors stay in use -- never "nothing deleted".
- **Replacing an existing DOS 3.3 file is in, after all.** It was written, measured, taken back out for want of 46 bytes, and brought back when those bytes turned up somewhere unexpected -- see below. DOSREPL is its own overlay (DISKTOOLS and XL): the new copy goes to sectors of its own, is read back, and only then does one catalog sector write switch the name to it. The old file is whole and readable until that instant; the disk must therefore hold both copies at once, and says so when it cannot. `tools/test_dosrepl.py` breaks every write in turn and checks the old bytes are still there. Margin left in the window: 172 bytes on 65C02, 74 on 6502. `bench/dosrepl.py` then drives the real thing in POM2 against a disposable floppy in drive 2 -- an Applesoft and an 8 KB binary replaced under their DOS name, the old sectors back in the bitmap, the neighbour untouched, and a disk one sector short of holding both copies refused.
- The bytes came from the audit, but not by shrinking it -- four attempts at that all cost more than they saved, and the roadmap lists them so nobody tries again. They came from **how the replaced file's sectors are remembered**: walking its track/sector chain a second time to free it cost 330 bytes of code, while letting `claim()` mark them in a 70-byte map as the audit already walks them costs 154 fewer bytes of code and ends the overlay 96 bytes lower. DOS33W's delete uses the same map.
- Where it did *not* fit: inside DOSWRITE, 632 bytes over; inside DOS33W with the copy engine, 1,987. The engine itself came out too -- `src/plugins/dos33_copy.h` holds `allocated`, `source_length`, `chunk`, `end_source`, `lists_io`, `transfer` and `verify_source` -- and both overlays came out of that move at exactly their old size, 7,145 and 7,178 bytes. Three shapes were then built and measured, and none of them fits the `$1B00-$3FFF` window: inside DOSWRITE, 632 bytes over; inside DOS33W with the engine, 1,987; as an overlay of its own, 46 bytes over **on the 6502 toolchain** and fitting on the 65C02. The last one was close enough to be tempting -- messages cut to the bone, the read-back buffer halved from 512 bytes to 256, `free_chain` rewritten to walk with a pointer -- but the floppies are 6502, and an overlay with four bytes of margin is one edit away from not building. The roadmap has the table and what to try next.
- `bench/dos33w.py` plays the two verbs under POM2 on a disposable DOS 3.3 floppy in drive 2, and reads the floppy back at every step: the locked file refused, the question declined, the delete whose sectors come back to the bitmap and whose entry keeps its track where UNDELETE reads it, the rename that keeps the bytes and the sectors, a name already taken refused. Thirteen checks. Each of them ejects the disk first, because POM2 only writes the floppy back to the host on eject -- read without ejecting, a "nothing was written" check passes whatever the program did.
- `src/plugins/dos33_fs.h` now holds the DOS 3.3 volume layer -- sector I/O read back, the bitmap, `audit()` -- shared with DOSWRITE, and `dos33_sense.inc` the write-protection sensing. `doswrite.PLG` came out of that move **byte for byte identical** in both editions. `tools/test_dos33w.py` (in `make test`) runs the real overlay over disposable disks: the delete frees exactly that file's sectors and no others, the deleted entry keeps its track where UNDELETE reads it, a refusal leaves the image byte for byte as it was, and a read error, a half-written sector or a sector that reads back different never lets the program claim more than it did.

### Writing into a ProDOS image (IMGPUT, DISKTOOLS and XL)

- A2FC could open a ProDOS image as a folder and take files out of it. **! -> Disks -> IMGPUT**, with the image open in one panel and the cursor on a file in the other, puts one back: the third write path of this release, and the first time the program is a **second ProDOS writer** -- ProDOS itself is not doing the writing, so nothing checks the work. Three structures have to agree afterwards: the volume bitmap, the directory entry, and the file's own index block.
- The order decides what an interruption costs, and it is the one whose cut is cheapest. The data blocks and the index block go first, into blocks the bitmap still calls free, each read back and compared: a cut there changes **nothing at all**, because nothing yet points at them and the bitmap never said they were taken. The bitmap is written next -- from there the blocks are ours -- and the directory entry last, one block, one write, the entry and the file count together. A cut between those two loses their space and no more, and the message says so instead of calling the work done.
- `tools/test_imgput.py` (in `make test`) runs the real overlay against disposable images and breaks every write in turn -- failed, half-written, and read back different -- then reads the image with `tools/prodos_read.py`: before the bitmap the image must come back byte for byte as it was, after it an entry must never name a block the bitmap calls free.
- **It found one.** The bitmap page was written without being read back, so a page that landed wrong went unnoticed -- and that is the single failure that gives a corrupt volume rather than lost space: the entry names blocks the bitmap calls free, and the next file written is handed them. It goes through the same verified write as everything else now.
- The window was the hard part: four 512-byte buffers overflowed it by 1,638 bytes. The bitmap page shares the directory buffer -- they are never wanted at the same instant -- and the read-back of a write goes into whichever buffer is idle, which is why `put_verified` is told where to put it. One walk of the bitmap now both proves the room and chooses the blocks, filling the index block with them, so the bitmap is not read again until it is written. The last 520 bytes came from compiling out a path this overlay can never take: `IMAGEIO_NODEVICE` leaves out `unit_of`, `readblk` and `writeblk`, dead code for an overlay that only ever opens a file. Margin left: 277 bytes on 6502, 270 on 65C02.
- What it refuses rather than guess: a file needing a tree (above 128 KB), a directory with no free slot, an image ProDOS will not open for update, and an image whose header or bitmap does not explain itself. The image is asked again after the question is answered, because it may have been swapped while it waited.
- **C does it too.** Copying into a mounted ProDOS image is the natural gesture, and until now it met "the other panel is read-only" -- a message that stopped being true when IMGPUT arrived. **C** with the image opposite now runs IMGPUT: one file, the one under the cursor, tags not read on this path, as the copy onto a DOS 3.3 disk already worked. **V** keeps the old refusal, because a move would have to delete the source once the image holds the file and IMGPUT deletes nothing. 51 bytes of the resident on 6502, 53 on 65C02.
- **And `bench/imgput.py` found what the host test could not.** The overlay read the volume header with a *file entry's* offsets -- a volume keeps its bitmap pointer, total and file count at 0x23, 0x25 and 0x21, where a file keeps its auxtype, its modification date and its header pointer. The host test never saw it because its image was built here, by hand, with the same wrong offsets: the fixture and the code shared one assumption, so twelve checks passed while the overlay refused every real image. The fixture now comes from `tools/mkvolume.py`, a writer that knows nothing of the overlay. The bench mounts a real 280-block image in the right panel, copies two files in from the menu, and reads the image back out of the hard disk at the end: exact bytes, type and auxtype, the file that was already there untouched, the file count raised, and every block an entry names marked used in the bitmap. 18/18 on both processors.

### A tagged directory says so
- Space, Ctrl-T and **\*** have tagged directories since 0.8.6 -- C, V, D and the marked MOVE walk them -- but the panel line never drew the mark, so tagging one changed nothing on screen. A directory's line now carries the star and the lock in columns 15 and 16, the two columns a file uses, and `<DIR>` still stands where a file shows its type. A locked directory shows its **L** for the first time.
- The slash after the name stays. Unifying the line on name-then-marks dropped it at first, and `<DIR>` did seem to say the same thing -- but eleven checks across seven benches read `NAME/`, and only two of them run in the plugin suite, so the suite reported 25/28 while five more benches were broken. A fifteen-character name pushes the two marks one column right, which is what the old line did too. `tools/test_display.py` renders the real `draw_entry` and compares the four lines (tagged or not, locked or not, up to a fifteen-character name) character by character, that case included.

### The LZC reference, and what UNSHRINK will never read
- `tools/lzc_ref.py` decodes and writes UNIX `compress` streams, which is what a NuFX thread of format 4 or 5 holds, header included. It is in `make test`: its own output is byte for byte the one `/usr/bin/compress` writes until the table freezes, and it reads back every stream that tool produces at 12, 13, 14 and 16 bits -- including the CLEAR codes `compress` sends once its table is full and its ratio falls, which a fixture has to be sixty kilobytes of noise to reach. The 6502 decoder is still to write, and the roadmap says where it would have to live.
- Two of the three formats that line asked for will not come. **Format 5, 16-bit LZC**, is out of reach of the machine, not of the budget: its table is 65,536 two-byte prefixes and as many suffixes, 192 KB on a 128 KB Apple. Only a format-5 thread whose `compress` header declares twelve bits or fewer can be decoded. **Format 1, SQueeze**, is left: nufxlib, the library that implemented it, records that the format has never actually been used and that neither P8 ShrinkIt nor II Unshrink read it correctly, and no archive in the sample corpus carries one. UNSQ already reads standalone SQueezed files.

### Browsing pictures no longer flashes the panels
- Between two images of an album (Left/Right on an HGR or DHGR picture), the screen carries the name being loaded and nothing else -- the transition the media overlays already gave. The panels are still read again, because the picture ate their table, but they are not drawn until the album is left. `tools/test_raw_transition.py` runs the real loop and refuses a redraw between two images.
- **And the same on the way in, for every picture viewer.** Opening a viewer left the two panels on the air for the whole of the first decoding, with `Loading NAME...` alone on row 22; only the next picture, reached with an arrow, got a screen of its own. An album that starts on the panels and then never shows them again reads as a flash, which is what it was. The screen now carries the name being read from the moment the viewer opens, here as between two pictures: `loading_screen` is one function, called in both places -- by the raw HGR/DHGR viewer, and by `overlay_run` for the ten specialized ones (Extasie, PACKFOT, 816/Paint, DGRVIEW, FONTVIEW, LZ4FH, PRINTSHOP, Purplesoft, Arlequin, MacPaint). Only the first picture of a session: a neighbour already has its name from the transition, and the three music viewers clear the screen themselves to write their credits.
- `tools/test_raw_transition.py` checks the screen before **every** decode of the raw album, its first as much as its neighbour's, and `bench/open_images.py` reads the text page under POM2 while each viewer is up -- it holds the name alone, where it used to hold both panels. DGRVIEW is the one exception, and not a lapse: its picture *is* the text page, so what the page holds once it has drawn is the picture.
- The two fixes together left the resident better off than they found it: MAIN goes from 457 to 465 bytes free (856 to 862 on 6502) and the language card from 60 to 73 (51 to 64), because the row-22 `cprintf` and the `sprintf` that built a directory name with its slash were both code of their own.

### The build says only what it cannot help saying
- The compiler printed 505 warnings, none of them real, which is the same as printing none: `#pragma warn (unused-param, ...)` now surrounds the service-stub blocks whose parameters belong to the ABI, `doswrite.c` says it ignores `writing` outside the image build, `unsq.c` and `unwrap.c` test their `FILE*` against zero instead of converting it, and a dead `.DO` suffix leaves IMGCONV. 193 remain, of two kinds that the stub idiom and the shared headers cannot avoid.
- `tools/check_warnings.py` (in `make test`, 7 seconds for both editions) builds everything and refuses any warning that is not one of those two kinds, in the files that may emit them. An unused parameter outside a stub block, a pointer used as an integer, a comparison that is always true: the build fails instead of hiding them in the flood.

### A hardware session is prepared, not improvised
- `docs/HARDWARE-CHECKLIST.md` is the sheet for the five 💾 lines of the roadmap -- the Mini on a II+, DOSWRITE on a real drive, FIXIT/REPAIR on a really damaged floppy, the auxiliary-memory pass above 4,096 blocks, the first IIgs boot: what to prepare, what to type, what must appear, what to write down.
- `tools/hw_media.py` writes the disks it needs -- a healthy 280-block volume, the same one broken in four places REPAIR can put right, a DOS 3.3 disk, and with `--big` a 20,000-block volume broken past the first bitmap page -- and prints the findings FIXIT must name, from the two oracles the benches use: the corruption declares what it produces, `prodos_check.py` reads it back, and a disagreement refuses the fixture. `tools/test_hw_media.py` keeps the images and the sheet in step.

### Every bench is played by the qualification
- `bench/all.py` holds the whole bench table: each of the ninety-three benches with the machine, the image and the fixtures it needs, in groups. `make qualify` plays it; `--list`, `--group`, `--only`, `--strict`, `--setup` and `--jobs` choose and prepare what runs, the port of each bench is read from its source so two benches never answer on the same one, and a step whose fixture is missing is a skip that names the command to build it. The `bench` job of `ci.yml` is now those groups, not a copy of the commands.
- `tools/test_bench_inventory.py` (in `make test`) refuses a bench file that is in no step, a step that names no bench, and a group the CI does not play. Before it, the release replay was twenty-five benches out of ninety-three: the seven written for the 0.8.9 formats were not among them, and nothing said so.
- The first full replay found `bench/plugin.py` broken at the published 0.8.9: the menu's category line has carried its count and description for a while, and the bench still compared the whole line with `Other`. It was in no CI step, so nothing said so. The check now reads the first word, and the SDK plugin bench is back to 4/4.
- It also showed that `bench/mb4c.py` cannot play its Mockingboard 4c half here: the card comes from POM2 sources newer than the emulator library the hosts are built against, so the bench passes its "absent card" checks (5/5) and then waits for a card that answers nothing. It is an emulator to rebuild, not a defect of A2FC; bench/README.md says so where the bench is described.
- The runner also refuses to trust a disk image older than `build/`: `make all` relinks without restaging the volumes, and a bench then boots the previous binary with the new overlays -- which looks like a crash, not like a stale file.

### The cc65 traps are read in every unit
- `tools/test_cc65_traps.py` compiles the resident and the fifty-four overlays in both editions and reads the assembly for the two shapes that have cost a release: a boolean built on the flags of a comparison a branch has already used (the DOS-order `.2MG` of 0.8.9) and a pointer whose high byte is set while its low byte is never written (DUET's page-aligned validator). `tools/test_flag_reuse.py` only ever read `src/a2fc.c`. A source rule refuses `(signed char)f()`, whose sign extension cc65 master drops.

### 190 bytes back in the resident
- MAIN goes from 276 to 466 bytes free on 65C02 (677 to 865 on 6502), the language card from 34 to 60, CATALOG from 30 to 224, with no change in behaviour: `empty_panel` and `fill_entry` replace the panel clears and entry fills written out in `read_panel`, `read_image_dir` and `read_dos33_panel`; the ten keys that only open an overlay and hand it their own letter become a table read in the `default` of the main switch (`main`: 1,980 bytes to 1,680); `file_at_cursor`, `open_row22` and `reread_both` each replace a sequence written out two to seven times.
- Written just above `read_dos33_panel`, those first two helpers landed **inside the CATALOG overlay** -- the `#pragma code-name (push, "CATALOG")` comes before it -- and the resident `read_panel` called them in an overlay's window. The link passed and MAIN claimed 172 bytes more than it had, exactly their size; the program would have worked only while CATALOG happened to be loaded. A function shared by the resident and an overlay goes outside the `code-name` blocks, and `ca65 -l` is what says which segment a `.proc` fell into. What else did not pay is in [docs/MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md).

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
