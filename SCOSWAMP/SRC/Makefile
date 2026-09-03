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
SOURCES = scoswamp.c paths.c memory_swap.c rules.c dice.c messages.c hgr_loader.s sfx.s music.s
HEADERS = paths.h memory_swap.h hgr_rle.h rules.h dice.h messages.h sfx.h music.h
OBJECTS = scoswamp.o paths.o memory_swap.o rules.o dice.o messages.o hgr_loader.o sfx.o music.o

# Flags de compilation
# -t $(TARGET) : cible Apple IIe Enhanced
# -O : optimisation
# -Oirs : optimisation inline, registres, size
# -Cl : locales statiques. Sur 6502 une variable de pile coute un calcul
# d'adresse (ldy #n ; lda (sp),y) a chaque acces, une statique un lda absolu.
# Mesure le 2026-09-03 : 547 octets de code rendus. Contrepartie : aucune
# fonction ne doit etre reentrante -- le graphe d'appels (jsr entre .proc des
# .s generes) n'a aucun cycle, verifie le meme jour ; a re-verifier si une
# fonction se met a s'appeler elle-meme, directement ou non.
CFLAGS = -t $(TARGET) -O -Oirs -Cl

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
# Pile C ramenee de 2 Ko a 1,5 Ko (2026-08-30) : la chaine d'appels la plus
# profonde du jeu est load_scene -> run_* -> cprintf -> vsnprintf, quelques
# centaines d'octets ; les tampons de fichiers sont statiques (iobuf) et la
# boucle principale interdit la recursion de load_scene. Les 512 octets
# rendus ont paye les directives CS/MB/DV. Passe a check-memory.sh, qui
# comptait 2048 en dur.
STACK   = 0x0180
# -C scoswamp.cfg : apple2enh.cfg plus la zone LOWRAM ($1000-$1FFF) et son
# segment LOWBSS, ou vivent les gros tampons. Voir le fichier lui-meme.
LDCFG   = scoswamp.cfg
LDFLAGS = -t $(TARGET) -C $(LDCFG) -Wl -D,__EXEHDR__=0 -Wl -S,0x4000 \
          -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__STACKSIZE__=$(STACK) -Wl -m,$(MAPFILE)

MAPFILE = build.map

# Cible par défaut
all: $(OUTDIR)/$(PROGRAM) $(OUTDIR)/$(LAUNCHER)

# Règle principale : lier les objets pour créer le binaire
# Le contrôle mémoire est systématique : un link réussi ne prouve pas que le
# binaire tient (ld65 peut manquer un débordement BSS, voir tools/check-memory.sh).
$(OUTDIR)/$(PROGRAM): $(OBJECTS) $(LDCFG)
	$(CL) $(CFLAGS) $(LDFLAGS) -o $(OUTDIR)/$(PROGRAM) $(OBJECTS) $(IOBUF)
	@echo "==> Compilation terminée : $(OUTDIR)/$(PROGRAM)"
	@echo "    Adresse de démarrage : \$$4000 (HGR préservé à \$$2000-\$$3FFF)"
	@echo ""
	@../../tools/check-memory.sh --himem $(HIMEM) --stack $(STACK) $(MAPFILE)

# Contrôle mémoire seul (nécessite une compilation préalable)
check: $(MAPFILE)
	@../../tools/check-memory.sh --himem $(HIMEM) --stack $(STACK) $(MAPFILE)

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

scoswamp.o: scoswamp.c paths.h memory_swap.h rules.h dice.h messages.h hgr_rle.h sfx.h music.h
	$(CC) $(CFLAGS) -o scoswamp.s scoswamp.c
	$(AS) -t $(TARGET) -o scoswamp.o scoswamp.s

paths.o: paths.c paths.h
	$(CC) $(CFLAGS) -o paths.s paths.c
	$(AS) -t $(TARGET) -o paths.o paths.s

memory_swap.o: memory_swap.c memory_swap.h
	$(CC) $(CFLAGS) -o memory_swap.s memory_swap.c
	$(AS) -t $(TARGET) -o memory_swap.o memory_swap.s

# ── Musiques ───────────────────────────────────────────────────────────────
# Chaque musique est une donnee sur le disque : MUSIC/<NOM>.MB.BIN ici, donc
# MUSIC/<NOM>.MB sur le volume (l'empaqueteur retire la derniere extension).
# Elles sortent de partitions MIDI du domaine public (SCOSWAMP.MORE/MUSIC/src,
# voir SOURCES.md) par midi_to_mb.py, qui reduit a trois voix et ecrit aussi
# la table de notes de music.s. La page qui veut une musique la nomme par une
# ligne "MU <NOM>.MB". Le tempo est fixe ici, pas dans le MIDI.
MUSIC    = ../../SCOSWAMP.MORE/MUSIC
MB       = python3 $(MUSIC)/midi_to_mb.py
MUSICS   = $(OUTDIR)/MUSIC/SALTARELLO.MB.BIN $(OUTDIR)/MUSIC/GREENSLEEVES.MB.BIN \
           $(OUTDIR)/MUSIC/COMEAGAIN.MB.BIN $(OUTDIR)/MUSIC/ACCUEIL.MB.BIN

