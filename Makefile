# A2 File Cmd -- two-panel ProDOS file manager for the Apple IIe.
#
#   make            the three ProDOS binaries, in build/
#   make disk       the floppy images dist/A2FILECMD.po and .dsk
#   make test       the tests outside the emulator (memory layout, volume)
#   make bench      the POM2 benches (needs the emulator, see bench/README.md)
#   make clean
#
# The program only just fits in the machine's memory: the link is checked
# every time by tools/check_layout.py, which catches the two overflows that
# ld65 lets through silently. See docs/MANUAL.md.

A2FC_VERSION = 0.7
VOLUME       = A2FILECMD

VOLUME_HD    = A2FILEHD     # the .2mg hard disk: another name, to coexist with the floppy
# ARCH=enh (default): Apple IIe enhanced, //c, IIgs -- cc65 target apple2enh
# (65C02, MouseText), with the machine's cc65 2.19. ARCH=6502: the NON
# enhanced IIe (6502, no MouseText), target apple2 -- whose 80-column
# console only exists in cc65 master (git, after 2.19: machinetype,
# aux80col, videomode for apple2): CC65_HEAD is a cc65 built from master
# (make ; make install PREFIX=~/opt/cc65-head), kept apart so as not to
# change the enhanced build. No mouse (for room), big BINARY2.
# The images take the -6502 suffix (make disk ARCH=6502).
ARCH ?= enh
CC65_HEAD ?= $(HOME)/opt/cc65-head
ifeq ($(ARCH),6502)
CC65BIN = CC65_HOME=$(CC65_HEAD)/share/cc65 $(CC65_HEAD)/bin/
TARGET = apple2
ASDEFS = -D A2_6502 -D CC65_MASTER
CLDEFS = --asm-define A2_6502 --asm-define CC65_MASTER -DA2FC_6502 -DA2FC_NOMOUSE -DA2FC_BIG_BINARY2
MOUSEOBJ =
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
IMG    = A2FILECMD
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
SYSTEM = $(BUILD)/A2FILE.SYSTEM.SYS
FORMAT = $(BUILD)/FORMAT.SYS.SYS
PO     = $(DIST)/$(IMG).po
DSK    = $(DIST)/$(IMG).dsk

OBJS = $(BUILD)/crt0.o $(BUILD)/overlay.o $(BUILD)/unshrink.o $(VDRIVEOBJ) $(BUILD)/a2fc_mli.o $(BUILD)/chain.o \
       $(BUILD)/music.o $(BUILD)/memory_swap.o $(BUILD)/mli_safe.o $(MOUSEOBJ)

.PHONY: all disk test bench example clean
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
# Volume /A2FILECMD, bootable: ProDOS 2.4.3, the launcher at the root (the
# only .SYSTEM file), the program, its overlays (BINs loaded at $1B00,
# hence their auxtype) and its help in A2FILE/. Two sizes of the same
# volume: the 5.25 floppy (280 blocks, .po and .dsk), which carries only
# the program to leave as much room as possible; and the .2mg hard disk
# (65535 blocks, ProDOS's maximum), which adds a DEMO directory built from
# scratch with one specimen of everything A2 File Cmd knows how to open.
STAGE = $(BUILD)/vol
HDV = $(BUILD)/$(IMG).hdv
TWOMG = $(DIST)/$(IMG).2mg
disk: $(PO)
$(PO): $(SYSTEM) $(CODE) $(FORMAT) $(DATA)/A2FILE.HELP.TXT $(DATA)/PRODOS.SYS $(DATA)/BASIC.SYSTEM.SYS \
       $(DATA)/README.TXT $(DATA)/prodos_boot.tmpl \
       $(TOOLS)/mkvolume.py $(TOOLS)/mkdemo.py $(TOOLS)/po2dsk.py $(TOOLS)/po22mg.py \
       $(TOOLS)/mkshk.py $(TOOLS)/mkbny.py $(TOOLS)/mkdos33.py $(wildcard $(DATA)/IMGHGR/*) | $(DIST)
	@rm -rf $(STAGE) && mkdir -p $(STAGE)/A2FILE
	cp $(DATA)/PRODOS.SYS $(DATA)/BASIC.SYSTEM.SYS $(STAGE)/
	cp $(SYSTEM) $(STAGE)/A2FILE.SYSTEM.SYS
	cp $(CODE) $(STAGE)/A2FILE/A2FILE.CODE.BIN
	for p in $(PLUGINS); do cp $(CODE).$$p "$(STAGE)/A2FILE/$$p.PLG#061B00"; done
	cp $(DATA)/A2FILE.HELP.TXT $(STAGE)/A2FILE/A2FILE.HELP.TXT
	cp $(FORMAT) $(STAGE)/A2FILE/FORMAT.SYS.SYS
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(PO) --volume $(VOLUME) \
	  --boot $(DATA)/prodos_boot.tmpl --blocks 280
	python3 $(TOOLS)/po2dsk.py $(PO) $(DSK)
	mkdir -p $(STAGE)/DEMO
	cp $(DATA)/README.TXT $(STAGE)/DEMO/README.TXT
	python3 $(TOOLS)/mkdemo.py $(STAGE)/DEMO
	cp -R $(DATA)/IMGHGR $(STAGE)/IMGHGR
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(HDV) --volume $(VOLUME_HD) \
	  --boot $(DATA)/prodos_boot.tmpl --blocks 65535
	python3 $(TOOLS)/po22mg.py $(HDV) $(TWOMG)
	@rm -rf $(STAGE)/DEMO $(STAGE)/IMGHGR   # the stage becomes the bare floppy again (bench/plugin.py picks it up)
	@echo "==> $(PO), $(DSK) and $(TWOMG)"

test:
	python3 $(TOOLS)/test_check_layout.py
	python3 $(TOOLS)/test_mkvolume.py
	python3 $(TOOLS)/test_mkdemo.py

bench: all disk
	python3 bench/run.py

# The third-party example overlay (sdk/), compiled OUTSIDE the tree with only
# src/a2fc_plugin.h: the proof that the ABI holds. Produces build/HELLO.PLG,
# to be put under A2FILE/. bench/plugin.py builds it and launches it in POM2.
example: $(BUILD)/HELLO.PLG
$(BUILD)/HELLO.PLG: sdk/hello.c sdk/plugin.cfg sdk/build.sh $(SRC)/a2fc_plugin.h | $(BUILD)
	sh sdk/build.sh sdk/hello.c HELLO

clean:
	rm -rf $(BUILD) $(DIST)
