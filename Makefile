# A2 File Cmd -- two-panel ProDOS file manager, Apple IIe.
#
#   make            the three ProDOS binaries, in build/ (ARCH=enh) or build-6502/
#   make disk       the two editions: the floppy dist/A2FILECMD-6502.po and
#                   .dsk (6502 build, the file manager and the disk tools only)
#                   and the hard disk dist/A2FILECMDXL-65C02.2mg, volume
#                   /A2FILECMDXL (65C02 build, everything).
#                   With ARCH=6502 or ARCH=enh given, only that edition.
#   make benchfloppy  build/A2FILECMD-full.po: a 65C02 floppy with every
#                   overlay, for the benches only -- never shipped
#   make test       the tests outside the emulator (memory layout, volume)
#   make bench      the POM2 benches (needs the emulator, see bench/README.md)
#   make clean
#
# The program only just fits in the machine's memory: the link is checked
# every time by tools/check_layout.py, which catches the two overflows that
# ld65 lets through silently. See docs/MANUAL.md.

A2FC_VERSION = 0.7
VOLUME       = A2FILECMD

# The .2mg hard disk: another volume name, to coexist with the floppy.
# (Comments stay on their own line: make keeps the blanks before a `#`.)
VOLUME_HD    = A2FILECMDXL
# Two editions, one tree (decided 2026-09-09, see TODO.md):
#
#   ARCH=6502  the FLOPPY edition, dist/A2FILECMD-6502.po and .dsk: target
#              apple2 (6502, no MouseText), so it runs on any Apple II with
#              128 KB and 80 columns, the 1983 IIe included; no mouse (for
#              room), big BINARY2. Carries the file manager and the disk
#              tools only (PLUGINS_FLOPPY), no BASIC.SYSTEM: what a user with
#              two Disk II drives and no hard disk cannot do otherwise.
#              The apple2 target's 80-column console only exists in cc65
#              master (git, after 2.19: machinetype, aux80col, videomode):
#              CC65_HEAD is a cc65 built from master (make ; make install
#              PREFIX=~/opt/cc65-head), kept apart from the 2.19 build.
#   ARCH=enh   the COMPLETE edition, dist/A2FILECMDXL-65C02.2mg: apple2enh
#              (65C02, MouseText) for the enhanced IIe, //c and IIgs, with
#              the mouse, every overlay, BASIC.SYSTEM, DEMO/ and IMGHGR/.
#
# `make disk` with no ARCH builds both; with ARCH given, that edition only.
ifeq ($(origin ARCH),undefined)
BOTH_EDITIONS = yes
endif
ARCH ?= enh
CC65_HEAD ?= $(HOME)/opt/cc65-head
ifeq ($(ARCH),6502)
CC65BIN = CC65_HOME=$(CC65_HEAD)/share/cc65 $(CC65_HEAD)/bin/
TARGET = apple2
ASDEFS = -D A2_6502 -D CC65_MASTER
CLDEFS = --asm-define A2_6502 --asm-define CC65_MASTER -DA2FC_6502 -DA2FC_NOMOUSE -DA2FC_BIG_BINARY2
MOUSEOBJ =
# The edition and the processor, in the file name.
IMG    = A2FILECMD-6502
BUILD_SUFFIX = -6502
BIN2SIZE = 0x0D00
LAYOUT_BIG = --big BINARY2
else
CC65BIN =
TARGET = apple2enh
ASDEFS =
CLDEFS =
MOUSEOBJ = $(BUILD)/mouse.o
# The volume /A2FILECMDXL and the processor, in the file name.
IMG    = A2FILECMDXL-65C02
BUILD_SUFFIX =
BIN2SIZE = 0x0500
LAYOUT_BIG =
endif
IOBUF  = $(TARGET)-iobuf-0800.o
VDRIVEOBJ = $(BUILD)/vsdrive.o
CL     = $(CC65BIN)cl65
AS     = $(CC65BIN)ca65

SRC   = src
DATA  = data
TOOLS = tools
BUILD = build$(BUILD_SUFFIX)
DIST  = dist

