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
# --codesize 100 : le facteur de gonflement que l'optimiseur s'autorise pour
# aller plus vite. cc65 2.19 en prend nettement plus par defaut -- mesure le
# 2026-09-04 sur scoswamp.c : 17 248 octets de CODE sans l'option, 16 309 avec,
# soit 939 octets, plus 68 dans la Language Card. En dessous de 100 le
# generateur cesse d'employer certaines sequences en ligne et le code REGROSSIT
# (19 255 a 90) : le minimum est un plateau de 100 a 130.
CFLAGS = -t $(TARGET) -O -Oirs -Cl --codesize 100

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
# Les dix musiques du disque : le dossier fantasy moderne, des compositions
# originales (SCOSWAMP.MORE/MUSIC/propositions-moderne, compose.py + un
# script par zone, DOCS/MUSIQUE-CLAIRIERES.md pour le plan des zones). Les
# themes de zone tiennent dans 2304 octets, les surcouches (combat, mort,
# victoire) dans 1280 : midi_to_mb.py refuse au-dela. Le dossier Renaissance
# (propositions/, sources dans src/) reste disponible en remplacement.
MODERNE  = $(MUSIC)/propositions-moderne
MUSICS   = $(OUTDIR)/MUSIC/ACCUEIL.MB.BIN \
           $(OUTDIR)/MUSIC/VILLAGE.MB.BIN \
           $(OUTDIR)/MUSIC/MARAISNO.MB.BIN \
           $(OUTDIR)/MUSIC/RIVIERE.MB.BIN \
           $(OUTDIR)/MUSIC/MARAISUD.MB.BIN \
           $(OUTDIR)/MUSIC/DANGER.MB.BIN \
           $(OUTDIR)/MUSIC/TOUR.MB.BIN \
           $(OUTDIR)/MUSIC/COMBAT.MB.BIN \
           $(OUTDIR)/MUSIC/MORT.MB.BIN \
           $(OUTDIR)/MUSIC/VICTOIRE.MB.BIN

musics: $(MUSICS)

$(MODERNE)/accueil/accueil.mid: $(MODERNE)/accueil/accueil.py $(MODERNE)/compose.py
	cd $(MODERNE)/accueil && python3 accueil.py
$(OUTDIR)/MUSIC/ACCUEIL.MB.BIN: $(MODERNE)/accueil/accueil.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 136 --max 2304 --wav $(MODERNE)/accueil/ACCUEIL.wav --notes-inc ay_notes.inc
$(MODERNE)/village/village.mid: $(MODERNE)/village/village.py $(MODERNE)/compose.py
	cd $(MODERNE)/village && python3 village.py
$(OUTDIR)/MUSIC/VILLAGE.MB.BIN: $(MODERNE)/village/village.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 166 --max 2304 --wav $(MODERNE)/village/VILLAGE.wav
$(MODERNE)/nord/nord.mid: $(MODERNE)/nord/nord.py $(MODERNE)/compose.py
	cd $(MODERNE)/nord && python3 nord.py
$(OUTDIR)/MUSIC/MARAISNO.MB.BIN: $(MODERNE)/nord/nord.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 150 --max 2304 --wav $(MODERNE)/nord/MARAISNO.wav
$(MODERNE)/riviere/riviere.mid: $(MODERNE)/riviere/riviere.py $(MODERNE)/compose.py
	cd $(MODERNE)/riviere && python3 riviere.py
$(OUTDIR)/MUSIC/RIVIERE.MB.BIN: $(MODERNE)/riviere/riviere.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 125 --max 2304 --wav $(MODERNE)/riviere/RIVIERE.wav
$(MODERNE)/sud/sud.mid: $(MODERNE)/sud/sud.py $(MODERNE)/compose.py
	cd $(MODERNE)/sud && python3 sud.py
$(OUTDIR)/MUSIC/MARAISUD.MB.BIN: $(MODERNE)/sud/sud.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 150 --max 2304 --wav $(MODERNE)/sud/MARAISUD.wav
$(MODERNE)/danger/danger.mid: $(MODERNE)/danger/danger.py $(MODERNE)/compose.py
	cd $(MODERNE)/danger && python3 danger.py
$(OUTDIR)/MUSIC/DANGER.MB.BIN: $(MODERNE)/danger/danger.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 136 --max 2304 --wav $(MODERNE)/danger/DANGER.wav
$(MODERNE)/tour/tour.mid: $(MODERNE)/tour/tour.py $(MODERNE)/compose.py
	cd $(MODERNE)/tour && python3 tour.py
