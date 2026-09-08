# A2 File Cmd -- gestionnaire de fichiers ProDOS a deux panneaux, Apple IIe.
#
#   make            les trois binaires ProDOS, dans build/
#   make disk       les images de disquette dist/A2FILECMD.po et .dsk
#   make test       les tests hors emulateur (disposition memoire, volume)
#   make bench      les bancs POM2 (demande l'emulateur, voir bench/README.md)
#   make clean
#
# Le programme ne tient dans la memoire de la machine que de justesse : le
# lien est verifie a chaque fois par tools/check_layout.py, qui attrape les
# deux debordements que ld65 laisse passer en silence. Voir docs/MANUAL.md.

A2FC_VERSION = 0.6.1
VOLUME       = A2FILECMD

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
# fonction ne doit etre reentrante, et les trois parcours recursifs de a2fc.c
# reprennent la pile par #pragma static-locals.
# --codesize 100 : le gonflement que l'optimiseur s'autorise. Mesure : en
# dessous de 100 le generateur cesse d'employer certaines sequences en ligne
# et le code REGROSSIT ; le minimum est un plateau de 100 a 130.
CFLAGS = -t $(TARGET) -O -Oirs -Cl --codesize 100

# __HIMEM__ = $BF00 : juste sous la page globale ProDOS. La pile C tient en
# 256 octets -- creux maximal mesure au banc : 94 (bench/stack.py).
HIMEM      = 0xBF00
A2FC_STACK = 0x00C0
# Les tampons d'E/S ProDOS viennent de $0800 vers le haut au lieu du tas :
# sans ce module le tas ne fait que 270 octets et tout fopen echoue.
IOBUF = apple2enh-iobuf-0800.o

CODE   = $(BUILD)/A2FILE.CODE.BIN
# Les surcouches, ecrites par le meme lien (A2FILE/NOM.PLG, lus en $1B00 a la
# demande) : le decodeur d'images, les visionneuses, l'aide, la suppression,
# la musique, le lanceur, les attributs, l'editeur, le menu, les images
# disque. Chacune a deux segments dans son fichier : NOM (code) puis NOMRO
# (chaines). Voir src/a2fc_plugin.h pour l'en-tete et la table de services.
PLUGINS = IMAGE TEXT HEX DELETE HELP EDIT MUSIC RUN ATTR MENU DISKIMG IMGFS DOS33 UNSHRINK BASLIST COMPARE SEARCH BINARY2
SYSTEM = $(BUILD)/A2FILE.SYSTEM.SYS
FORMAT = $(BUILD)/FORMAT.SYS.SYS
PO     = $(DIST)/$(VOLUME).po
DSK    = $(DIST)/$(VOLUME).dsk

OBJS = $(BUILD)/crt0.o $(BUILD)/overlay.o $(BUILD)/unshrink.o $(BUILD)/a2fc_mli.o $(BUILD)/chain.o \
       $(BUILD)/music.o $(BUILD)/memory_swap.o $(BUILD)/mli_safe.o $(BUILD)/mouse.o

.PHONY: all disk test bench example clean
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
# A2FILE.CODE a ses trois adresses (voir src/loader.c).
$(SYSTEM): $(SRC)/loader.c $(BUILD)/crt0_loader.o $(BUILD)/loader_mli.o Makefile | $(BUILD)
	$(CL) $(CFLAGS) -D 'A2FC_VERSION="$(A2FC_VERSION)"' --start-addr 0x2000 \
	  -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__FILETYPE__=0xFF \
	  -o $@ $(BUILD)/crt0_loader.o $(BUILD)/loader_mli.o $< $(IOBUF)

$(CODE): $(SRC)/a2fc.c $(SRC)/a2fc.cfg $(SRC)/a2fc_plugin.h $(SRC)/music.h $(SRC)/memory_swap.h $(OBJS) Makefile | $(BUILD)
	$(CL) $(CFLAGS) -D 'A2FC_VERSION="$(A2FC_VERSION)"' -C $(SRC)/a2fc.cfg \
	  -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__STACKSIZE__=$(A2FC_STACK) \
	  -Wl -m,$(BUILD)/a2fc.map -Wl -Ln,$(BUILD)/a2fc.lbl \
	  -o $@ $(BUILD)/crt0.o $(BUILD)/overlay.o $(BUILD)/unshrink.o $(SRC)/a2fc.c $(BUILD)/a2fc_mli.o \
	  $(BUILD)/chain.o $(BUILD)/music.o $(BUILD)/memory_swap.o $(BUILD)/mli_safe.o \
	  $(BUILD)/mouse.o $(IOBUF)
	@python3 $(TOOLS)/check_layout.py --lbl $(BUILD)/a2fc.lbl --bin $@

