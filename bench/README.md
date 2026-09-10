# Les bancs

Ils jouent d'A2 File Cmd comme un utilisateur, dans un Apple IIe emule sans
fenetre, et verifient ce que l'ecran affiche. Rien n'est ajoute au binaire
livre pour cela : les adresses des variables observees viennent de la table de
symboles du lien (`build/a2fc.lbl`), et l'ecran est lu la ou l'Apple II le
range, en `$400-$7FF`.

Les bancs disquette utilisent l’image interne `dist/A2FILECMD-6502-BOOT-0.7.6.po`.
La conversion DSK publiée conserve les mêmes blocs ProDOS ; les `.po` ne sont
pas joints aux releases. Les bancs XL amorcent directement leur `.2mg`.

| | |
|---|---|
| `smoke.py` | la disquette publiee demarre-t-elle sur les panneaux ? |
| `awp.py` | un document AppleWorks (3.0 puis 2.x) se lit page par page, ligne pour ligne ce que tools/mkawp.py a ecrit |
| `subdir.py` | A2FILE.SYSTEM et A2FILE/ copies dans /HD/APPS d'un disque dur, lances de BASIC par `-APPS/A2FILE.SYSTEM` : surcouches, aide, formateur et retour se trouvent depuis ce dossier |
| `vdrive.py` | deux volumes par la ligne serie (VDrive) : le serveur `vsdrive_server.py` sert un .po au pont TCP de la Super Serial Card de POM2 (`pom2_playtest --ssc PORT`, 6 controles). La version Uthernet II (`pom2_playtest --uthernet`, `Pom2(uthernet=True)`) attend son pilote, voir le TODO |
| `ops.py` | les operations longues : la barre de progression sur toute la ligne pendant une copie de 300 Ko, ESC qui l'interrompt (fichier partiel retire), trois fichiers marques copies puis supprimes avec la barre |
| `chatmauve.py` | la carte RGB Le Chat Mauve en slot 7 (`pom2_playtest --chatmauve [variante]`, `Pom2(chatmauve=...)`) : ALIEN vu depuis A2FC est, pixel pour pixel, l'ecran que BASIC en fait avec la carte ; une seconde HGR, puis la mire DHGR brute (bandes unies, seize couleurs), puis ALIEN de nouveau identique -- le verrou de mode de la carte ne derive pas (6 controles par variante ; `python3 bench/chatmauve.py feline video7 eve`) |
| `machine.py` | le controle de machine du lanceur : MACHID falsifie a 64 Ko depuis BASIC, `-A2FILE.SYSTEM` refuse en 40 colonnes et rend la main ; un //c passe |
| `hd.py` | le disque dur `.2mg` publie amorce-t-il, avec son dossier DEMO au complet ; une page brute s'affiche, un `.2MG` s'ouvre comme un dossier |
| `run.py` | la session complete : naviguer, marquer, copier, deplacer, renommer, verrouiller, changer type et auxtype, creer un dossier, supprimer, lire un texte et des octets, editer, afficher les deux formats d'image et les comparer octet a octet, jouer la fanfare, ecrire et relire des images disque (.PO et .DSK) et copier une disquette, ouvrir une image comme un dossier et en extraire un fichier, lire un catalogue DOS 3.3 et en extraire un fichier, ouvrir le formateur, cliquer a la souris (pointeur, bornes, selection, ouverture, changement de panneau, barre de touches), lancer un programme Applesoft (depuis le disque dur, avec le BASIC.SYSTEM de la disquette) et revenir sur les panneaux par -A2FILE.SYSTEM. **72 controles.** |
| `disksingle.py` | comparaison exacte de 280 blocs sur un seul lecteur, changement D2 vers D1, noms des disques à chaque échange et images sources intactes |
| `six.py` | UNDELETE, DISKCMP, MKIMAGE, RESCUE, SYNC et TREE : volumes jetables, effacement ProDOS réel, contenu relu sur l’hôte et pile surveillée |
| `volinfo.py` | diagnostic ProDOS en lecture seule, disquette saine/corrompue et volume de 32 Mo, carte paginée et retour avec pile préservée, sur les deux processeurs |
| `blocktools.py` | VERIFY par lots avec fichier illisible, rapport VOLINFO relu sur la disquette éjectée, refus d’écrasement, BLKVIEW, recherche traversant les blocs, extraction exacte et bornes de navigation |
| `disasm.py` | désassemblage BIN/SYS, choix 6502/65C02, pagination, offsets 24 bits, export TXT relu octet par octet, refus d’écrasement, annulation et pile ; `A2FC_CAPTURE=/tmp/disasm.ppm` conserve une capture POM2 |
| `tree.py` | parcours de la racine XL jusqu’au résultat complet, totaux exacts comparés à l’image et pile préservée |
| `memory.py` | le creux maximal de la pile C, mesure en faisant travailler le programme |
| `pom2.py` | le pilote d'emulateur commun |