$(OUTDIR)/MUSIC/TOUR.MB.BIN: $(MODERNE)/tour/tour.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 125 --max 2304 --wav $(MODERNE)/tour/TOUR.wav
$(MODERNE)/combat/combat.mid: $(MODERNE)/combat/combat.py $(MODERNE)/compose.py
	cd $(MODERNE)/combat && python3 combat.py
$(OUTDIR)/MUSIC/COMBAT.MB.BIN: $(MODERNE)/combat/combat.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 200 --max 1280 --wav $(MODERNE)/combat/COMBAT.wav
$(MODERNE)/mort/mort.mid: $(MODERNE)/mort/mort.py $(MODERNE)/compose.py
	cd $(MODERNE)/mort && python3 mort.py
$(OUTDIR)/MUSIC/MORT.MB.BIN: $(MODERNE)/mort/mort.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 125 --max 1280 --no-loop --wav $(MODERNE)/mort/MORT.wav
$(MODERNE)/victoire/victoire.mid: $(MODERNE)/victoire/victoire.py $(MODERNE)/compose.py
	cd $(MODERNE)/victoire && python3 victoire.py
$(OUTDIR)/MUSIC/VICTOIRE.MB.BIN: $(MODERNE)/victoire/victoire.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 150 --max 1280 --no-loop --wav $(MODERNE)/victoire/VICTOIRE.wav
# Une musique par clairiere : 35 pieces du dossier moderne, clairieres/NN-nom,
# nommees d'apres le lieu ; les pages de chaque clairiere portent
# "MU <NOM>.MB" (SCOSWAMP.MORE/MUSIC/plan_mu.json, carte.json).
CLAIR    = $(MODERNE)/clairieres
CLAIRS   = $(OUTDIR)/MUSIC/COURBENS.MB.BIN \
           $(OUTDIR)/MUSIC/PATROUIL.MB.BIN \
           $(OUTDIR)/MUSIC/JARDINS.MB.BIN \
           $(OUTDIR)/MUSIC/LOUPS.MB.BIN \
           $(OUTDIR)/MUSIC/FEUFOLLET.MB.BIN \
           $(OUTDIR)/MUSIC/CROISEMENT.MB.BIN \
           $(OUTDIR)/MUSIC/GEANT.MB.BIN \
           $(OUTDIR)/MUSIC/BRIGANDS.MB.BIN \
           $(OUTDIR)/MUSIC/VASE.MB.BIN \
           $(OUTDIR)/MUSIC/SCORPNAIN.MB.BIN \
           $(OUTDIR)/MUSIC/AIGLE.MB.BIN \
           $(OUTDIR)/MUSIC/SABLES.MB.BIN \
           $(OUTDIR)/MUSIC/CROUPIE.MB.BIN \
           $(OUTDIR)/MUSIC/FALAISE.MB.BIN \
           $(OUTDIR)/MUSIC/PONT.MB.BIN \
           $(OUTDIR)/MUSIC/OISEAUX.MB.BIN \
           $(OUTDIR)/MUSIC/BRUME.MB.BIN \
           $(OUTDIR)/MUSIC/PIQUENIQUE.MB.BIN \
           $(OUTDIR)/MUSIC/SCORPIONS.MB.BIN \
           $(OUTDIR)/MUSIC/HERBEUX.MB.BIN \
           $(OUTDIR)/MUSIC/CRISTAL.MB.BIN \
           $(OUTDIR)/MUSIC/ANGOISSE.MB.BIN \
           $(OUTDIR)/MUSIC/LICORNE.MB.BIN \
           $(OUTDIR)/MUSIC/ARENE.MB.BIN \
           $(OUTDIR)/MUSIC/PINCES.MB.BIN \
           $(OUTDIR)/MUSIC/ORQUES.MB.BIN \
           $(OUTDIR)/MUSIC/BETE.MB.BIN \
           $(OUTDIR)/MUSIC/ARBRESEPEES.MB.BIN \
           $(OUTDIR)/MUSIC/ARAIGNEES.MB.BIN \
           $(OUTDIR)/MUSIC/GRENOUILLES.MB.BIN \
           $(OUTDIR)/MUSIC/PROFONDE.MB.BIN \
           $(OUTDIR)/MUSIC/MAITRELOUPS.MB.BIN \
           $(OUTDIR)/MUSIC/RONDPOINT.MB.BIN \
           $(OUTDIR)/MUSIC/TRONC.MB.BIN \
           $(OUTDIR)/MUSIC/BASSIN.MB.BIN
