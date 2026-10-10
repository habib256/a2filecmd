# Recensement du corpus Apple II

Mesure locale du 10 octobre 2026 ; sources ouvertes en lecture seule. Le registre des lecteurs à développer est dans [FORMATS-A-COUVRIR.md](FORMATS-A-COUVRIR.md).

## Périmètre et nombres

| Mesure | Nombre |
| --- | ---: |
| Archives/disquettes du cache Asimov | 1 878 |
| Éléments conteneurs dans l’ancien index | 2 253 |
| Entrées de fichiers dans l’ancien index | 48 831 |
| Disquettes supplémentaires MultiScribe/Apple Writer | 29 |
| Sources relues pour ce recensement | 1 907 |
| Images uniques DOS/ProDOS relues | 1 501 |
| Images identiques ignorées (SHA-256) | 113 |
| Occurrences de fichiers classées par le vrai C IDENT | 37 777 |
| Contenus distincts avec type/aux/système identiques | 27 408 |
| Éléments refusés/non lus lors du scan | 641 |

Le cache est une **sélection** de l’inventaire public Asimov, pas toute la production Apple II. Son ancien index comporte DOS, ProDOS, NuFX et des volumes non identifiés. La relecture actuelle couvre DOS 3.3 35×16 et ProDOS dans les images brutes/2IMG, ZIP et gzip pris en charge. Les deux inventaires ont des périmètres différents ; leurs nombres ne doivent pas être soustraits pour calculer un taux de couverture.

La déduplication des images utilise SHA-256. Celle des fichiers utilise (SHA-256 du contenu, type, type auxiliaire, système de fichiers), sans tenir compte du nom. Les nombres de fichiers sont donc encore des occurrences sur les images différentes. Les champs conservés par fichier comprennent source, membre ZIP, chemin interne, taille, type, auxiliaire, empreinte, description IDENT et lecteur choisi.

## Lecteurs proposés par IDENT

**Candidat** signifie que le détecteur propose un lecteur. Cela ne signifie ni que sa structure a été entièrement validée par le lecteur, ni que le rendu a été comparé à l’original. TEXT, HEX, les binaires supposés exécutables et le repli DOSVIEW ne sont pas une preuve qu’un format documentaire est couvert.

| Lecteur | Nature | Occurrences | Contenus distincts |
| --- | --- | ---: | ---: |
| DOSVIEW | générique/repli | 16247 | 12328 |
| DOSBAS | candidat | 6615 | 5292 |
| HEX | générique/repli | 4434 | 2682 |
| TEXT | générique/repli | 2628 | 1242 |
| BASLIST | candidat | 1732 | 1534 |
| DISASM | générique/repli | 1484 | 1142 |
| DOSINT | candidat | 1024 | 817 |
| DISASM | candidat | 954 | 459 |
| MERLIN | candidat | 894 | 461 |
| IMAGE | candidat | 269 | 207 |
| EXTASIE | candidat | 230 | 207 |
| FONTVIEW | candidat | 224 | 101 |
| AWP | candidat | 223 | 218 |
| AWDATA | candidat | 223 | 191 |
| SCASM | candidat | 108 | 100 |
| FONTRIX | candidat | 90 | 90 |
| PRINTSHOP | candidat | 86 | 81 |
| DOSMCS | candidat | 74 | 43 |
| INTBASIC | candidat | 47 | 42 |
| PASTEXT | candidat | 40 | 26 |
| PSBORDER | candidat | 25 | 25 |
| DOSNEWS | candidat | 22 | 22 |
| NEWSPAN | candidat | 15 | 15 |
| MACPAINT | candidat | 13 | 12 |
| MULTISCR | candidat | 13 | 13 |
| MAGWIN | candidat | 12 | 12 |
| MCS | candidat | 8 | 4 |
| LISAV2 | candidat | 7 | 7 |
| GMAGIC | candidat | 6 | 6 |
| NEWSPAGE | candidat | 5 | 5 |
| RUN | candidat | 5 | 4 |
| APPLEWR | candidat | 4 | 4 |
| DGRVIEW | candidat | 4 | 4 |
| DUET | candidat | 4 | 4 |
| DOCVIEW | candidat | 3 | 3 |
| SCIIBIN | candidat | 2 | 2 |
| MDVIEW | candidat | 1 | 1 |
| PAINT816 | candidat | 1 | 1 |
| PT3 | candidat | 1 | 1 |