# -Cl: static locals. On a 6502 a stack variable costs an address
# computation at every access, a static one an absolute lda. The price: no
# function may be reentrant, and the three recursive walks in a2fc.c
# take the stack back with #pragma static-locals.
# --codesize 100: the growth the optimiser allows itself. Measured: below
# 100 the generator stops using some inline sequences and the code GROWS
# AGAIN; the minimum is a plateau from 100 to 130.
CODESIZE ?= 100
CFLAGS = -t $(TARGET) $(CLDEFS) -O -Oirs -Cl --codesize $(CODESIZE)

# __HIMEM__ = $BF00: just below the ProDOS global page. The C stack fits in
# 256 bytes -- maximum depth measured on the bench: 94 (bench/stack.py).
HIMEM      = 0xBF00
A2FC_STACK = 0x00C0
# The ProDOS I/O buffers come from $0800 upward instead of the heap:
# without this module the heap is only 270 bytes and every fopen fails.

CODE   = $(BUILD)/A2FILE.CODE.BIN
# The overlays, written by the same link (A2FILE/NAME.PLG, read at $1B00 on
# demand): the image decoder, the viewers, the help, deletion, music, the
# launcher, the attributes, the editor, the menu, the disk images. Each has
# two segments in its file: NAME (code) then NAMERO (strings). See
# src/a2fc_plugin.h for the header and the service table.
PLUGINS = IMAGE TEXT HEX DELETE HELP EDIT MUSIC RUN ATTR MENU DISKIMG IMGFS DOS33 UNSHRINK BASLIST COMPARE SEARCH BINARY2 AWP
# The floppy edition: the commands, the two viewers that cost four blocks,
# and the disk tools. The editor, the pictures, the music, the archives and
# the document readers stay on the hard disk (45 blocks, with BASIC.SYSTEM's
# 21, given back to the disk tools to come -- see TODO.md, "Les deux editions").
PLUGINS_FLOPPY = HELP TEXT HEX DELETE RUN ATTR MENU DISKIMG IMGFS DOS33
SYSTEM = $(BUILD)/A2FILE.SYSTEM.SYS
FORMAT = $(BUILD)/FORMAT.SYS.SYS
PO     = $(DIST)/$(IMG).po
DSK    = $(DIST)/$(IMG).dsk

OBJS = $(BUILD)/crt0.o $(BUILD)/overlay.o $(BUILD)/unshrink.o $(VDRIVEOBJ) $(BUILD)/a2fc_mli.o $(BUILD)/chain.o \
       $(BUILD)/music.o $(BUILD)/memory_swap.o $(BUILD)/mli_safe.o $(MOUSEOBJ)

.PHONY: all disk benchfloppy test bench example clean
all: $(SYSTEM) $(CODE) $(FORMAT)

$(BUILD) $(DIST):
	@mkdir -p $@

$(BUILD)/%.o: $(SRC)/%.s | $(BUILD)
	$(AS) -t $(TARGET) $(ASDEFS) -o $@ $<

$(BUILD)/memory_swap.o: $(SRC)/memory_swap.c $(SRC)/memory_swap.h | $(BUILD)
	$(CL) $(CFLAGS) -c -o $@ $<

# The Mockingboard player reads its stream in slices in low RAM (-D LOWBUF):
# its BSS moves down into LOWBSS instead of the main window.
$(BUILD)/music.o: $(SRC)/music.s $(SRC)/ay_notes.inc | $(BUILD)
	$(AS) -t $(TARGET) $(ASDEFS) -D LOWBUF -I $(SRC) -o $@ $<

# The launcher: a real SYS program, loaded at $2000 by ProDOS, which reads
# A2FILE.CODE to its three addresses (see src/loader.c).
$(SYSTEM): $(SRC)/loader.c $(BUILD)/crt0_loader.o $(BUILD)/loader_mli.o Makefile | $(BUILD)
	$(CL) $(CFLAGS) -D 'A2FC_VERSION="$(A2FC_VERSION)"' --start-addr 0x2000 \
	  -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__FILETYPE__=0xFF \
	  -o $@ $(BUILD)/crt0_loader.o $(BUILD)/loader_mli.o $< $(IOBUF)