MUSICS  += $(CLAIRS)
musics: $(CLAIRS)      # la cible musics est definie plus haut : ses prerequis sont deja developpes

$(CLAIR)/01-courbens/courbens.mid: $(CLAIR)/01-courbens/courbens.py $(MODERNE)/compose.py
	cd $(CLAIR)/01-courbens && python3 courbens.py
$(OUTDIR)/MUSIC/COURBENS.MB.BIN: $(CLAIR)/01-courbens/courbens.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 176 --max 2304 --wav $(CLAIR)/01-courbens/COURBENS.wav
$(CLAIR)/02-patrouil/patrouil.mid: $(CLAIR)/02-patrouil/patrouil.py $(MODERNE)/compose.py
	cd $(CLAIR)/02-patrouil && python3 patrouil.py
$(OUTDIR)/MUSIC/PATROUIL.MB.BIN: $(CLAIR)/02-patrouil/patrouil.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 162 --max 2304 --wav $(CLAIR)/02-patrouil/PATROUIL.wav
$(CLAIR)/03-jardins/jardins.mid: $(CLAIR)/03-jardins/jardins.py $(MODERNE)/compose.py
	cd $(CLAIR)/03-jardins && python3 jardins.py
$(OUTDIR)/MUSIC/JARDINS.MB.BIN: $(CLAIR)/03-jardins/jardins.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 144 --max 2304 --wav $(CLAIR)/03-jardins/JARDINS.wav
$(CLAIR)/04-loups/loups.mid: $(CLAIR)/04-loups/loups.py $(MODERNE)/compose.py
	cd $(CLAIR)/04-loups && python3 loups.py
$(OUTDIR)/MUSIC/LOUPS.MB.BIN: $(CLAIR)/04-loups/loups.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 172 --max 2304 --wav $(CLAIR)/04-loups/LOUPS.wav
$(CLAIR)/05-feufollet/feufollet.mid: $(CLAIR)/05-feufollet/feufollet.py $(MODERNE)/compose.py
	cd $(CLAIR)/05-feufollet && python3 feufollet.py
$(OUTDIR)/MUSIC/FEUFOLLET.MB.BIN: $(CLAIR)/05-feufollet/feufollet.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 154 --max 2304 --wav $(CLAIR)/05-feufollet/FEUFOLLET.wav
$(CLAIR)/06-croisement/croisement.mid: $(CLAIR)/06-croisement/croisement.py $(MODERNE)/compose.py
	cd $(CLAIR)/06-croisement && python3 croisement.py
$(OUTDIR)/MUSIC/CROISEMENT.MB.BIN: $(CLAIR)/06-croisement/croisement.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 150 --max 2304 --wav $(CLAIR)/06-croisement/CROISEMENT.wav
$(CLAIR)/07-geant/geant.mid: $(CLAIR)/07-geant/geant.py $(MODERNE)/compose.py
	cd $(CLAIR)/07-geant && python3 geant.py
$(OUTDIR)/MUSIC/GEANT.MB.BIN: $(CLAIR)/07-geant/geant.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 138 --max 2304 --wav $(CLAIR)/07-geant/GEANT.wav
$(CLAIR)/08-brigands/brigands.mid: $(CLAIR)/08-brigands/brigands.py $(MODERNE)/compose.py
	cd $(CLAIR)/08-brigands && python3 brigands.py
$(OUTDIR)/MUSIC/BRIGANDS.MB.BIN: $(CLAIR)/08-brigands/brigands.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 180 --max 2304 --wav $(CLAIR)/08-brigands/BRIGANDS.wav
$(CLAIR)/09-vase/vase.mid: $(CLAIR)/09-vase/vase.py $(MODERNE)/compose.py
	cd $(CLAIR)/09-vase && python3 vase.py
$(OUTDIR)/MUSIC/VASE.MB.BIN: $(CLAIR)/09-vase/vase.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 138 --max 2304 --wav $(CLAIR)/09-vase/VASE.wav
$(CLAIR)/10-scorpnain/scorpnain.mid: $(CLAIR)/10-scorpnain/scorpnain.py $(MODERNE)/compose.py
	cd $(CLAIR)/10-scorpnain && python3 scorpnain.py