Le repli DOSVIEW comprend aussi des formats déjà reconnus mais sans raccordement à leur lecteur spécialisé en DOS : notamment 1 162 candidats clip art Print Shop, 216 HRCG et 44 Fontrix. Ce ne sont pas 1 422 nouveaux formats. DOSVIEW sait lui-même afficher certaines images HGR brutes ; il ne faut pas classer tous ses fichiers comme illisibles.

## Lacunes et refus du scan

| Cause | Éléments |
| --- | ---: |
| unsupported filesystem/container | 448 |
| non-sequential DOS T/S list | 48 |
| sector | 43 |
| no supported image in container | 42 |
| short DOS binary | 14 |
| storage type 5 non gere | 10 |
| short DOS BASIC/source | 7 |
| cyclic DOS directory | 6 |
| directory backlink | 5 |
| volume length | 3 |
| block outside image | 3 |
| 'ascii' codec can't decode byte 0xc4 in position 4: ordinal not in range(128) | 3 |
| oversized seedling | 2 |
| invalid/unsupported 2IMG | 2 |
| empty live name | 2 |
| oversized sapling | 1 |
| 'ascii' codec can't decode byte 0xb8 in position 0: ordinal not in range(128) | 1 |
| 'ascii' codec can't decode byte 0xac in position 1: ordinal not in range(128) | 1 |

Une erreur de chaîne, de longueur, de secteur ou de nom refuse la lecture de l’image concernée. Les fichiers ProDOS étendus à deux fourches (stockage 5), Pascal, CP/M, Gutenberg, WOZ/NIB, NuFX/ShrinkIt et les géométries DOS non prises en charge par cet outil ne sont pas reclassés par cette passe. Leurs entrées éventuellement présentes dans l’ancien index restent comptées **séparément**. Les types DOS S/R et alternatifs non gérés ne sont pas extraits par `legacy_corpus.py`. Aucun lecteur WOZ n’a été ajouté.

Un type générique $06/$04/$F5, une adresse de chargement ou une taille isolée ne prouve pas un format : le corpus contient par exemple un fichier de jeu de 144 octets à $6800 qui pourrait être pris à tort pour une bordure Print Shop. De même, les $F5 de Talk Is Cheap sont des commandes, pas des projets New Print Shop.

## Reproduire

```sh
python3 tools/corpus_census.py \
  --corpus "$HOME/.cache/a2fc/asimov_corpus" \
  --extra /tmp/a2fc-wordpro-corpus/images \
  --output /tmp/a2fc-census
```

Le script compile le **vrai** `src/plugins/ident.c` et ses règles partagées, puis applique le routage DOS officiel. Les sondes nécessitant un FILE utilisent une copie temporaire jetable, sans écriture des sources. Les lecteurs de corpus bornent les blocs et détectent les cycles. Les tests couvrent une fausse signature ProDOS dans un disque DOS, cycles, blocs hors limites, fichiers creux et conteneurs 2IMG malformés.

Résultats complets de cette exécution : `/tmp/a2fc-census/{manifest,files,failures,summary}.json`. Le manifeste donne les SHA-256 des 1 907 sources. Le dépôt garde [le résumé](corpus/2026-10-10-summary.json) et [les types mesurés](corpus/2026-10-10-types.csv), pas les disquettes ni les documents d’origine.

Sources publiques : [inventaire Asimov](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/) et [index technique CiderPress II](https://ciderpress2.com/doc-index.html). Les priorités de développement sont un jugement, pas une statistique mondiale de popularité.

Le [lot PFS supplémentaire](PFS-WRITE.md) est recensé séparément : huit
contenus Write, deux File et six Plan distincts. Ses 28 sources ne sont
pas ajoutées rétroactivement au total de 1 907 sources ci-dessus.