# Le formateur, programme a part : il ecrase A2 File Cmd en memoire et le
# relance en sortant. Pas de suffixe .SYSTEM : ProDOS amorce le premier
# fichier .SYSTEM du catalogue, et il ne doit pas passer avant le lanceur.
$(FORMAT): $(SRC)/format.c $(SRC)/format_diskii.s $(SRC)/format_mli.s $(SRC)/format.cfg $(BUILD)/chain.o Makefile | $(BUILD)
	$(CL) $(CFLAGS) -D 'A2FC_VERSION="$(A2FC_VERSION)"' -C $(SRC)/format.cfg \
	  --start-addr 0x2000 -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=0x6400 \
	  -Wl -D,__FILETYPE__=0xFF -o $@ \
	  $(SRC)/format.c $(SRC)/format_diskii.s $(SRC)/format_mli.s $(BUILD)/chain.o $(IOBUF)

# ── La disquette et le disque dur ──────────────────────────────────────────
# Volume /A2FILECMD, amorcable : ProDOS 2.4.3, le lanceur a la racine (seul
# fichier .SYSTEM), le programme, ses surcouches (des BIN charges en $1B00,
# d'ou leur auxtype) et son aide dans A2FILE/. Deux tailles du meme volume :
# la disquette 5,25 (280 blocs, .po et .dsk), qui ne porte que le programme
# pour laisser le plus de place possible ; et le disque dur .2mg (65535
# blocs, le maximum de ProDOS), qui ajoute un dossier DEMO fabrique de toutes
# pieces avec un exemplaire de chaque chose qu'A2 File Cmd sait ouvrir.
STAGE = $(BUILD)/vol
HDV = $(BUILD)/A2FILECMD.hdv
TWOMG = $(DIST)/A2FILECMD.2mg
disk: $(PO)
$(PO): $(SYSTEM) $(CODE) $(FORMAT) $(DATA)/A2FILE.HELP.TXT $(DATA)/PRODOS.SYS $(DATA)/BASIC.SYSTEM.SYS \
       $(DATA)/README.TXT $(DATA)/prodos_boot.tmpl \
       $(TOOLS)/mkvolume.py $(TOOLS)/mkdemo.py $(TOOLS)/po2dsk.py $(TOOLS)/po22mg.py \
       $(TOOLS)/mkshk.py $(TOOLS)/mkbny.py $(TOOLS)/mkdos33.py | $(DIST)
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
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(HDV) --volume $(VOLUME) \
	  --boot $(DATA)/prodos_boot.tmpl --blocks 65535
	python3 $(TOOLS)/po22mg.py $(HDV) $(TWOMG)
	@rm -rf $(STAGE)/DEMO   # le stage redevient la disquette nue (bench/plugin.py le reprend)
	@echo "==> $(PO), $(DSK) et $(TWOMG)"

test:
	python3 $(TOOLS)/test_check_layout.py
	python3 $(TOOLS)/test_mkvolume.py
	python3 $(TOOLS)/test_mkdemo.py

bench: all disk
	python3 bench/run.py

# La surcouche d'exemple d'un tiers (sdk/), compilee HORS de l'arbre avec le
# seul src/a2fc_plugin.h : la preuve que l'ABI tient. Produit build/HELLO.PLG,
# a poser sous A2FILE/. bench/plugin.py le construit et le lance dans POM2.
example: $(BUILD)/HELLO.PLG
$(BUILD)/HELLO.PLG: sdk/hello.c sdk/plugin.cfg sdk/build.sh $(SRC)/a2fc_plugin.h | $(BUILD)
	sh sdk/build.sh sdk/hello.c HELLO

clean:
	rm -rf $(BUILD) $(DIST)
