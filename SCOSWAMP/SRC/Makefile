# Makefile pour Le Marais aux Scorpions (SCOSWAMP)
# Compile pour Apple IIe Enhanced avec cc65

# Configuration
TARGET = apple2enh
PROGRAM = SCOSWAMP.BIN
CC = cc65
AS = ca65
LD = ld65
CL = cl65

# Répertoires
SRCDIR = .
OUTDIR = ..

# Fichiers source
SOURCES = scoswamp.c paths.c memory_swap.c
HEADERS = paths.h memory_swap.h
OBJECTS = scoswamp.o paths.o memory_swap.o

# Flags de compilation
# -t $(TARGET) : cible Apple IIe Enhanced
# -O : optimisation
# -Oirs : optimisation inline, registres, size
CFLAGS = -t $(TARGET) -O -Oirs

# Flags de linkage
# -Wl -S,0x4000 : démarrage à $4000 (préserve HGR Page 1 à $2000-$3FFF)
# -Wl -D,__EXEHDR__=0 : binaire brut sans en-tête AppleSingle
LDFLAGS = -t $(TARGET) -Wl -D,__EXEHDR__=0 -Wl -S,0x4000

# Cible par défaut
all: $(OUTDIR)/$(PROGRAM)

# Règle principale : lier les objets pour créer le binaire
$(OUTDIR)/$(PROGRAM): $(OBJECTS)
	$(CL) $(CFLAGS) $(LDFLAGS) -o $(OUTDIR)/$(PROGRAM) $(OBJECTS)
	@echo "==> Compilation terminée : $(OUTDIR)/$(PROGRAM)"
	@echo "    Adresse de démarrage : \$$4000 (HGR préservé à \$$2000-\$$3FFF)"

# Compilation des fichiers .c en .o
scoswamp.o: scoswamp.c paths.h memory_swap.h
	$(CC) $(CFLAGS) -o scoswamp.s scoswamp.c
	$(AS) -t $(TARGET) -o scoswamp.o scoswamp.s

paths.o: paths.c paths.h
	$(CC) $(CFLAGS) -o paths.s paths.c
	$(AS) -t $(TARGET) -o paths.o paths.s

memory_swap.o: memory_swap.c memory_swap.h
	$(CC) $(CFLAGS) -o memory_swap.s memory_swap.c
	$(AS) -t $(TARGET) -o memory_swap.o memory_swap.s

# Nettoyage des fichiers intermédiaires
clean:
	rm -f *.o *.s
	@echo "==> Fichiers intermédiaires supprimés"

# Nettoyage complet (inclut le binaire)
distclean: clean
	rm -f $(OUTDIR)/$(PROGRAM)
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

# Installation : copie le binaire dans le répertoire parent
install: all
	@echo "==> Binaire disponible dans $(OUTDIR)/$(PROGRAM)"

# Déclaration des cibles "phony" (ne correspondent pas à des fichiers)
.PHONY: all clean distclean rebuild info install