$(CODE): $(SRC)/a2fc.c $(SRC)/a2fc.cfg $(SRC)/a2fc_plugin.h $(SRC)/music.h $(SRC)/memory_swap.h $(OBJS) Makefile | $(BUILD)
	$(CL) $(CFLAGS) -D 'A2FC_VERSION="$(A2FC_VERSION)"' -C $(SRC)/a2fc.cfg \
	  -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__STACKSIZE__=$(A2FC_STACK) -Wl -D,__BIN2SIZE__=$(BIN2SIZE) \
	  -Wl -m,$(BUILD)/a2fc.map -Wl -Ln,$(BUILD)/a2fc.lbl \
	  -o $@ $(BUILD)/crt0.o $(BUILD)/overlay.o $(BUILD)/unshrink.o $(VDRIVEOBJ) $(SRC)/a2fc.c $(BUILD)/a2fc_mli.o \
	  $(BUILD)/chain.o $(BUILD)/music.o $(BUILD)/memory_swap.o $(BUILD)/mli_safe.o \
	  $(MOUSEOBJ) $(IOBUF)
	@python3 $(TOOLS)/check_layout.py --lbl $(BUILD)/a2fc.lbl --bin $@ $(LAYOUT_BIG)

# The formatter, a separate program: it overwrites A2 File Cmd in memory and
# relaunches it on exit. No .SYSTEM suffix: ProDOS boots the first .SYSTEM
# file of the catalog, and it must not come before the launcher.
$(FORMAT): $(SRC)/format.c $(SRC)/format_diskii.s $(SRC)/format_mli.s $(SRC)/format.cfg $(BUILD)/chain.o Makefile | $(BUILD)
	$(CL) $(CFLAGS) -D 'A2FC_VERSION="$(A2FC_VERSION)"' -C $(SRC)/format.cfg \
	  --start-addr 0x2000 -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=0x6400 \
	  -Wl -D,__FILETYPE__=0xFF -o $@ \
	  $(SRC)/format.c $(SRC)/format_diskii.s $(SRC)/format_mli.s $(BUILD)/chain.o $(IOBUF)

# -- The floppy and the hard disk -------------------------------------------
# Two volumes, bootable: ProDOS 2.4.3, the launcher at the root (the only
# .SYSTEM file), the program, its overlays (BINs loaded at $1B00, hence
# their auxtype) and its help in A2FILE/.
#   The floppy /A2FILECMD (280 blocks, .po and .dsk), the 6502 build: the
# file manager and the disk tools (PLUGINS_FLOPPY), nothing else.
#   The hard disk /A2FILECMDXL (.2mg, 65535 blocks, ProDOS's maximum), the
# 65C02 build: every overlay, BASIC.SYSTEM, and a DEMO directory built from
# scratch with one specimen of everything A2 File Cmd knows how to open.
STAGE = $(BUILD)/vol
HDV = $(BUILD)/$(IMG).hdv
TWOMG = $(DIST)/$(IMG).2mg
FULLPO = $(BUILD)/A2FILECMD-full.po
STAGE_DEPS = $(SYSTEM) $(CODE) $(FORMAT) $(DATA)/A2FILE.HELP.TXT $(DATA)/PRODOS.SYS \
       $(DATA)/prodos_boot.tmpl $(TOOLS)/mkvolume.py

ifdef BOTH_EDITIONS
disk:
	$(MAKE) ARCH=6502 disk
	$(MAKE) ARCH=enh disk
else ifeq ($(ARCH),6502)
disk: $(PO)
else
disk: $(TWOMG)
endif

