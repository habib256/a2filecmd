# Makefile pour Le Marais aux Scorpions (SCOSWAMP)
# Compile pour Apple IIe Enhanced avec cc65

# Configuration
TARGET = apple2enh
PROGRAM = SCOSWAMP.BIN
LAUNCHER = SCOSWAMP.SYSTEM.SYS
CC = cc65
AS = ca65
LD = ld65
CL = cl65

# Répertoires
SRCDIR = .
OUTDIR = ..

# Fichiers source
SOURCES = scoswamp.c paths.c memory_swap.c rules.c dice.c messages.c hgr_loader.s
HEADERS = paths.h memory_swap.h hgr_rle.h rules.h dice.h messages.h
OBJECTS = scoswamp.o paths.o memory_swap.o rules.o dice.o messages.o hgr_loader.o

# Flags de compilation
# -t $(TARGET) : cible Apple IIe Enhanced
# -O : optimisation
# -Oirs : optimisation inline, registres, size
CFLAGS = -t $(TARGET) -O -Oirs

# Flags de linkage
# -Wl -S,0x4000 : démarrage à $4000 (préserve HGR Page 1 à $2000-$3FFF)
# -Wl -D,__EXEHDR__=0 : binaire brut sans en-tête AppleSingle
# apple2enh-iobuf-0800.o : les tampons d'E/S ProDOS (1 Ko par fichier ouvert)
# viennent de $0800..__MAIN_START__ au lieu du tas. Sans lui le tas ne fait
# que 270 octets et TOUT fopen echoue avec ENOMEM (errno=2, _oserror=0).
IOBUF   = apple2enh-iobuf-0800.o
# __HIMEM__ = $BF00 : le programme prend la place de BASIC.SYSTEM ($9600-$BEFF).
# Sans ca le moteur de combat ne rentre pas -- mesure au lien : 21 914 octets de
# code pour 22 016 disponibles sous $9600, et le BSS debordait alors SANS que
# ld65 le signale (apple2enh.cfg calcule sa taille par __HIMEM__ - __STACKSIZE__
# - __ONCE_RUN__, qui passe en negatif et deborde en entier non signe : le lien
# reussit et le binaire ecrase la RAM d'a cote). A $BF00 : 10 598 octets libres,
# tas de 4 903. Contrepartie assumee : plus de retour a BASIC, on sort par le
# QUIT ProDOS -- ce que fait deja le stub de sortie cc65, dont le code vit dans
# la Language Card. Cf. TODO.md, "1. __HIMEM__ = $BF00".
# -Wl -m,$(MAPFILE) : produit la carte memoire. Elle n'est pas un luxe ici :
# le BSS n'est pas dans le .BIN, il est alloue au lancement, et le fichier de
# configuration cc65 ne signale pas son debordement (voir ci-dessus).
# Une seule definition du plafond : le lien la passe a ld65, et le controle
# memoire la recoit telle quelle. Elle n'apparait PAS dans la carte quand elle
# vient de la ligne de commande -- le script ne peut donc pas la deviner.
HIMEM   = 0xBF00
LDFLAGS = -t $(TARGET) -Wl -D,__EXEHDR__=0 -Wl -S,0x4000 \
          -Wl -D,__HIMEM__=$(HIMEM) -Wl -m,$(MAPFILE)

MAPFILE = build.map

# Cible par défaut
all: $(OUTDIR)/$(PROGRAM) $(OUTDIR)/$(LAUNCHER)

# Règle principale : lier les objets pour créer le binaire
# Le contrôle mémoire est systématique : un link réussi ne prouve pas que le
# binaire tient (ld65 peut manquer un débordement BSS, voir tools/check-memory.sh).
$(OUTDIR)/$(PROGRAM): $(OBJECTS)
	$(CL) $(CFLAGS) $(LDFLAGS) -o $(OUTDIR)/$(PROGRAM) $(OBJECTS) $(IOBUF)
	@echo "==> Compilation terminée : $(OUTDIR)/$(PROGRAM)"
	@echo "    Adresse de démarrage : \$$4000 (HGR préservé à \$$2000-\$$3FFF)"
	@echo ""
	@../../tools/check-memory.sh --himem $(HIMEM) $(MAPFILE)

# Contrôle mémoire seul (nécessite une compilation préalable)
check: $(MAPFILE)
	@../../tools/check-memory.sh --himem $(HIMEM) $(MAPFILE)

# Le lanceur ProDOS. Charge en $2000 par ProDOS lui-meme, il lit le jeu en
# $4000 et lui saute dedans -- BASIC.SYSTEM ne peut plus le faire depuis que
# le binaire monte jusqu'a $9556 (voir loader.c pour le detail).
# Type ProDOS SYS ($FF) : c'est ce qui le rend lancable au boot. __EXEHDR__=0
# est indispensable : sans lui cc65 prefixe le fichier d'un en-tete de 4 octets
# que ProDOS chargerait en $2000 et executerait -- droit dans le moniteur.
$(OUTDIR)/$(LAUNCHER): loader.c
	$(CL) $(CFLAGS) --start-addr 0x2000 -Wl -D,__EXEHDR__=0 \
	      -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__FILETYPE__=0xFF -o $@ loader.c $(IOBUF)
	@echo "==> Lanceur ProDOS : $@"

# Compilation des fichiers .c en .o
rules.o: rules.c rules.h dice.h
	$(CC) $(CFLAGS) -o rules.s rules.c
	$(AS) -t $(TARGET) -o rules.o rules.s

messages.o: messages.c messages.h
	$(CC) $(CFLAGS) -o messages.s messages.c
	$(AS) -t $(TARGET) -o messages.o messages.s