musics: $(MUSICS)

$(OUTDIR)/MUSIC/SALTARELLO.MB.BIN: $(MUSIC)/src/saltarello.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 160 --vol 13,9,11 --wav $(MUSIC)/saltarello.wav --notes-inc ay_notes.inc
$(OUTDIR)/MUSIC/GREENSLEEVES.MB.BIN: $(MUSIC)/src/greensleeves.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 140 --vol 13,8,11 --wav $(MUSIC)/greensleeves.wav
$(OUTDIR)/MUSIC/COMEAGAIN.MB.BIN: $(MUSIC)/src/comeagain.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 170 --vol 13,8,11 --wav $(MUSIC)/comeagain.wav
# La composition maison (accueil.py), gardee comme quatrieme fichier.
$(MUSIC)/accueil.mid: $(MUSIC)/accueil.py
	python3 $(MUSIC)/accueil.py
$(OUTDIR)/MUSIC/ACCUEIL.MB.BIN: $(MUSIC)/accueil.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 150 --vol 13,8,10

ay_notes.inc: $(OUTDIR)/MUSIC/SALTARELLO.MB.BIN

music.o: music.s ay_notes.inc
	$(AS) -t $(TARGET) -o music.o music.s

sfx.o: sfx.s sfx.h
	$(AS) -t $(TARGET) -o sfx.o sfx.s

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

# Le disque porte les DONNEES autant que le binaire : le moteur est
# data-driven, donc une page de texte corrigee ou une image reconvertie doit
# reconstruire l'image disque. Sans ces dependances, `make hdv` repondait
# "Nothing to be done" apres une correction du corpus et le joueur testait un
# disque perime -- ce qui nous a deja coute une seance de debogage sur un bug
# qui n'existait plus.
# Les noms doivent etre EXACTS. `find` ne peut pas se plaindre d'un chemin
# absent ici -- le 2>/dev/null qui protege des repertoires optionnels avale
# aussi la faute de frappe -- donc un mauvais nom se lit comme "aucune
# dependance". `MSGFR` / `MSGEN` etaient dans ce cas, les fichiers s'appelant
# MSGFR.TXT / MSGEN.TXT : ajouter une paire de messages ne reconstruisait pas
# l'image, le disque gardait un catalogue a MSG_COUNT-2 lignes, et
# messages_load rejette un fichier qui n'a pas exactement MSG_COUNT lignes --
# toute l'interface partait vide, pas seulement les deux nouveaux messages.
# HELPFR.TXT / HELPEN.TXT n'y figuraient pas du tout.
PAYLOAD = $(shell find $(OUTDIR)/TEXTFR $(OUTDIR)/TEXTEN $(OUTDIR)/IMG $(OUTDIR)/MUSIC \
                       $(OUTDIR)/MSGFR.TXT $(OUTDIR)/MSGEN.TXT \
                       $(OUTDIR)/HELPFR.TXT $(OUTDIR)/HELPEN.TXT \
                       $(OUTDIR)/SAVE \
                       $(OUTDIR)/TITLE.TXT \
                       -type f 2>/dev/null)

hdv: $(HDV)

$(HDV): $(OUTDIR)/$(PROGRAM) $(OUTDIR)/$(LAUNCHER) $(BOOTTMPL) $(MUSICS) $(PAYLOAD) | $(VOLBUILD)
	@rm -rf $(STAGE) && mkdir -p $(STAGE) $(dir $(HDV))
	@for f in $(OUTDIR)/*; do \
		b=`basename "$$f"`; \
		case " $(STAGE_EXCLUDE) " in *" $$b "*) continue;; esac; \
		cp -R "$$f" $(STAGE)/; \
	done
	$(VOLBUILD) $(STAGE) $(BOOTTMPL) $(HDV)
	@rm -rf $(STAGE)
	@echo "==> Image disque : $(HDV)"

# ── Images de release ──────────────────────────────────────────────────────
# `make hdv` produit l'image de travail, toujours au meme nom, que l'emulateur
# voisin relance sans qu'on retape un chemin. `make release` en tire les deux
# fichiers qu'un joueur telecharge, portant le numero de version :
#
#   dist/scoswamp-$(VERSION).hdv   les blocs ProDOS bruts
#   dist/scoswamp-$(VERSION).2mg   les memes blocs + 64 octets d'en-tete 2MG
#
# Le .2mg existe parce que plusieurs emulateurs refusent de deviner la
# geometrie d'un .hdv d'apres sa taille ; l'en-tete la leur dit.
VERSION  = 0.9
RELHDV   = ../../dist/scoswamp-$(VERSION).hdv
REL2MG   = ../../dist/scoswamp-$(VERSION).2mg
WRAP2MG  = $(TOOLS)/wrap_2mg.py

release: $(REL2MG)

$(RELHDV): $(HDV)
	@cp $(HDV) $@
	@echo "==> Image de release : $@"

$(REL2MG): $(RELHDV) $(WRAP2MG)
	@python3 $(WRAP2MG) $(RELHDV) $@

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
	# music.s et hgr_loader.s sont ecrits a la main : on ne les touche pas
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
.PHONY: all hdv release check clean distclean rebuild info install