$(OUTDIR)/MUSIC/SCORPNAIN.MB.BIN: $(CLAIR)/10-scorpnain/scorpnain.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 184 --max 2304 --wav $(CLAIR)/10-scorpnain/SCORPNAIN.wav
$(CLAIR)/11-aigle/aigle.mid: $(CLAIR)/11-aigle/aigle.py $(MODERNE)/compose.py
	cd $(CLAIR)/11-aigle && python3 aigle.py
$(OUTDIR)/MUSIC/AIGLE.MB.BIN: $(CLAIR)/11-aigle/aigle.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 156 --max 2304 --wav $(CLAIR)/11-aigle/AIGLE.wav
$(CLAIR)/12-sables/sables.mid: $(CLAIR)/12-sables/sables.py $(MODERNE)/compose.py
	cd $(CLAIR)/12-sables && python3 sables.py
$(OUTDIR)/MUSIC/SABLES.MB.BIN: $(CLAIR)/12-sables/sables.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 144 --max 2304 --wav $(CLAIR)/12-sables/SABLES.wav
$(CLAIR)/13-croupie/croupie.mid: $(CLAIR)/13-croupie/croupie.py $(MODERNE)/compose.py
	cd $(CLAIR)/13-croupie && python3 croupie.py
$(OUTDIR)/MUSIC/CROUPIE.MB.BIN: $(CLAIR)/13-croupie/croupie.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 132 --max 2304 --wav $(CLAIR)/13-croupie/CROUPIE.wav
$(CLAIR)/14-falaise/falaise.mid: $(CLAIR)/14-falaise/falaise.py $(MODERNE)/compose.py
	cd $(CLAIR)/14-falaise && python3 falaise.py
$(OUTDIR)/MUSIC/FALAISE.MB.BIN: $(CLAIR)/14-falaise/falaise.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 144 --max 2304 --wav $(CLAIR)/14-falaise/FALAISE.wav
$(CLAIR)/15-pont/pont.mid: $(CLAIR)/15-pont/pont.py $(MODERNE)/compose.py
	cd $(CLAIR)/15-pont && python3 pont.py
$(OUTDIR)/MUSIC/PONT.MB.BIN: $(CLAIR)/15-pont/pont.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 154 --max 2304 --wav $(CLAIR)/15-pont/PONT.wav
$(CLAIR)/16-oiseaux/oiseaux.mid: $(CLAIR)/16-oiseaux/oiseaux.py $(MODERNE)/compose.py
	cd $(CLAIR)/16-oiseaux && python3 oiseaux.py
$(OUTDIR)/MUSIC/OISEAUX.MB.BIN: $(CLAIR)/16-oiseaux/oiseaux.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 168 --max 2304 --wav $(CLAIR)/16-oiseaux/OISEAUX.wav
$(CLAIR)/17-brume/brume.mid: $(CLAIR)/17-brume/brume.py $(MODERNE)/compose.py
	cd $(CLAIR)/17-brume && python3 brume.py
$(OUTDIR)/MUSIC/BRUME.MB.BIN: $(CLAIR)/17-brume/brume.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 128 --max 2304 --wav $(CLAIR)/17-brume/BRUME.wav
$(CLAIR)/18-piquenique/piquenique.mid: $(CLAIR)/18-piquenique/piquenique.py $(MODERNE)/compose.py
	cd $(CLAIR)/18-piquenique && python3 piquenique.py
$(OUTDIR)/MUSIC/PIQUENIQUE.MB.BIN: $(CLAIR)/18-piquenique/piquenique.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 176 --max 2304 --wav $(CLAIR)/18-piquenique/PIQUENIQUE.wav
$(CLAIR)/19-scorpions/scorpions.mid: $(CLAIR)/19-scorpions/scorpions.py $(MODERNE)/compose.py
	cd $(CLAIR)/19-scorpions && python3 scorpions.py
$(OUTDIR)/MUSIC/SCORPIONS.MB.BIN: $(CLAIR)/19-scorpions/scorpions.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 184 --max 2304 --wav $(CLAIR)/19-scorpions/SCORPIONS.wav
$(CLAIR)/20-herbeux/herbeux.mid: $(CLAIR)/20-herbeux/herbeux.py $(MODERNE)/compose.py
	cd $(CLAIR)/20-herbeux && python3 herbeux.py
$(OUTDIR)/MUSIC/HERBEUX.MB.BIN: $(CLAIR)/20-herbeux/herbeux.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 150 --max 2304 --wav $(CLAIR)/20-herbeux/HERBEUX.wav
$(CLAIR)/21-cristal/cristal.mid: $(CLAIR)/21-cristal/cristal.py $(MODERNE)/compose.py
	cd $(CLAIR)/21-cristal && python3 cristal.py