## Les deux editions

`dist/A2FILECMD-6502-BOOT-0.7.6.po` est l'**edition disquette**, construite en 6502
(`build-6502/`) avec le gestionnaire et les outils disque seulement : c'est
elle que les bancs amorcent par defaut, et sa table de symboles est prise
dans `build-6502/` sans rien dire. `run.py` y saute la section souris, et les
bancs de l'editeur, des images, des archives et des lecteurs (`shk.py`,
`bny.py`, `awp.py`, `find.py`, la session complete de `run.py`) ont besoin de
`make benchfloppy ARCH=enh` : `A2FC_IMG=A2FILECMD-full python3 bench/run.py`
prend `build/A2FILECMD-full.po`, la disquette 65C02 avec toutes les
surcouches et BASIC.SYSTEM, jamais publiee, et les symboles de `build/`.
`hd.py` amorce `dist/A2FILECMD-65C02-XL-0.7.6.2mg` ;
`A2FC_CPU=6502 A2FC_PRESET=iie_unenh python3 bench/hd.py` teste la XL 6502.
`extras.py` vérifie BOOT + EXTRA avec deux lecteurs, les échanges avec un
seul lecteur et BASIC.SYSTEM. Par défaut il prend le 6502 ;
`A2FC_IMG=A2FILECMD-65C02-BOOT python3 bench/extras.py` prend le 65C02.
La même variable choisit la disquette dans `smoke.py`. Les deux EXTRA sont
indépendantes. `python3 tools/check_images.py` relit les six volumes,
compare les surcouches aux builds respectifs et vérifie les copies `.dsk`.

Avec `A2FC_PRESET=iie_unenh`, POM2 est le IIe de 1983 (`pom2_playtest
--preset iie_unenh` : 6502 NMOS, firmware sans MouseText, `$FBC0 = $EA`) --
la seule machine qui prouve l'edition disquette, puisqu'un `stz` ou un `bra`
y sont des opcodes indefinis. La version 65C02 y affiche son refus.

## Les faire tourner

