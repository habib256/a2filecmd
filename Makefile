# A2 Retro Cmd -- gestionnaire de fichiers ProDOS a deux panneaux, Apple IIe.
#
#   make            les trois binaires ProDOS, dans build/
#   make disk       les images de disquette dist/A2RETROCMD.po et .dsk
#   make test       les tests hors emulateur (disposition memoire, volume)
#   make bench      les bancs POM2 (demande l'emulateur, voir bench/README.md)
#   make clean
#
# Le programme ne tient dans la memoire de la machine que de justesse : le
# lien est verifie a chaque fois par tools/check_layout.py, qui attrape les
# deux debordements que ld65 laisse passer en silence. Voir docs/MANUAL.md.

A2RC_VERSION = 1.0
VOLUME       = A2RETROCMD

TARGET = apple2enh
CL     = cl65
AS     = ca65

SRC   = src
DATA  = data
TOOLS = tools
BUILD = build
DIST  = dist

# -Cl : locales statiques. Sur 6502 une variable de pile coute un calcul
# d'adresse a chaque acces, une statique un lda absolu. Contrepartie : aucune
# fonction ne doit etre reentrante, et les trois parcours recursifs de a2rc.c
# reprennent la pile par #pragma static-locals.
# --codesize 100 : le gonflement que l'optimiseur s'autorise. Mesure : en
# dessous de 100 le generateur cesse d'employer certaines sequences en ligne
# et le code REGROSSIT ; le minimum est un plateau de 100 a 130.
CFLAGS = -t $(TARGET) -O -Oirs -Cl --codesize 100

# __HIMEM__ = $BF00 : juste sous la page globale ProDOS. La pile C tient en
# 256 octets -- creux maximal mesure au banc : 94 (bench/stack.py).
HIMEM      = 0xBF00
A2RC_STACK = 0x0100
# Les tampons d'E/S ProDOS viennent de $0800 vers le haut au lieu du tas :
# sans ce module le tas ne fait que 270 octets et tout fopen echoue.
IOBUF = apple2enh-iobuf-0800.o

CODE   = $(BUILD)/A2RETRO.CODE.BIN
SYSTEM = $(BUILD)/A2RETRO.SYSTEM.SYS
FORMAT = $(BUILD)/FORMAT.SYS.SYS
PO     = $(DIST)/$(VOLUME).po
DSK    = $(DIST)/$(VOLUME).dsk

OBJS = $(BUILD)/crt0.o $(BUILD)/a2rc_mli.o $(BUILD)/chain.o $(BUILD)/music.o \
       $(BUILD)/memory_swap.o $(BUILD)/mli_safe.o

.PHONY: all disk test bench clean
all: $(SYSTEM) $(CODE) $(FORMAT)

$(BUILD) $(DIST):
	@mkdir -p $@

$(BUILD)/%.o: $(SRC)/%.s | $(BUILD)
	$(AS) -t $(TARGET) -o $@ $<

$(BUILD)/memory_swap.o: $(SRC)/memory_swap.c $(SRC)/memory_swap.h | $(BUILD)
	$(CL) $(CFLAGS) -c -o $@ $<

# Le lecteur Mockingboard lit son flux par tranches en RAM basse (-D LOWBUF) :
# sa BSS descend dans LOWBSS au lieu de la fenetre principale.
$(BUILD)/music.o: $(SRC)/music.s $(SRC)/ay_notes.inc | $(BUILD)
	$(AS) -t $(TARGET) -D LOWBUF -I $(SRC) -o $@ $<

# Le lanceur : un vrai programme SYS, charge en $2000 par ProDOS, qui lit
# A2RETRO.CODE a ses trois adresses (voir src/loader.c).
$(SYSTEM): $(SRC)/loader.c Makefile | $(BUILD)
	$(CL) $(CFLAGS) -D 'A2RC_VERSION="$(A2RC_VERSION)"' --start-addr 0x2000 \
	  -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__FILETYPE__=0xFF \
	  -o $@ $< $(IOBUF)