$(OUTDIR)/MUSIC/CRISTAL.MB.BIN: $(CLAIR)/21-cristal/cristal.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 156 --max 2304 --wav $(CLAIR)/21-cristal/CRISTAL.wav
$(CLAIR)/22-angoisse/angoisse.mid: $(CLAIR)/22-angoisse/angoisse.py $(MODERNE)/compose.py
	cd $(CLAIR)/22-angoisse && python3 angoisse.py
$(OUTDIR)/MUSIC/ANGOISSE.MB.BIN: $(CLAIR)/22-angoisse/angoisse.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 148 --max 2304 --wav $(CLAIR)/22-angoisse/ANGOISSE.wav
$(CLAIR)/23-licorne/licorne.mid: $(CLAIR)/23-licorne/licorne.py $(MODERNE)/compose.py
	cd $(CLAIR)/23-licorne && python3 licorne.py
$(OUTDIR)/MUSIC/LICORNE.MB.BIN: $(CLAIR)/23-licorne/licorne.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 142 --max 2304 --wav $(CLAIR)/23-licorne/LICORNE.wav
$(CLAIR)/24-arene/arene.mid: $(CLAIR)/24-arene/arene.py $(MODERNE)/compose.py
	cd $(CLAIR)/24-arene && python3 arene.py
$(OUTDIR)/MUSIC/ARENE.MB.BIN: $(CLAIR)/24-arene/arene.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 164 --max 2304 --wav $(CLAIR)/24-arene/ARENE.wav
$(CLAIR)/25-pinces/pinces.mid: $(CLAIR)/25-pinces/pinces.py $(MODERNE)/compose.py
	cd $(CLAIR)/25-pinces && python3 pinces.py
$(OUTDIR)/MUSIC/PINCES.MB.BIN: $(CLAIR)/25-pinces/pinces.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 176 --max 2304 --wav $(CLAIR)/25-pinces/PINCES.wav
$(CLAIR)/26-orques/orques.mid: $(CLAIR)/26-orques/orques.py $(MODERNE)/compose.py
	cd $(CLAIR)/26-orques && python3 orques.py
$(OUTDIR)/MUSIC/ORQUES.MB.BIN: $(CLAIR)/26-orques/orques.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 166 --max 2304 --wav $(CLAIR)/26-orques/ORQUES.wav
$(CLAIR)/27-bete/bete.mid: $(CLAIR)/27-bete/bete.py $(MODERNE)/compose.py
	cd $(CLAIR)/27-bete && python3 bete.py
$(OUTDIR)/MUSIC/BETE.MB.BIN: $(CLAIR)/27-bete/bete.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 143 --max 2304 --wav $(CLAIR)/27-bete/BETE.wav
$(CLAIR)/28-arbresepees/arbresepees.mid: $(CLAIR)/28-arbresepees/arbresepees.py $(MODERNE)/compose.py
	cd $(CLAIR)/28-arbresepees && python3 arbresepees.py
$(OUTDIR)/MUSIC/ARBRESEPEES.MB.BIN: $(CLAIR)/28-arbresepees/arbresepees.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 166 --max 2304 --wav $(CLAIR)/28-arbresepees/ARBRESEPEES.wav
$(CLAIR)/29-araignees/araignees.mid: $(CLAIR)/29-araignees/araignees.py $(MODERNE)/compose.py
	cd $(CLAIR)/29-araignees && python3 araignees.py
$(OUTDIR)/MUSIC/ARAIGNEES.MB.BIN: $(CLAIR)/29-araignees/araignees.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 150 --max 2304 --wav $(CLAIR)/29-araignees/ARAIGNEES.wav
$(CLAIR)/30-grenouilles/grenouilles.mid: $(CLAIR)/30-grenouilles/grenouilles.py $(MODERNE)/compose.py
	cd $(CLAIR)/30-grenouilles && python3 grenouilles.py
$(OUTDIR)/MUSIC/GRENOUILLES.MB.BIN: $(CLAIR)/30-grenouilles/grenouilles.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 176 --max 2304 --wav $(CLAIR)/30-grenouilles/GRENOUILLES.wav
$(CLAIR)/31-profonde/profonde.mid: $(CLAIR)/31-profonde/profonde.py $(MODERNE)/compose.py
	cd $(CLAIR)/31-profonde && python3 profonde.py
