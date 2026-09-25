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

**ShrinkIt / NuFX and Binary II**
`UNSHRINK` implements documented LZW/1 and LZW/2 formats; `BINARY2` follows
the public member-header format. No archive executable code is bundled.
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

**Andy McFadden — CiderPress II**
The format notes of CiderPress II guided the MacPaint and AppleWorks data
base and spreadsheet readers, and its test files are the real samples the
tests use (`data/CP2/README.TXT` lists them). The best of them ship in the
XL image's DEMO folder, each in the folder of its kind, and `DEMO/README`
names them and their source.
URL: [CiderPress II](https://github.com/fadden/CiderPress2) · [format notes](https://ciderpress2.com/formatdoc/)

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
- `src/unshrink.s` describes the documented archive algorithms; its decoder
  is an independent implementation written for the overlay memory limits.
- `src/plugins/duet.s` names the Electric Duet players it transcribes and
  what was changed (zero page, alignment, exits); `src/plugins/duet.c` names
  the Mockingboard rendition it follows.

The project does not copy Norton Commander, A2Command, ProDOS or ADTPro
executables. Their interfaces, manuals and protocols are references or
inspirations. The generated demo files are also original: `tools/mkdemo.py`
creates the pictures, music, text and sample archives during the build.
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

Historical archives may move or disappear; the repository copies the relevant attribution and
source-path information so the record remains useful if a mirror changes.

Only the fragments identified above are derived from external code or
documented routines. The A2FileCmd overlays, ProDOS walkers, image readers,
tests, demo data and user interface were written for this project. Generated
demo files are created by `tools/mkdemo.py`; they are not copied from the
inspiration projects. See the repository source comments and `LICENSE` for
the complete copyright and redistribution terms.