$(CODE): $(SRC)/a2rc.c $(SRC)/a2rc.cfg $(SRC)/music.h $(SRC)/memory_swap.h $(OBJS) Makefile | $(BUILD)
	$(CL) $(CFLAGS) -D 'A2RC_VERSION="$(A2RC_VERSION)"' -C $(SRC)/a2rc.cfg \
	  -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__STACKSIZE__=$(A2RC_STACK) \
	  -Wl -m,$(BUILD)/a2rc.map -Wl -Ln,$(BUILD)/a2rc.lbl \
	  -o $@ $(BUILD)/crt0.o $(SRC)/a2rc.c $(BUILD)/a2rc_mli.o $(BUILD)/chain.o \
	  $(BUILD)/music.o $(BUILD)/memory_swap.o $(BUILD)/mli_safe.o $(IOBUF)
	@python3 $(TOOLS)/check_layout.py --lbl $(BUILD)/a2rc.lbl --bin $@

# Le formateur, programme a part : il ecrase A2 Retro Cmd en memoire et le
# relance en sortant. Pas de suffixe .SYSTEM : ProDOS amorce le premier
# fichier .SYSTEM du catalogue, et il ne doit pas passer avant le lanceur.
$(FORMAT): $(SRC)/format.c $(SRC)/format_diskii.s $(SRC)/format_mli.s $(SRC)/format.cfg $(BUILD)/chain.o Makefile | $(BUILD)
	$(CL) $(CFLAGS) -D 'A2RC_VERSION="$(A2RC_VERSION)"' -C $(SRC)/format.cfg \
	  --start-addr 0x2000 -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=0x6400 \
	  -Wl -D,__FILETYPE__=0xFF -o $@ \
	  $(SRC)/format.c $(SRC)/format_diskii.s $(SRC)/format_mli.s $(BUILD)/chain.o $(IOBUF)

# ── La disquette ───────────────────────────────────────────────────────────
# Volume /A2RETROCMD, 280 blocs, amorcable : ProDOS 2.4.3, le lanceur a la
# racine (seul fichier .SYSTEM), le programme et son aide dans A2RETRO/, et
# un dossier DEMO fabrique de toutes pieces pour essayer le visionneur, le
# lecteur Mockingboard et l'editeur.
STAGE = $(BUILD)/vol
disk: $(PO)
$(PO): $(SYSTEM) $(CODE) $(FORMAT) $(DATA)/A2RETRO.HELP.TXT $(DATA)/PRODOS.SYS $(DATA)/BASIC.SYSTEM.SYS \
       $(DATA)/README.TXT $(DATA)/prodos_boot.tmpl \
       $(TOOLS)/mkvolume.py $(TOOLS)/mkdemo.py $(TOOLS)/po2dsk.py | $(DIST)
	@rm -rf $(STAGE) && mkdir -p $(STAGE)/A2RETRO $(STAGE)/DEMO
	cp $(DATA)/PRODOS.SYS $(DATA)/BASIC.SYSTEM.SYS $(STAGE)/
	cp $(SYSTEM) $(STAGE)/A2RETRO.SYSTEM.SYS
	cp $(CODE) $(STAGE)/A2RETRO/A2RETRO.CODE.BIN
	cp $(DATA)/A2RETRO.HELP.TXT $(STAGE)/A2RETRO/A2RETRO.HELP.TXT
	cp $(FORMAT) $(STAGE)/A2RETRO/FORMAT.SYS.SYS
	cp $(DATA)/README.TXT $(STAGE)/DEMO/README.TXT
	python3 $(TOOLS)/mkdemo.py $(STAGE)/DEMO
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(PO) --volume $(VOLUME) \
	  --boot $(DATA)/prodos_boot.tmpl --blocks 280
	python3 $(TOOLS)/po2dsk.py $(PO) $(DSK)
	@echo "==> $(PO) et $(DSK)"

test:
	python3 $(TOOLS)/test_check_layout.py
	python3 $(TOOLS)/test_mkvolume.py
	python3 $(TOOLS)/test_mkdemo.py

bench: all disk
	python3 bench/run.py

clean:
	rm -rf $(BUILD) $(DIST)