$(OUTDIR)/MUSIC/PROFONDE.MB.BIN: $(CLAIR)/31-profonde/profonde.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 136 --max 2304 --wav $(CLAIR)/31-profonde/PROFONDE.wav
$(CLAIR)/32-maitreloups/maitreloups.mid: $(CLAIR)/32-maitreloups/maitreloups.py $(MODERNE)/compose.py
	cd $(CLAIR)/32-maitreloups && python3 maitreloups.py
$(OUTDIR)/MUSIC/MAITRELOUPS.MB.BIN: $(CLAIR)/32-maitreloups/maitreloups.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 150 --max 2304 --wav $(CLAIR)/32-maitreloups/MAITRELOUPS.wav
$(CLAIR)/33-rondpoint/rondpoint.mid: $(CLAIR)/33-rondpoint/rondpoint.py $(MODERNE)/compose.py
	cd $(CLAIR)/33-rondpoint && python3 rondpoint.py
$(OUTDIR)/MUSIC/RONDPOINT.MB.BIN: $(CLAIR)/33-rondpoint/rondpoint.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 158 --max 2304 --wav $(CLAIR)/33-rondpoint/RONDPOINT.wav
$(CLAIR)/34-tronc/tronc.mid: $(CLAIR)/34-tronc/tronc.py $(MODERNE)/compose.py
	cd $(CLAIR)/34-tronc && python3 tronc.py
$(OUTDIR)/MUSIC/TRONC.MB.BIN: $(CLAIR)/34-tronc/tronc.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 150 --max 2304 --wav $(CLAIR)/34-tronc/TRONC.wav
$(CLAIR)/35-bassin/bassin.mid: $(CLAIR)/35-bassin/bassin.py $(MODERNE)/compose.py
	cd $(CLAIR)/35-bassin && python3 bassin.py
$(OUTDIR)/MUSIC/BASSIN.MB.BIN: $(CLAIR)/35-bassin/bassin.mid $(MUSIC)/midi_to_mb.py
	$(MB) $< $@ --bpm 150 --max 2304 --wav $(CLAIR)/35-bassin/BASSIN.wav

# La composition maison (accueil.py) reste disponible hors disque.
$(MUSIC)/accueil.mid: $(MUSIC)/accueil.py
	python3 $(MUSIC)/accueil.py

ay_notes.inc: $(OUTDIR)/MUSIC/ACCUEIL.MB.BIN

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
# HELPFR.TXT / HELPEN.TXT n'y figuraient pas du tout, OBJFR/OBJEN non plus,
# et MAP.BIN arrive avec le meme piege : une carte perimee sur le disque ne se
# voit pas, elle montre seulement les mauvaises clairieres.
PAYLOAD = $(shell find $(OUTDIR)/TEXTFR $(OUTDIR)/TEXTEN $(OUTDIR)/IMG $(OUTDIR)/MUSIC \
                       $(OUTDIR)/MSGFR.TXT $(OUTDIR)/MSGEN.TXT \
                       $(OUTDIR)/HELPFR.TXT $(OUTDIR)/HELPEN.TXT \
                       $(OUTDIR)/OBJFR.TXT $(OUTDIR)/OBJEN.TXT \
                       $(OUTDIR)/MAP.BIN \
                       $(OUTDIR)/SAVE \
                       $(OUTDIR)/TITLE.TXT \
                       -type f 2>/dev/null)

# La carte du Marais : 35 clairieres, leurs sorties, la table de rabattement
# page -> clairiere et les noms dans les deux langues, tires de la bible
# topologique SCOSWAMP.MORE/carte.json (voir SCOSWAMP/DOCS/CARTOGRAPHIE.md).
# L'empaqueteur retire la derniere extension : MAP.BIN devient MAP sur le
# volume, comme MUSIC/<NOM>.MB.BIN devient MUSIC/<NOM>.MB.
CARTE    = ../../SCOSWAMP.MORE/carte.json
$(OUTDIR)/MAP.BIN: $(TOOLS)/build_map.py $(CARTE)
	python3 $(TOOLS)/build_map.py --root ../..

map: $(OUTDIR)/MAP.BIN

hdv: $(HDV)

$(HDV): $(OUTDIR)/$(PROGRAM) $(OUTDIR)/$(LAUNCHER) $(BOOTTMPL) $(MUSICS) \
        $(OUTDIR)/MAP.BIN $(PAYLOAD) | $(VOLBUILD)
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
.PHONY: all hdv map release check clean distclean rebuild info install