Il faut [POM2](https://github.com/habib256/pom2) construit sans interface
graphique, avec son serveur de commande (`--ai-control`) et une option
`--mouse` qui branche une AppleMouse II (HLE AppleWin) en slot 4 -- c'est
`pom2_playtest`, l'hote minimal du depot voisin, qui les a :

```sh
make disk
POM2=/chemin/vers/pom2_headless python3 bench/run.py --out /tmp/bench
POM2=/chemin/vers/pom2_headless python3 bench/memory.py
```

Sans la variable `POM2`, les bancs cherchent l'executable a l'emplacement par
defaut de l'auteur et s'arretent proprement s'il n'y est pas.

`Pom2(..., preset='iie')` est la machine par defaut, un Apple //e Enhanced
avec la carte HDV en slot 5 et un Mockingboard en slot 2. `preset='iic'`
donne un Apple //c (ROM 32 Ko) : son lecteur integre est le Disk II du slot
6, donc `--boot 6` amorce la disquette comme sur le //e, et le disque dur est
une unite SmartPort sur le port arriere, servie par le firmware du //c en
slot 5 (pas de carte, pas de Mockingboard). Les deux presets amorcent
`dist/A2FILECMD-6502-BOOT-0.7.6.po` jusqu'aux panneaux. `Pom2(..., floppy2=...)` met une
seconde disquette dans le lecteur 2 du meme Disk II des l'amorcage
(`pom2_playtest --disk2`) : un vrai DOS 3.3 dans un lecteur, sans passer par
`/disk` -- ce que le banc des disques physiques attendait.

## En integration continue

L'emulateur n'est pas sur les executeurs de GitHub, et il ne serait pas
raisonnable de l'y construire a chaque commit. Le travail `bench` du
[workflow](../.github/workflows/ci.yml) ne se declenche donc que si la
variable de depot **`POM2_RUNNER`** contient l'etiquette d'un executeur
auto-heberge qui a POM2 ; sinon il est saute, et la publication n'exige que
la construction et les tests hors emulateur. C'est la limite honnete du
dispositif : la compilation, les budgets memoire et la fabrication des images
sont verifies partout, la session complete la ou l'Apple II existe.

## Les quinze nouvelles surcouches

`bench/plugins.py` exécute les quinze bancs, avec un journal par outil.
Chaque banc construit son disque dur de travail et y ajoute explicitement
sa surcouche ; ceux qui écrivent vérifient ensuite la disquette du lecteur 2
sur l'hôte. Ces volumes sont des fixtures, pas les images publiées.

```sh
make disk
make xplugins ARCH=6502
A2FC_PRESET=iie_unenh python3 bench/plugins.py --jobs 3 --out /tmp/plugins-6502
A2FC_BUILD=build python3 bench/plugins.py --jobs 3 --out /tmp/plugins-enh
```

Les noms de bancs peuvent suivre les options pour une reprise ciblée
(`date fixtypes`, par exemple). Deux suites simultanées doivent utiliser
un décalage de ports distinct : `A2FC_PORT_OFFSET=100` pour la seconde.
`findfile.py` teste FIND : filtres type/date combinés, annulation et remise à zéro,
poursuite au-delà de 40 résultats par nom et contenu, sous-dossiers après le
premier lot, fin exacte, extraits avec positions, retour depuis l’aperçu et pile ;
l'ancien `find.py` teste SEARCH/COMPARE.
`crc.py` vérifie aussi les pages de 20 résultats sur un lot de 45 fichiers,
l’arrêt par ESC et la conservation des marques. Il compare les résultats avec
`zlib.crc32`, y compris un fichier vide,
les limites 255/256 et 511/512/513 octets, et les fichiers marqués.

La disquette `benchfloppy` garde les dix-neuf surcouches du noyau et
BASIC.SYSTEM pour les anciens bancs ; les quinze nouvelles ne tiennent pas
toutes dessus et se testent avec `plugins.py` sur disque dur.

Validation du 2026-09-09 : les quinze bancs passent sur IIe non enhanced
(6502) et IIe enhanced (65C02), **239 contrôles par processeur**. Les
contrôles d’amorçage des deux images publiées passent également.

`A2FC_PRESET=iie_unenh python3 bench/extras.py` amorce la disquette publiée
avec son complément : surcouche native, surcouche à table de services, menu
commun, renommage du volume, absence du disque, choix explicite du lecteur,
échanges sur un seul lecteur et retour au disque du fichier, annulation
après chargement d'une grande surcouche, puis BASIC.SYSTEM du complément.

Validation du complément (2026-09-09) : 19 contrôles POM2 et le contrôle
des images passent sur IIe non enhanced ; les 72 contrôles de la session
complète 65C02 et les 23 tests hors émulateur passent également.

`bench/format.py` vérifie la surcouche FORMAT depuis le BOOT publié :
protection du volume du programme, annulations sans écriture, disquette
protégée, formatage Disk II et RAM, SmartPort de 65535 blocs, bitmap,
restauration du résident et retour direct. Exécuter une fois avec
`A2FC_PRESET=iie_unenh`, puis avec `A2FC_IMG=A2FILECMD-65C02-BOOT`.

`goto.py` vérifie les favoris et les chemins directs (P) : casse, correction,
annulation, chemin absent, limite de 63 caractères et choix du panneau actif.
Il vérifie aussi le déplacement des favoris (M), sa persistance et les annulations.

Les sauvegardes GOTO sont testées avec écriture incomplète, échecs de renommage,
restauration du fichier original et collisions avec les fichiers de récupération.