# The stage: the launcher, the program, the overlays named in $(1), the help,
# the formatter. Called with the plugin list.
define stage
	@rm -rf $(STAGE) && mkdir -p $(STAGE)/A2FILE
	cp $(DATA)/PRODOS.SYS $(STAGE)/
	cp $(SYSTEM) $(STAGE)/A2FILE.SYSTEM.SYS
	cp $(CODE) $(STAGE)/A2FILE/A2FILE.CODE.BIN
	for p in $(1); do cp $(CODE).$$p "$(STAGE)/A2FILE/$$p.PLG#061B00"; done
	cp $(DATA)/A2FILE.HELP.TXT $(STAGE)/A2FILE/A2FILE.HELP.TXT
	cp $(FORMAT) $(STAGE)/A2FILE/FORMAT.SYS.SYS
endef

# The floppy edition (ARCH=6502).
$(PO): $(STAGE_DEPS) $(TOOLS)/po2dsk.py | $(DIST)
	$(call stage,$(PLUGINS_FLOPPY))
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(PO) --volume $(VOLUME) \
	  --boot $(DATA)/prodos_boot.tmpl --blocks 280
	python3 $(TOOLS)/po2dsk.py $(PO) $(DSK)
	@python3 $(TOOLS)/prodos_read.py $(PO) | head -1
	@echo "==> $(PO) and $(DSK): the floppy edition ($(ARCH))"

# The complete edition (ARCH=enh).
$(TWOMG): $(STAGE_DEPS) $(DATA)/BASIC.SYSTEM.SYS $(DATA)/README.TXT \
       $(TOOLS)/mkdemo.py $(TOOLS)/po22mg.py \
       $(TOOLS)/mkshk.py $(TOOLS)/mkbny.py $(TOOLS)/mkdos33.py $(wildcard $(DATA)/IMGHGR/*) | $(DIST)
	$(call stage,$(PLUGINS))
	cp $(DATA)/BASIC.SYSTEM.SYS $(STAGE)/
	mkdir -p $(STAGE)/DEMO
	cp $(DATA)/README.TXT $(STAGE)/DEMO/README.TXT
	python3 $(TOOLS)/mkdemo.py $(STAGE)/DEMO
	cp -R $(DATA)/IMGHGR $(STAGE)/IMGHGR
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(HDV) --volume $(VOLUME_HD) \
	  --boot $(DATA)/prodos_boot.tmpl --blocks 65535
	python3 $(TOOLS)/po22mg.py $(HDV) $(TWOMG)
	@rm -rf $(STAGE)/DEMO $(STAGE)/IMGHGR   # the stage keeps the program alone (bench/plugin.py picks it up)
	@echo "==> $(TWOMG): the complete edition ($(ARCH))"

# A 65C02 floppy with every overlay and BASIC.SYSTEM, for the benches that
# exercise the editor, the pictures, the archives and the readers from a
# floppy (bench/run.py and friends, A2FC_IMG=A2FILECMD-full). Never shipped.
benchfloppy: $(FULLPO)
$(FULLPO): $(STAGE_DEPS) $(DATA)/BASIC.SYSTEM.SYS
	$(call stage,$(PLUGINS))
	cp $(DATA)/BASIC.SYSTEM.SYS $(STAGE)/
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(FULLPO) --volume $(VOLUME) \
	  --boot $(DATA)/prodos_boot.tmpl --blocks 280
	@echo "==> $(FULLPO): the bench floppy, every overlay ($(ARCH))"

test:
	python3 $(TOOLS)/test_check_layout.py
	python3 $(TOOLS)/test_mkvolume.py
	python3 $(TOOLS)/test_mkdemo.py

bench: disk
	$(MAKE) ARCH=enh benchfloppy
	python3 bench/run.py

# The third-party example overlay (sdk/), compiled OUTSIDE the tree with only
# src/a2fc_plugin.h: the proof that the ABI holds. Produces build/HELLO.PLG,
# to be put under A2FILE/. bench/plugin.py builds it and launches it in POM2.
example: $(BUILD)/HELLO.PLG
$(BUILD)/HELLO.PLG: sdk/hello.c sdk/plugin.cfg sdk/build.sh $(SRC)/a2fc_plugin.h | $(BUILD)
	sh sdk/build.sh sdk/hello.c HELLO

clean:
	rm -rf $(BUILD) $(DIST)
