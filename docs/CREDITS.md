# Credits, inspirations and reused code

A2FileCmd is original GPL v3 software by **Arnaud Verhille**. The links below
identify the projects that shaped its interface, supplied technical references,
or contributed code patterns. They are listed so that the provenance of every
borrowed or adapted fragment is easy to check.

**cc65 — Oliver Schmidt**
Toolchain and Apple II startup code. `src/crt0.s` and `src/crt0_loader.s`
retain the V2.19 provenance notice; local loader changes are marked there.
URL: [cc65 repository](https://github.com/cc65/cc65) · [Apple II startup source](https://github.com/cc65/cc65/blob/V2.19/libsrc/apple2/crt0.s)

**Colin Leroy — a2tools / Ammonoid**
The serial virtual-drive glue in `src/vsdrive.s` follows the documented
a2tools approach; the source comment names the corresponding file and author.
URL: [a2tools repository](https://github.com/colinleroy/a2tools) · [Ammonoid releases](https://github.com/colinleroy/a2tools/releases)

**Jerry Hewett and Gary Desrochers — Hyper-FORMAT**
The Disk II ProDOS formatter descends from their public-domain routines,
carried by ADTPro and credited in `src/format.c` and `src/format_diskii.s`.
URL: [ADTPro source tree](https://github.com/ADTPro/adtpro)

**ProDOS 8 documentation**
File-system structures, MLI calls, allocation blocks and path rules follow the
published Apple II technical references.
URL: [ProDOS 8 technical information](https://prodos8.com/)

**A2Command**
The Apple II two-panel file-manager model and command-oriented disk workflow
are explicit design inspirations.
URL: [A2Command archive](https://mirrors.apple2.org.za/ftp.apple.asimov.net/utility/A2Command%20v1.1.zip)

**Norton Commander**
The two-panel layout, selection marks and bottom key bar are interface
inspirations.
URL: [Norton Commander archive](https://winworldpc.com/product/norton-commander/3x)

**ShrinkIt / NuFX and Binary II — Andy McFadden's NufxLib**
`UNSHRINK` decodes LZW/1 and LZW/2 after NufxLib's routines
(`Nu_ExpandLZW1/2`, `Nu_ExpandRLE`, `Nu_LZWGetCode` in `Lzw.c`), rewritten
in 6502 assembly; `src/unshrink.s` names them. `BINARY2` follows the public
member-header format. No archive executable code is bundled.
URLs: [NuFX notes](https://ciderpress2.com/formatdoc/NuFX-notes.html) · [NuLib format library](https://nulib.com/library/)

**Paul Lutus — Electric Duet**
The Electric Duet song format (three-byte records, two voices) played by
`DUET`. Its original player routine is under the GPL; the format is documented
by its author.
URL: [Electric Duet](https://arachnoid.com/electric_duet/index.html) · [player under the GPL](https://a2central.com/2014/01/paul-lutus-gpls-player-routine-from-electric-duet/)

**Alex Patalenski — improved Electric Duet player**
`src/plugins/duet.s` transcribes his 1989 speaker player, published by Emil
Dotchevski, instruction for instruction: its 73-cycle loop is kept in an
aligned segment so the timing stays his. Apple II DeskTop uses the same player.
URL: [the listing and byte code](https://www.reddit.com/r/apple2/comments/pue775/improved_electric_duet_player_by_alex_patalenski/) · [Apple II DeskTop](https://github.com/a2stuff/a2d)

**Cybernesto — electric-mock (GPL v3)**
The Mockingboard rendition of Electric Duet songs in `src/plugins/duet.c`
follows his player: one AY tone per voice. A2FileCmd times it with the VIA
instead of delay loops, and scales the periods to the speaker player.
URL: [electric-mock repository](https://github.com/cybernesto/electric-mock)

**GROUiK / French Touch — PT3 player for 6502 (GPL v3)**
`PT3`'s primary player: "Vortex Tracker II v1.0 PT3 player for 6502", from
the sources of the demo *One More Thing* (2019), translated by GROUiK from
**S.V. Bulba**'s ZX Spectrum player, with **Ivan Roshin**'s note and volume
table generators. `src/plugins/ppt3/original/ppt3.a` is the ACME source as
published, with its licence; `src/plugins/ppt3/ppt3.s` is its ca65 port,
byte-identical to it unless `PPT3_A2FC` is defined, and
`src/plugins/ppt3/README.md` lists every A2FileCmd change (address guards,
zero-page relocation, auxiliary-memory wrapper, no card access).
URL: [S.V. Bulba's players](https://bulba.untergrund.net/main_e.htm) (cited in the original source)

**Vince Weaver — pt3_lib (0BSD)**
`PT3`'s fallback player, in main memory: TurboSound pairs, modules over
32 KB, or when the auxiliary memory is declined. `src/plugins/pt3lib/`
keeps the upstream sources and lists the A2FileCmd changes.
URL: [pt3_lib](https://github.com/deater/dos33fsprogs/tree/master/music/pt3_lib)

**Penguin Software (later Polarware) — The Graphics Magician**
`GMAGIC` draws the picture files of The Graphics Magician (Penguin Software,
1982-1984; Penguin became Polarware), a Penguin Software product. It is a
clean-room implementation written from `docs/GRAPHICS-MAGICIAN-FORMAT.md`
alone, by a writer who read no Penguin program, disk or disassembly; no
Penguin code is copied. The 108 fill patterns and the eight brushes in
`src/plugins/gmagic_tables.inc` are interoperability data, generated from
the specification's Appendix A (observed on the screen); Penguin's font is
not used: text is drawn with BOLD.SET, A2FileCmd's demo font (CiderPress
II's STANDARD test font, bolded). The specification's study credits Andy
McFadden's commented disassembly of PICDRAWH, which was its starting point.
URL: [The Graphics Magician](https://graphicsmagician.com/) · [the format](GRAPHICS-MAGICIAN-FORMAT.md)

**Broderbund — Fantavision (1985)**
`FANTA.SYSTEM` plays Fantavision movies. It is a clean-room player written
from `docs/FANTAVISION-FORMAT.md` alone, the format and the original
player's behaviour as observed on real movies; none of Broderbund's code or
tables is used. The tests use `tools/fantavision_ref.py` and generated
movies; the DEMO movies are generated by `tools/mkdemo_viewers.py`.
URL: [the format](FANTAVISION-FORMAT.md)

**Baudville — Take 1 (1985)**
`TAKE1.SYSTEM` plays Take 1 movies. It is a clean-room player written from
`docs/TAKE1-FORMAT.md` alone; the specification comes from our own study of
the format, checked frame by frame against the original under emulation. No
Baudville code, movie or picture is copied or shipped: the tests, the
bench and `DEMO/MOVIES/TAKE1.DSK` (`tools/mkdemo_take1.py`) use synthetic
movies.
URL: [the format](TAKE1-FORMAT.md)

**Software Arts / VisiCorp — VisiCalc**
`VISICALC` shows VisiCalc worksheets, recalculated the way VisiCalc does.
The behaviour (file grammar, left-to-right arithmetic, decimal rounding,
display formats) was observed on the original under emulation and written
down in `docs/VISICALC-FORMAT.md`; `tools/visicalc_probes.json.gz` holds
only observed outputs of test worksheets written for this purpose. No
VisiCalc code is copied or shipped.
URL: [the format](VISICALC-FORMAT.md)

**Other formats read (no code from them)**
Springboard's The Newsroom (photos, banners and the clip art disks that
`NRCLIP` turns into pictures, `docs/NEWSROOM-FORMAT.md`), Le Chat Mauve's
Arlequin pictures (`docs/ARLEQUIN-FORMAT.md`), Purplesoft pictures
(`docs/PURPLESOFT-FORMAT.md`), Movie Maker shape sheets (Interactive
Picture Systems), Epistole (Version Soft), Papyrus (Ediciel), HomeWord
(Sierra) and Bank Street Writer (Broderbund) documents in `DOCVIEW`,
Terrapin Logo procedures and pictures, KoalaPad / Micro-Illustrator
pictures (Koala Technologies, Island Graphics: raw hi-res pages), DOS Tool
Kit and Beagle Bros HRCG fonts. These readers follow observed file layouts;
no program code is copied.

**Andy McFadden — CiderPress II**
The format notes of CiderPress II guided the MacPaint and AppleWorks data
base and spreadsheet readers, and its test files are the real samples the
tests use (`data/CP2/README.TXT` lists them). CiderPress II is under the
Apache License 2.0. The best of them ship in the XL image's DEMO folder,
each in the folder of its kind (`BORROWED` in `tools/stage_demo.py`):
PRESIDENTS, MATH.QUIZ, ESCHERWATER.MAC, SHRINKIT.BSC, HELLO.AS, STANDARD
and three shape tables. Four DEMO files are drawn from STANDARD by
`tools/mkdemo_viewers.py`: MGTK.FONT, BOLD.SET, ITALIC.FONT and the letters
of the Newsroom banner; GMAGIC draws text with BOLD.SET too.
`DEMO/README.TXT` (`data/README.TXT`) names them and their source.
URL: [CiderPress II](https://github.com/fadden/CiderPress2) · [format notes](https://ciderpress2.com/formatdoc/)

**System software on the disks**
The ProDOS disks carry ProDOS 8 v2.4.3 (`data/PRODOS.SYS` and the boot
blocks `data/prodos_boot.tmpl`); the 800K and XL disks add BASIC.SYSTEM
(`data/BASIC.SYSTEM.SYS`): Apple software distributed for the community by
John Brooks. They also carry Joshua Bell's INTBASIC.SYSTEM, which holds
Steve Wozniak's Integer BASIC ([`data/INTBASIC.md`](../data/INTBASIC.md)).
The DOS 3.3 disk boots on Apple's DOS 3.3 tracks 0-2
([`data/DOS33-BOOT.md`](../data/DOS33-BOOT.md)). All are copied unmodified.
URL: [ProDOS 8](https://prodos8.com/) · [INTBASIC.SYSTEM](https://github.com/a2stuff/intbasic)

**ZX Spectrum PT3 modules**
`media/pt3/` keeps eight starting modules and 5,507 ProTracker 3 modules
by their ZX Spectrum composers, downloaded from ZX-Art and zxtunes.com, for
the PT3 tests and the media volume; they are not on the distribution
disks. `media/pt3/MUSIC/SOURCES.TXT` names the author, title and source of
each one, and [SAMPLE-MEDIA.md](SAMPLE-MEDIA.md) the eight others.

**POM2 — Arnaud Verhille**
Separate emulator project used for repeatable Apple IIe, //c and disk-device
verification.
URL: [POM2 repository](https://github.com/habib256/pom2)

**David Schmidt — ADTPro**
Virtual-drive and disk-transfer workflows support moving the supplied `.dsk`
images to real hardware.
URL: [ADTPro project](https://adtpro.com/)

### Reading the source notices

The repository keeps attribution next to the affected implementation:

- `src/crt0.s` and `src/crt0_loader.s` identify the cc65 startup source and
  describe the local staging changes.
- `src/vsdrive.s` identifies the a2tools file and explains the adapted serial
  entry points.
- `src/format.c` and `src/format_diskii.s` identify the Hyper-FORMAT lineage
  and separate the original formatter work from A2FileCmd integration.
- `src/unshrink.s` names the NufxLib routines its decoder follows, rewritten
  in assembly for the overlay memory limits.
- `src/plugins/duet.s` names the Electric Duet players it transcribes and
  what was changed (zero page, alignment, exits); `src/plugins/duet.c` names
  the Mockingboard rendition it follows.
- `src/plugins/gmagic.s` and `tools/gmagic_ref.py` say they were written
  from the Graphics Magician specification alone (clean room),
  `src/plugins/gmagic_tables.inc` that its tables come from its Appendix A,
  and `src/plugins/gmagic_text.inc` that its font is BOLD.SET.
- `src/plugins/ppt3/README.md` and the header of `src/plugins/ppt3/ppt3.s`
  credit GROUiK, S.V. Bulba and Ivan Roshin; `tools/test_ppt3_port.py`
  proves the port equal to the original; `src/plugins/pt3lib/README.md`
  credits Vince Weaver.

The project does not copy Norton Commander, A2Command or ADTPro
executables; the only third-party executables on the disks are the system
software listed above, unmodified. Interfaces, manuals and protocols are
references or inspirations. The generated demo files are also original:
`tools/mkdemo.py`, `tools/mkdemo_viewers.py` and `tools/mkdemo_take1.py`
create the pictures, movies, music, documents and sample archives during
the build.
When redistributing a modified build, keep this section, the source notices
and `LICENSE` with the program so the attribution remains visible.

### Reference index

For readers who want to compare the implementation with its references:

- [A2FileCmd source and issue tracker](https://github.com/habib256/a2filecmd)
- [cc65 documentation](https://cc65.github.io/doc/)
- [cc65 Apple II library sources](https://github.com/cc65/cc65/tree/V2.19/libsrc/apple2)
- [a2tools source and releases](https://github.com/colinleroy/a2tools)
- [ADTPro documentation](https://adtpro.com/docs.htm)
- [ADTPro source](https://github.com/ADTPro/adtpro)
- [ProDOS 8 technical reference](https://prodos8.com/docs/)
- [Electric Duet, Paul Lutus](https://arachnoid.com/electric_duet/index.html)
- [Alex Patalenski's Electric Duet player](https://www.reddit.com/r/apple2/comments/pue775/improved_electric_duet_player_by_alex_patalenski/)
- [electric-mock, Cybernesto](https://github.com/cybernesto/electric-mock)
- [Apple II DeskTop file types](https://github.com/a2stuff/a2d/blob/main/notes/filetypes.md)
- [CiderPress II format notes](https://ciderpress2.com/formatdoc/)
- [NuLib library and Binary II references](https://nulib.com/library/)
- [Apple II FAQ archive](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/)
- [A2Command archive mirror](https://mirrors.apple2.org.za/ftp.apple.asimov.net/utility/)
- [Norton Commander archive](https://winworldpc.com/product/norton-commander/3x)
- [POM2 emulator](https://github.com/habib256/pom2)
- [ZX-Art AY / PT3 catalogue](https://zxart.ee/)
- [ZX-Art PT3 API](https://zxart.ee/api/types:zxMusic/export:zxMusic/language:eng/start:0/limit:1/filter:zxMusicFormat=PT3;)
- [ABSTRACT (Ra, 1999) PT3](https://zxart.ee/tune/77827)
- [dh2020rt (EA, 2020) PT3](https://zxart.ee/tune/325794)
- [Music (VAD, 2002) PT3](https://zxart.ee/tune/82459)
- [Old Skool For Demodulation (EA, 2020) PT3](https://zxart.ee/tune/357249)
- [realtime blast (EA, 2026) PT3](https://zxart.ee/tune/588679)
- [Yazzie: final theme (nq, 2019) PT3](https://zxart.ee/eng/authors/n/nq/yazzie-final-theme/)
- [ana_ng.pt3 in dos33fsprogs](https://github.com/deater/dos33fsprogs/blob/master/graphics/dgr/animations/tmbg/music/ana_ng.pt3)
- [mA2E_3.pt3 in dos33fsprogs](https://github.com/deater/dos33fsprogs/blob/master/graphics/gr/animations/grongy_roads/music/mA2E_3.pt3)
- [Vortex Tracker II](https://bulba.untergrund.net/vortex_e.htm)
- [zxtunes.com author list](https://zxtunes.com/authors_list.php?letter=A&lm=200&ln=eng)
- [zxtunes.com Macros archive](https://zxtunes.com/en/authors/macros)
- [zxtunes.com Korund archive](https://zxtunes.com/en/authors/korund)
- [Vince Weaver pt3_lib](https://github.com/deater/dos33fsprogs/tree/master/music/pt3_lib)
- [Asimov spreadsheet disks](https://www.apple.asimov.net/images/productivity/spreadsheet/) (VisiCalc 1.37, 1.93, 2.08, Home and Office Companion: run under POM2 to observe VisiCalc for `docs/VISICALC-FORMAT.md`; not copied into the repository. VisiCalc is a trademark of its owners; no VisiCalc code is used)

Historical archives may move or disappear; the repository copies the relevant attribution and
source-path information so the record remains useful if a mirror changes.

Only the fragments identified above are derived from external code or
documented routines. The A2FileCmd overlays, ProDOS walkers, image readers,
tests, demo data and user interface were written for this project. Generated
demo files are created by `tools/mkdemo.py`, `tools/mkdemo_viewers.py` and
`tools/mkdemo_take1.py`; they are not copied from the inspiration projects,
apart from the fonts drawn from STANDARD named above. See the repository source comments and `LICENSE` for
the complete copyright and redistribution terms.