dice.o: dice.c dice.h
	$(CC) $(CFLAGS) -o dice.s dice.c
	$(AS) -t $(TARGET) -o dice.o dice.s

scoswamp.o: scoswamp.c paths.h memory_swap.h rules.h dice.h
	$(CC) $(CFLAGS) -o scoswamp.s scoswamp.c
	$(AS) -t $(TARGET) -o scoswamp.o scoswamp.s

paths.o: paths.c paths.h
	$(CC) $(CFLAGS) -o paths.s paths.c
	$(AS) -t $(TARGET) -o paths.o paths.s

memory_swap.o: memory_swap.c memory_swap.h
	$(CC) $(CFLAGS) -o memory_swap.s memory_swap.c
	$(AS) -t $(TARGET) -o memory_swap.o memory_swap.s

hgr_loader.o: hgr_loader.s hgr_rle.h
	$(AS) -t $(TARGET) -o hgr_loader.o hgr_loader.s

# ── Image disque ProDOS ────────────────────────────────────────────────────
# Le volume est construit depuis $(OUTDIR) (= SCOSWAMP/) moins les dossiers de
# développement : DOCS et SRC n'ont rien à faire sur le disque du joueur, et
# ils mangeraient des slots du répertoire racine (51 en tout). Tout le reste
# part dans l'image, donc un nouvel asset n'a rien à déclarer ici.
#
# Cette cible existe parce que sans elle on relie SCOSWAMP.BIN et on oublie de
# refaire l'image : on teste alors un binaire à jour dans une image périmée.
# C'est ce qui est arrivé le 2026-08-29 — le disque portait le binaire d'avant
# le correctif iobuf, et le jeu rejouait un "errno=2 ProDOS=$$00" déjà corrigé.
TOOLS    = ../../SCOSWAMP.MORE/TOOLS
VOLBUILD = $(TOOLS)/build/build_prodos_volume
# Les deux premiers blocs (1 Ko) du volume : le boot loader ProDOS, que le
# constructeur recopie tel quel. Extrait d'une image amorçable connue et versionné
# ici, sinon `make hdv` ne peut pas partir d'un arbre propre (dist/ est ignoré).
BOOTTMPL = $(TOOLS)/prodos_boot.tmpl
HDV      = ../../dist/SCOSWAMP.HDV
STAGE    = ../../dist/.stage
# DOCS et SRC : du developpement, rien a faire sur le disque du joueur.
# BASIC.SYSTEM et STARTUP.BAS : le jeu occupe desormais $9600-$A3D9, c'est-a-dire
# la place de BASIC.SYSTEM. Il ne peut plus etre lance depuis BASIC, et laisser
# BASIC.SYSTEM sur le disque le ferait meme demarrer a sa place (ProDOS execute
# le premier fichier .SYSTEM du repertoire, et B vient avant S).
STAGE_EXCLUDE = DOCS SRC BASIC.SYSTEM.SYS STARTUP.BAS

hdv: $(HDV)

$(HDV): $(OUTDIR)/$(PROGRAM) $(OUTDIR)/$(LAUNCHER) $(BOOTTMPL) | $(VOLBUILD)
	@rm -rf $(STAGE) && mkdir -p $(STAGE) $(dir $(HDV))
	@for f in $(OUTDIR)/*; do \
		b=`basename "$$f"`; \
		case " $(STAGE_EXCLUDE) " in *" $$b "*) continue;; esac; \
		cp -R "$$f" $(STAGE)/; \
	done
	$(VOLBUILD) $(STAGE) $(BOOTTMPL) $(HDV)
	@rm -rf $(STAGE)
	@echo "==> Image disque : $(HDV)"

# Prérequis d'ordre seulement : on ne sait pas le construire depuis ici, on dit
# comment. Le tenir hors des dépendances normales évite de refaire l'image
# chaque fois que l'outil est relié.
$(VOLBUILD):
	@echo "Absent : $(VOLBUILD)"
	@echo "  cmake -S $(TOOLS) -B $(TOOLS)/build"
	@echo "  cmake --build $(TOOLS)/build --target build_prodos_volume"
	@exit 1

# Nettoyage des fichiers intermédiaires
clean:
	# Pas de `rm *.s` : hgr_loader.s est un source 6502 ecrit a la main, pas
	# un intermediaire cc65. On ne nomme que les .s reellement generes.
	rm -f *.o scoswamp.s paths.s memory_swap.s rules.s dice.s messages.s $(MAPFILE)
	@echo "==> Fichiers intermédiaires supprimés"

# Nettoyage complet (inclut le binaire)
distclean: clean
	rm -f $(OUTDIR)/$(PROGRAM) $(OUTDIR)/$(LAUNCHER)
	@echo "==> Nettoyage complet effectué"

# Rebuild complet
rebuild: distclean all

# Afficher les informations de configuration
info:
	@echo "Configuration du projet :"
	@echo "  Cible         : $(TARGET)"
	@echo "  Programme     : $(PROGRAM)"
	@echo "  Sources       : $(SOURCES)"
	@echo "  Répertoire    : $(OUTDIR)"
	@echo "  Compilateur   : $(CC) $(CFLAGS)"
	@echo "  Linkage       : $(LDFLAGS)"
	@echo "  Adresse start : \$$4000 (HGR Page 1 à \$$2000-\$$3FFF préservé)"
	@echo "  Image disque  : $(HDV) (cible 'hdv')"

# Installation : copie le binaire dans le répertoire parent
install: all
	@echo "==> Binaire disponible dans $(OUTDIR)/$(PROGRAM)"

# Déclaration des cibles "phony" (ne correspondent pas à des fichiers)
.PHONY: all hdv check clean distclean rebuild info install
