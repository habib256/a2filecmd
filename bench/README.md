# Les bancs

Ils jouent d'A2 File Cmd comme un utilisateur, dans un Apple IIe emule sans
fenetre, et verifient ce que l'ecran affiche. Rien n'est ajoute au binaire
livre pour cela : les adresses des variables observees viennent de la table de
symboles du lien (`build/a2fc.lbl`), et l'ecran est lu la ou l'Apple II le
range, en `$400-$7FF`.

Les bancs disquette utilisent l’image interne `dist/A2FILECMD-6502-BOOT-0.9.0.po`.
La conversion DSK publiée conserve les mêmes blocs ProDOS ; les `.po` ne sont
pas joints aux releases. Les bancs XL amorcent directement leur `.2mg`.

| | |
|---|---|
| `smoke.py` | la disquette publiee demarre-t-elle sur les panneaux ? |
| `awp.py` | un document AppleWorks (3.0 puis 2.x) se lit page par page, ligne pour ligne ce que tools/mkawp.py a ecrit |
| `subdir.py` | A2FILE.SYSTEM et A2FILE/ copies dans /HD/APPS d'un disque dur, lances de BASIC par `-APPS/A2FILE.SYSTEM` : surcouches, aide, formateur et retour se trouvent depuis ce dossier |
| `vdrive.py` | deux volumes par la ligne serie (VDrive) : le serveur `vsdrive_server.py` sert un .po au pont TCP de la Super Serial Card de POM2 (`pom2_playtest --ssc PORT`, 6 controles). La version Uthernet II (`pom2_playtest --uthernet`, `Pom2(uthernet=True)`) attend son pilote, voir le TODO |
| `data_safety.py` | copies et déplacements vérifiés, deux sauvegardes successives, avertissement RAM avant écriture et comparaison des octets AUX après refus ; volumes jetables |
| `sequences.py` | les enchainements entre outils, etat et octets relus apres la sortie : image HGR puis musique puis copie de deux fichiers marques ; ESC pendant une copie de 300 Ko puis la meme copie au bout puis V vers un autre dossier ; disquette remplacee en lecteur 2 sous un panneau ouvert, volumes relus, copie depuis chacune. Deux CPU sur la disquette de banc. |
| `ops.py` | les operations longues : la barre de progression sur toute la ligne pendant une copie de 300 Ko, ESC qui l'interrompt (fichier partiel retire), trois fichiers marques copies puis supprimes avec la barre |
| `chatmauve.py` | la carte RGB Le Chat Mauve en slot 7 (`pom2_playtest --chatmauve [variante]`, `Pom2(chatmauve=...)`) : ALIEN vu depuis A2FC est, pixel pour pixel, l'ecran que BASIC en fait avec la carte ; une seconde HGR, puis la mire DHGR brute (bandes unies, seize couleurs), puis ALIEN de nouveau identique -- le verrou de mode de la carte ne derive pas (6 controles par variante ; `python3 bench/chatmauve.py feline video7 eve`) |
| `machine.py` | le controle de machine du lanceur : MACHID falsifie a 64 Ko depuis BASIC, `-A2FILE.SYSTEM` refuse en 40 colonnes et rend la main ; sur IIe enhanced a 6502 NMOS (`--preset iie_nmos`) l'edition 65C02 refuse le processeur, la 6502 passe ; un //c passe |
| `iic.py` | l'Apple //c (`preset='iic'`) : la disquette 6502 publiee dans le lecteur integre avec un disque SmartPort (volumes, lecture, copies vers /RAM et vers le SmartPort relues dans le `.hdv`, pile C et plancher, disquette jamais ecrite), puis la XL 65C02 amorcee par le SmartPort (copie relue, pile, souris du //c : statut, pointeur, borne, clics). **20 controles.** La copie disquette → SmartPort, lecteur 2 vide, demande POM2 7dc429b ou plus recent (le sequenceur Disk II n'etait pas remis a zero moteur allume sur un lecteur vide) : `make pom2host` apres la mise a jour de `~/src/pom2` |
| `hd.py` | le disque dur `.2mg` publie amorce-t-il, avec son dossier DEMO au complet ; une page brute s'affiche, un `.2MG` s'ouvre comme un dossier |
| `run.py` | la session complete : naviguer, marquer, copier, deplacer, renommer, verrouiller, changer type et auxtype, creer un dossier, supprimer, lire un texte et des octets, editer, afficher les deux formats d'image et les comparer octet a octet, jouer la fanfare, ecrire et relire des images disque (.PO et .DSK) et copier une disquette, ouvrir une image comme un dossier et en extraire un fichier, lire un catalogue DOS 3.3 et en extraire un fichier, ouvrir le formateur, cliquer a la souris (pointeur, bornes, selection, ouverture, changement de panneau, barre de touches), lancer un programme Applesoft (depuis le disque dur, avec le BASIC.SYSTEM de la disquette) et revenir sur les panneaux par -A2FILE.SYSTEM. **73 controles** (74 sur la XL 65C02, 66 sur la XL 6502). |
| `disksingle.py` | comparaison exacte de 280 blocs sur un seul lecteur, changement D2 vers D1, noms des disques à chaque échange et images sources intactes |
| `six.py` | UNDELETE, DISKCMP, MKIMAGE, RESCUE, SYNC et TREE : volumes jetables, effacement ProDOS réel, contenu relu sur l’hôte et pile surveillée |
| `volinfo.py` | diagnostic ProDOS en lecture seule, disquette saine/corrompue et volume de 32 Mo, carte paginée et retour avec pile préservée, sur les deux processeurs |
| `fixit.py` | FIXIT, chantier Read (increments 1 a 8) : volume jetable sain controle depuis la liste des volumes puis depuis un dossier, ecran « READ ONLY » sans aucun constat, ligne de resume « 0 findings.  R rescan  ESC/RETURN back » sans aucune touche du chantier WRITE, et verdict « consistent » ; puis la meme disquette cassee sur l'hote en dix-sept endroits, qui remplit une page de 18 lignes : chaque identifiant de l'oracle est nomme avec son compteur, son premier bloc et son premier rang, « more findings than the table holds » clot les seize echantillons, « Key: next / ESC: back » attend une touche, `R` refait le parcours et rend exactement les memes lignes, et le verdict compte les constats sans rien ecrire ; Echap avec resident et pile C preserves, les deux disquettes relues octet pour octet et la saine toujours saine pour `tools/prodos_check.py`, sur les deux processeurs |
| `repair.py` | REPAIR, chantier WRITE (increments 9 a 15) : quatre disquettes jetables, chacune son amorcage, les deux moities de l'oracle hote recoupees avant chacun. (1) seule la bitmap est fausse (`bitmap_lost` + `bitmap_free_used` + `bitmap_reserved_free`) : l'ecran de plan nomme chaque controle avec son compteur, la ligne « Plan: 3 corrections over 1 blocks. Nothing written yet. » et les seules touches « F fix  ESC back » ; `F` puis le mot FIX tape en entier rendent « Applied 1 of 1 blocks; rescan clean: repaired. », et sur l'hote la disquette est saine pour `tools/prodos_check.py` avec le SEUL bloc de bitmap modifie. (2) le repertoire ET la bitmap (`file_count_high` + `dir_eof_wrong` + `parent_wrong` + `bitmap_lost`) : les quatre controles au plan, « Plan: 4 corrections over 4 blocks. », « Applied 4 of 4 blocks; rescan clean: repaired. », disquette saine sur l'hote et seuls les blocs que l'oracle nomme modifies. (3) blocs partages : refus (« Cross-linked blocks: ... »). (4) Echap a la question. Les disquettes refusees relues octet pour octet, resident et pile C preserves, sur les deux processeurs |
| `macpaint.py` | MACPAINT, les documents MacPaint synthetiques (`tools/macpaint_ref.py`) : refus d'un binaire, d'un flux coupe et d'une version d'en-tete inconnue, AUX intacte ; Retour sur un `.MAC`, les deux plans relus a chaque position du defilement (Bas jusqu'a la butee 528, Haut jusqu'a 0), « /RAM rebuilt. », curseur, resident et pile C ; un `.PNTG` avec en-tete MacBinary par le menu. 20 controles sur les deux processeurs |
| `arlequin.py` | ARLEQUIN, les images `$F8` d'ARLEQUIN 1.1 (Le Chat Mauve), sur une Feline (`Pom2(chatmauve='feline')`) : refus d'un binaire, d'un `$F8` sans signature et d'un flux coupe, AUX intacte apres chacun ; une image plein ecran et une fenetre 9 x 81 synthetiques (`tools/arlequin_ref.py`), et AIGLE et FE1 du constructeur si `/GISTDATA` est la : les deux plans relus contre la reference (noir compris autour d'une fenetre), « /RAM rebuilt. », curseur, resident et pile C ; Retour ouvre ARLEQUIN. 21 controles sur les deux processeurs |
| `bigvol.py` | FIXIT et REPAIR au-dela d'une page de bitmap : un volume jetable de 20 000 blocs en S5,D2 (`pom2_playtest --hd2`, `Pom2(hd2=...)`), casse sur l'hote (FILE_COUNT d'un sous-dossier lointain, un bloc perdu dans la quatrieme page). Echap a la question de profondeur et N a celle de /RAM : « Scan cancelled », motif en AUX `$4000` intact ; Q puis Y : controle rapide titre « - QUICK », FILE_COUNT seul, reclamations en AUX ; R puis F sans nouvelle question /RAM : FILE_COUNT et BM_LOST aux blocs de l'oracle ; REPAIR (question /RAM reposee) : « Plan: 2 corrections over 2 blocks », FIX, « repaired » ; sur l'hote le volume est sain et seuls la cle du sous-dossier et la page de bitmap ont bouge. Cycles des deux controles affiches ; resident, pile C et /RAM verifies, sur les deux processeurs (32 controles) |
| `menu.py` | Catégories complètes, ordre alphabétique, flèches ±6, Échap, conservation AUX, questions et saisies en inverse |
| `blocktools.py` | VERIFY par lots avec fichier illisible, rapport VOLINFO relu sur la disquette éjectée, refus d’écrasement, BLKVIEW, recherche traversant les blocs, extraction exacte et bornes de navigation |
| `disasm.py` | désassemblage BIN/SYS, choix 6502/65C02, pagination, offsets fichier sur sept chiffres et adresses CPU 16 bits, export TXT relu octet par octet, refus d’écrasement, annulation et pile ; `A2FC_CAPTURE=/tmp/disasm.ppm` conserve une capture POM2 |
| `ident.py` | formats de fichiers, textes Apple à bit haut, UTF-8 sur 2/3/4 octets, BOM, fins de ligne et séquences invalides ou coupées à 512 octets |
| `hexnav.py` | HEX : offset fichier sur sept chiffres, G/R/E, pages avant/arrière, annulation, hors fichier, dernier octet, fichier vide et pile |
| `textrestart.py` | TEXT : pages, R vers le début, retour borné et sélection restaurée |
| `restart_readers.py` | BASLIST et AppleWorks : page suivante puis R vers la première page |
| `shapes.py` | SHAPES : une table refusee, une table synthetique par Retour (pages 1 et 2, Espace en fin, B, ligne d'etat), les trois tables de CiderPress II par le menu, chaque page HGR comparee a `tools/shapes_ref.py` ; curseur, resident, pile C et /RAM intacts |
| `dos33w.py` | DOS33W sur une vraie disquette DOS 3.3 en lecteur 2 (jetable) : un fichier verrouille refuse, la question declinee qui n'ecrit rien, la suppression dont les secteurs reviennent exactement au bitmap et dont l'entree garde sa piste pour UNDELETE, le renommage qui garde les octets et les secteurs, un nom deja pris refuse. Le disque relu par `tools/mini33_fixture.py` a chaque etape. Port 6912 |
| `imgput.py` | IMGPUT : une image ProDOS de 280 blocs fabriquee par `tools/mkvolume.py`, posee sur le disque du banc et **montee** dans le panneau droit (Retour sur le .PO) ; la question declinee qui n'ecrit rien, deux fichiers copies dedans depuis le menu, un nom deja present refuse. A l'arret l'image est extraite du disque dur et relue comme un volume : octets, type et auxtype exacts, le fichier deja la intact, le compte de fichiers a jour, et chaque bloc que l'entree nomme marque occupe dans le bitmap -- l'entree qui nomme un bloc libre est la seule panne qui corrompt un volume au lieu de perdre de la place. 21/21 sur les deux processeurs, la copie par **C** comprise. Port 6914 |
| `dosrepl.py` | DOSREPL sur une vraie disquette DOS 3.3 en lecteur 2 (jetable) : la question declinee qui n'ecrit rien, un Applesoft puis un binaire de 8 Ko remplaces sous leur nom DOS avec leur prefixe exact, les secteurs de l'ancien rendus au bitmap et la nouvelle copie ailleurs, le voisin et le disque source intacts, un second remplacement qui redonne le meme disque, et un disque a un secteur pres trop plein pour porter les deux copies refuse. Le disque relu par `tools/mini33_fixture.py` a chaque etape, ejecte d'abord puisque POM2 ne le reecrit qu'a l'ejection. Port 6913 |
| `cpmw.py` | CPMW : un volume CP/M fabrique par `tools/cpm_ref.py` dans l'ordre `apple` sans que la surcouche le sache, curseur dessus a gauche et trois fichiers ProDOS a droite ; la question declinee, les trois mis dans le volume, un second passage ou les trois noms sont pris. A l'arret l'image est relue par la meme reference : octets exacts, remplissage a l'octet de fin CP/M, aucun bloc reclame par deux fichiers, et -- le controle qui compte -- les deux fichiers deja la intacts, car un secteur CP/M est la moitie d'un bloc ProDOS et chaque ecriture est une lecture-modification-ecriture. 17/17 sur les deux processeurs. Port 6916 |
| `pascalw.py` | PASCALW : un volume Apple Pascal fabrique par `tools/pascal_ref.py`, pose sur le disque du banc, curseur dessus a gauche et trois fichiers ProDOS a droite ; la question declinee qui n'ecrit rien, les trois mis dans le volume, un second passage ou les trois noms sont pris et rien n'est ecrase. A l'arret l'image est extraite du disque dur et relue par la meme reference : octets exacts, genres UCSD inverses de ceux du lecteur ($02 code, $03 texte, $05 donnees, le reste non type), le fichier deja la intact, et aucune plage de blocs qui en chevauche une autre -- un volume UCSD n'a pas de bitmap pour le rattraper. 13/13 sur les deux processeurs. Port 6915 |
| `foreignfs.py` | PASCAL et CPM : un volume Apple Pascal et un disque CP/M fabriques par `tools/pascal_ref.py` et `tools/cpm_ref.py`, poses en images sur le disque du banc, extraits dans /WORKHD/OUT depuis le menu ; le disque relu a l'arret contre les deux references, octet pour octet, les types ProDOS des genres Pascal, les noms deja pris sautes au second passage, et les images elles-memes inchangees. L'ordre des secteurs CP/M n'est pas dit a la surcouche : elle le trouve. Port 6911 |
| `squeeze.py` | UNSQ par le menu et par Retour sur un .QQ : un .QQ et une archive ACU synthetiques (dossier saute, nom deja pris compte), un .QQ abime qui ne laisse rien, le .QQ de l'archive Binary II et IconEd.ACU de CiderPress II quand le cache les a ; les fichiers relus sur un second disque dur contre `tools/squeeze_ref.py`. Puis le meme programme Business BASIC liste deux fois, par T sur le fichier $09 et par Retour sur sa copie nommee .BA3 mais typee $06, et TIMESET (cache local) : l'ecran contre `tools/busbasic_ref.py`. Port 6859 |
| `wrappers.py` | UNWRAP et SCIIBIN : les trois AppleSingle de `data/CP2` par Retour, un MacBinary par le menu, un nom deja pris refuse ; Z-Link en cinq parties BinSCII, SHRINKIT refuse car deja present, une deuxieme partie seule refusee ; les fichiers relus sur un second disque dur contre `tools/unwrap_ref.py` et `tools/binscii_ref.py` |
| `diskcopy.py` | une image DiskCopy 4.2 de 800 Ko ouverte comme dossier (resident) et un fichier copie hors d'elle ; une image DiskCopy Mac refusee ; IMGCONV .DC -> .PO, .PO -> .DC (octet pour octet `tools/dc42.py`, type `$E0/$8005`) et le refus d'une somme fausse, sorties sur un second disque dur (`hd2`). 11 controles sur les deux processeurs |
| `awdata.py` | AWDATA : un tableur synthetique de 23 nombres relus contre le FOUT de reference (`tools/awdata_ref.py`, 9e chiffre a une unite pres), la formule de la page 2, (end), B et Echap, curseur, resident et pile C ; PRESIDENTS (4 fiches, barre, R) par le menu et les 16 pages de MATH.QUIZ par Retour, de `data/CP2`. 40 controles sur les deux processeurs |
| `mdview.py` | Markdown, repliement, CRLF/bit haut, document de 67 pages, historique circulaire de 64 pages, ligne de 22 Ko sans saut (280 lignes écran), UTF-8 majoritaire/BOM/caractère coupé à 2 Ko, blocs de code, retour et reprise par R |
| `tree.py` | parcours de la racine XL jusqu’au résultat complet, totaux exacts comparés à l’image et pile préservée |
| `memory.py` | le creux maximal de la pile C, mesure en faisant travailler le programme |
| `mini33.py` | the Apple II+ 48 KB DOS 3.3 edition on an NMOS core: panels, pagination, long names, preview, malformed and missing disks, quit and relaunch, and changed-character-only screen writes through watchpoints |
| `mini33_write.py` | the same edition's real DOS writes on disposable images: cancel, hardware write protection, a copy that stays on the panels, a refused collision, then DOS BLOAD and SAVE over the result |
| `mini33_ops.py` | tags, hi-res viewer, exclusive TXT create, catalog-first delete, and a tagged two-file copy, on disposable images |
| `mini33_format.py` | F on disposable images: refused on the boot drive, cancelled, refused on a write-protected disk, then a real RWTS format with DOS copied from the boot disk, every shipped file copied onto it, and the result booted into A2FC Mini; then the same from a zero-filled image and from a never formatted diskette (POM2's `insertBlankDisk`, no address fields; `--no-fresh` skips it), watching the progress bar. Every Mini bench reads the boot disk's file count from the image (`MINI_FILES`), so a dist disk holding more than the four built files still passes |
| `mini33_time.py` | what the disk paths cost in cycles, since a missed sector is a whole 200 000-cycle revolution: catalog reads and a 48-sector copy, with the copy's writing phase broken down per RWTS call (reads, writes, read-backs, drive switches, revolutions per data sector; `--max-rev-per-sector` turns that last one into a failure). Read-only on the catalog paths |
| `pom2.py` | le pilote d'emulateur commun |

## Les deux editions

`dist/A2FILECMD-6502-BOOT-0.9.0.po` est l'**edition disquette**, construite en 6502
(`build-6502/`) avec le gestionnaire et les outils disque seulement : c'est
elle que les bancs amorcent par defaut, et sa table de symboles est prise
dans `build-6502/` sans rien dire. `run.py` y saute la section souris, et les
bancs de l'editeur, des images, des archives et des lecteurs (`shk.py`,
`bny.py`, `awp.py`, `find.py`, la session complete de `run.py`) ont besoin de
`make benchfloppy ARCH=enh` : `A2FC_IMG=A2FILECMD-full python3 bench/run.py`
prend `build/A2FILECMD-full.po`, la disquette 65C02 des scénarios de session
avec BASIC.SYSTEM, jamais publiée, et les symboles de `build/`. Avec
`A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh A2FC_IMG=A2FILECMD-full`, la
même disquette de banc en 6502 (`make benchfloppy ARCH=6502`) sert aux bancs
d'archives (`shk.py`, `bny.py`) sur ce CPU. Le lecteur
MUSIC est chargé depuis une copie de MEDIA en lecteur 2. Les bancs AWP,
Binary II et ShrinkIt utilisent `archive_support.py` pour substituer leur
lecteur à FORMAT/DISKIMG dans une copie jetable de cette disquette : tous
les outils ne tiennent plus ensemble sur 140 Ko.
`hd.py` amorce `dist/A2FILECMD-65C02-XL-0.9.0.2mg` ;
`A2FC_CPU=6502 A2FC_PRESET=iie_unenh python3 bench/hd.py` teste la XL 6502.
`run.py --xl 65C02` et `run.py --xl 6502` jouent la session complète sur
la XL publiée de ce processeur (la 6502 sur le IIe non enhanced, sans
souris) : POM2 ne prend qu’un disque dur, donc le volume XL est rebâti
avec les fichiers de travail à sa racine, après avoir vérifié qu’il
redonne sans eux le `.2mg` publié octet à octet.
`extras.py` vérifie BOOT + FILES et les demandes des autres catégories avec deux lecteurs, les échanges avec un
seul lecteur et BASIC.SYSTEM. Par défaut il prend le 6502 ;
`python3 bench/extras.py` vérifie les mêmes disquettes 6502 sur IIe enhanced.
La même variable choisit la disquette dans `smoke.py`. Les quatre catégories sont
indépendantes. `python3 tools/check_images.py` relit les six volumes,
compare les surcouches aux builds respectifs et vérifie les copies `.dsk`.

Avec `A2FC_PRESET=iie_unenh`, POM2 est le IIe de 1983 (`pom2_playtest
--preset iie_unenh` : 6502 NMOS, firmware sans MouseText, `$FBC0 = $EA`) --
la seule machine qui prouve l'edition disquette, puisqu'un `stz` ou un `bra`
y sont des opcodes indefinis. La version 65C02 y affiche son refus.
Avec `iie_nmos`, POM2 garde le firmware enhanced mais met un 6502 NMOS :
la machine ou seul le test du processeur arrete l'edition 65C02.

## Les faire tourner

Pour la Mockingboard 4c sur //c, construire l'hôte isolé avec
`python3 bench/build_pt3_trace.py`, puis lancer
`POM2=/tmp/a2fc-pt3-trace A2FC_IMG=A2FILECMD-full python3 bench/mb4c.py` et
`POM2=/tmp/a2fc-pt3-trace A2FC_BUILD=build-6502 python3 bench/mb4c.py`.
Le banc active la carte via `A2FC_MB4C` seulement dans ses processus enfants,
la place sur le slot virtuel 3 et vérifie la fenêtre `$C400` du nouveau cœur
POM2. Il teste MB1/PT3 avec et sans carte, pause/sortie, registres AY/IRQ et
conservation des octets AUX et du volume jetable. Le corpus PT3 est lu sans
modification. L'ancien hôte `pom2_playtest` ne branche aucune carte sur //c.

Si `mb4c.py` passe sa phase « sans carte » (5/5) puis expire sur
`WELCOME.MB on MB4c`, c'est la bibliothèque de l'émulateur qui est en
retard sur ses sources : la carte vient d'une version de POM2 plus récente
que `~/src/pom2/build/libpom2_core.a`. Reconstruire POM2, puis
`python3 bench/build_pt3_trace.py` (et `make pom2host`), avant de chercher
du côté d'A2FC. Constaté le 18 septembre 2026 avec POM2 0.9.4.

`bench/launch.py` exécute un programme Integer BASIC et un programme Applesoft,
après annulation puis confirmation, en contrôlant leurs octets sur le volume
jetable. Utiliser `A2FC_IMG=A2FILECMD-full` ou `A2FC_BUILD=build-6502` ; avec
ce dernier, `--companion` teste BOOT + DEVTOOLS et les programmes sur disque dur.
Les scénarios sur BOOT plein répondent explicitement à l'avertissement de
configuration non sauvegardée. `bench/mb4c.py` couvre aussi la fin naturelle
des deux lecteurs, sans touche, avec restauration des panneaux et silence AY.

Limite de validation : la dernière étape de `extras.py` (relancement manuel
d'A2FC après le programme Applesoft avec `HOME`) peut finir en `SYNTAX ERROR`
dans POM2 //e non amélioré. Le lancement depuis DEVTOOLS passe, mais le banc
complet reste en échec ; voir le suivi LAUNCHER dans `TODO.md`.

Il faut [POM2](https://github.com/habib256/pom2) construit sans interface
graphique, avec son serveur de commande (`--ai-control`) et une option
`--mouse` qui branche une AppleMouse II (HLE AppleWin) en slot 4 -- c'est
`pom2_playtest`, l'hote minimal dont la source est dans ce depot
(`bench/pom2_playtest/`), construit par `make pom2host` dans `build/` contre
la bibliotheque de l'emulateur (`POM2_ROOT`, par defaut `~/src/pom2`) :

```sh
make disk
POM2=/chemin/vers/pom2_headless python3 bench/run.py --out /tmp/bench
POM2=/chemin/vers/pom2_headless python3 bench/memory.py
```

Sans la variable `POM2`, les bancs cherchent `build/pom2_playtest` et
s'arretent proprement s'il n'y est pas : `make pom2host` d'abord.

L'hote doit **activer l'ecriture differee du disque dur et la vider a
l'arret** (`setWriteBackEnabled(true)` sur la carte HDV et l'unite SmartPort
du //c, `flushBay`/`saveDirty` avant de rendre la main) : POM2 garde les
blocs ecrits par l'invite en RAM et ne les recopie dans le `.hdv` que sur
demande. Sans cela, toute comparaison d'octets du `.hdv` apres l'arret est
creuse -- un fichier copie en est simplement absent -- et les controles
« preserve every disk byte » passent a vide. `pom2_playtest` le fait depuis le
14 septembre 2026 ; pour s'en assurer sur un autre hote, copier un fichier
seul dans le banc et relire le `.hdv` avec `tools/prodos_read.py`.

`Pom2(..., preset='iie')` est la machine par defaut, un Apple //e Enhanced
avec la carte HDV en slot 5 et un Mockingboard en slot 2. `preset='iic'`
donne un Apple //c (ROM 32 Ko) : son lecteur integre est le Disk II du slot
6, donc `--boot 6` amorce la disquette comme sur le //e, et le disque dur est
une unite SmartPort sur le port arriere, servie par le firmware du //c en
slot 5 (pas de carte, pas de Mockingboard). Les deux presets amorcent
`dist/A2FILECMD-6502-BOOT-0.9.0.po` jusqu'aux panneaux. `Pom2(..., floppy2=...)` met une
seconde disquette dans le lecteur 2 du meme Disk II des l'amorcage
(`pom2_playtest --disk2`) : un vrai DOS 3.3 dans un lecteur, sans passer par
`/disk` -- ce que le banc des disques physiques attendait.
`Pom2(..., hd2=...)` branche un second disque dur, lecteur 2 de la carte HDV
du slot 5 (`pom2_playtest --hd2`, pas sur le //c), recopie dans son fichier a
l'arret comme le premier : le volume de plus de 4 096 blocs que `bigvol.py`
fait controler et reparer sans que ce soit celui du programme. Un hote
construit avant le 17 septembre 2026 refuse l'option : `make pom2host`.

## Les jouer tous : `bench/all.py`

La table de `bench/all.py` porte **chaque** banc avec la machine et l'image
qu'il demande. C'est elle que rejoue la qualification d'une version, et c'est
elle que joue la CI, groupe par groupe :

```sh
make qualify                      # disques, disquettes de banc, puis tout
python3 bench/all.py --list       # ce qui serait joue, et ce qui manque
python3 bench/all.py --group media cards --out /tmp/a2fc-bench
python3 bench/all.py --only fixit repair --jobs 2
```

`--jobs` sert à itérer, pas à qualifier : plusieurs émulateurs à 200 000
cycles par seconde se privent l'un l'autre, et les bancs qui comptent le
temps réel (une copie nibble, une copie interrompue par Échap) expirent
alors sans que rien ne soit cassé. `make qualify` joue la table un banc à
la fois.

Un pas dont la fixture manque est **SKIP**, avec la commande qui la
construit ; `--strict` en fait un echec, ce que veut une publication.
`--setup` construit ce qu'une commande sait construire (les hotes POM2
jetables ; avec `--make`, les disques aussi). Le port de chaque banc est lu
dans sa source, jamais recopie ici : avec `--jobs`, deux bancs qui
repondraient sur le meme port ne partent jamais ensemble. Un journal par pas
dans `--out`, et un resume qui nomme les echecs et les sauts.

Avant, la liste vivait dans `ci.yml` : vingt-cinq bancs sur les
quatre-vingt-treize de ce dossier, et les sept bancs des formats de la 0.8.9
n'en faisaient pas partie -- rien ne le disait. `tools/test_bench_inventory.py`,
dans `make test`, refuse desormais un fichier de banc qui n'est dans aucun
pas (ou qui n'est pas declare comme utilitaire dans `HELPERS`), et verifie
que le travail `bench` de la CI joue bien tous les groupes de la table.
`bench/plugins.py` garde la liste des surcouches a table de services : c'est
le pas `plugins` du lanceur.

## En integration continue

L'emulateur n'est pas sur les executeurs de GitHub, et il ne serait pas
raisonnable de l'y construire a chaque commit. Le travail `bench` du
[workflow](../.github/workflows/ci.yml) ne se declenche donc que si la
variable de depot **`POM2_RUNNER`** contient l'etiquette d'un executeur
auto-heberge qui a POM2 ; sinon il est saute, et la publication n'exige que
la construction et les tests hors emulateur. C'est la limite honnete du
dispositif : la compilation, les budgets memoire et la fabrication des images
sont verifies partout, la session complete la ou l'Apple II existe. Le
travail appelle `bench/all.py --group ...` : les etapes portent les groupes
de la table, pas une copie des commandes.

## Les quinze nouvelles surcouches

`bench/plugins.py` exécute les bancs des surcouches à table de services --
les quinze d'origine plus `fixit.py` et `repair.py` --, avec un journal par
outil. Chaque banc construit son disque dur de travail et y ajoute
explicitement sa surcouche ; ceux qui écrivent vérifient ensuite la
disquette du lecteur 2 sur l'hôte. Ces volumes sont des fixtures, pas les
images publiées. Chacun **relit le dernier mot** de son outil : la ligne 22
est comparée mot pour mot à ce que `src/plugins/NOM.c` écrit aujourd'hui
(`api->message`, `api->note`, les questions de `confirm`/`prompt`), et non à
un fragment qui survivrait à n'importe quelle reformulation. Une grosse
surcouche parle après le redessin du résident : `xplug.wait_note` attend que
la ligne 22 porte quelque chose, `xplug.note_blank` qu'elle soit rendue vide
quand l'outil abandonne sans rien dire.

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
`A2FC_PRESET=iie_unenh`, puis avec `A2FC_IMG=A2FILECMD-full`.

`gotobad.py` vérifie le refus des configurations GOTO hors limites, aux chemins
mal formés ou avec NUL,
et leur conservation par CRC relu sur le disque.

`gotocfg.py` vérifie les fins de ligne CR/LF/CRLF mélangées, les lignes vides,
le dernier favori sans terminateur, les sauts et la relecture après sauvegarde.

`goto.py` vérifie les favoris et les chemins directs (P) : casse, correction,
annulation, chemin absent, limite de 63 caractères et choix du panneau actif.
Il vérifie aussi le déplacement des favoris (M), sa persistance et les annulations.

Les sauvegardes GOTO sont testées avec écriture incomplète, échecs de renommage,
restauration du fichier original et collisions avec les fichiers de récupération.

`open_images.py` ouvre Extasie, PACKFOT, 816/Paint et lo-res avec Entrée puis
I, reconnaît DGR et RLE sans indication de nom/type et ouvre un sprite
sans en-tête avec I. Il contrôle les pixels décodés, le refus de perte de
`/RAM`, le recours
explicite à H et le parcours de l’album brut. Exécuter avec
`A2FC_PRESET=iie_unenh`, puis `A2FC_IMG=A2FILECMD-full`.

`sample_media.py` lit `~/src/pom2/hdv/GISTDATA.hdv` en lecture seule (ou
`A2FC_SAMPLE_DISK`), puis copie DIP.CHIPS, BBROS.MINI, les deux programmes
Integer BASIC et les 52 polices dans un volume jetable. Il compare les pages
HGR complètes à des rendus de référence indépendants et contrôle la mémoire
AUX avant/après. Exécuter avec les deux couples `A2FC_BUILD`/`A2FC_PRESET`.
Les régressions synthétiques portables sont dans `tools/test_sample_media.py`.

Pour PT3, `python3 bench/build_pt3_trace.py` construit un hôte temporaire
`/tmp/a2fc-pt3-trace` à partir du pilote POM2 habituel, sans modifier le projet
POM2. Il trace les registres AY en lecture seule. Exécuter ensuite
`POM2=/tmp/a2fc-pt3-trace A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh python3 bench/pt3.py`,
puis avec `A2FC_BUILD=build A2FC_PRESET=iie`. Le banc vérifie le morceau complet,
les registres de la carte, la pause/reprise, le silence à la sortie, les
pointeurs malformés et la préservation d'AUX ; le passage enhanced vérifie
également le refus sans carte sur //c. Les deux emplacements historiques
`/SAMPLE.MEDIA` et `/IMG/SAMPLE.MEDIA` du corpus sont acceptés.

`pt3_large.py` génère ses propres modules avec `tools/pt3_fixture.py` : mêmes
notes dans 2 Ko et 65 535 octets, pointeurs traversant des pages, `$FFFF`
invalide et fichier de 65 536 octets refusé. Il vérifie à vitesse 1x la pause,
le feuilletage, la fin naturelle, Échap, le silence, la limite basse de pile C,
les octets AUX hors écran texte et le volume source entier, sur images jetables.

```sh
POM2=/tmp/a2fc-pt3-trace A2FC_BUILD=build A2FC_PRESET=iie python3 bench/pt3_large.py
POM2=/tmp/a2fc-pt3-trace A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh python3 bench/pt3_large.py
```

Qualification sur disque dur POM2 : 13/13 contrôles sur chaque CPU, durée du
morceau de 65 535 octets de 8,30 s (65C02) et 8,47 s (6502). Ces mesures ne
qualifient pas le débit d'une disquette physique.

`roi.py` checks preferences across restart and marked MOVE (same/cross volume,
collision, cancellation, manifest collision, preserved bytes, AUX and stack).
`music.py` checks foreground MB1 audio, pause, Escape, natural end and malformed
files on disposable images. Like `pt3.py` and `roi.py`, it needs the disposable AY trace host.
`python3 bench/build_pt3_trace.py` builds a matching POM2 core in `/tmp`,
without modifying the POM2 checkout, and enables and flushes HDV writeback only
for the disposable bench host. Run with `POM2=/tmp/a2fc-pt3-trace`.
`duet.py` checks the Electric Duet overlay on a disposable disk: the song
staged at `$2400`, the Mockingboard by default and the speaker player's
aligned loop on `1` (the CPU is sampled in that segment), the default 1/8
pulse and all three `D` settings (checking the running player's shift/NOP
instructions and continued playback), pause, Left/Right
between songs, Escape, both natural ends, a `.ED` BIN, A2DeskTop's
`JESU.JOY` from the sample disk when it is present, a truncated song, the
menu on a text file, AUX and the stack floor. No AY trace host is needed.
`batch_missing.py` verifies table and mark restoration after a malformed
BATCH entry point, including a source in the right panel.

`media.py` checks same-format Left/Right navigation, boundaries, marks, PT3
credits and seven specialized image viewers. `large_nav.py` checks more than
300 mixed entries, nested parent returns, both panels and music across windows.
Both use disposable volumes and `POM2=/tmp/a2fc-pt3-trace`.

`catalog_safety.py` rejects cyclic ProDOS/DOS catalogs and invalid DOS sectors,
then compares every byte of its disposable HDV and AUX. `catalog_overlay.py`
opens a DOS-order image as a panel, then asks for help and sorts from that
panel: both reread it from inside an overlay, so the CATALOG read is deferred
and settled by the main loop; the catalog must be back and the image intact.
The same is done from a ProDOS image opened as a folder and from one of its
subdirectories, and Escape must still land on the directory left. In `run.py`
the final `-A2FILE.SYSTEM` relaunch from BASIC.SYSTEM is an isolated scenario:
it prints an `OPEN (chantier 10)` line instead of aborting the session's verdict. `tree_safety.py`
reproduces the 20-level recursion case: copy and delete must refuse with the
stack canary and the whole disk intact; a three-level copy must still preserve
all source and destination bytes. Run both with each `A2FC_BUILD`/`A2FC_PRESET`
pair and the disposable writeback host described above. `tools/test_tree_stack.py`
executes the assembly guard over all 65,536 pointer values on both CPUs.

`python3 tools/fuzz_images.py --cases 1000 --out /tmp/a2fc-fuzz` covers DGR,
Extasie, PACKFOT, 816/Paint, MGTK fonts, Print Shop and LZ4FH under ASan/UBSan.
The input files are temporary and checked for modification; native rendering
is covered separately by the media benches.

`paint816.py` lit aussi TWOSTEVESTITLE depuis le corpus GISTDATA en lecture
seule, puis le copie sur son disque jetable. Il vérifie Échap normal et, sur
65C02, le bit Open-Apple/PB0 renvoyé par cc65 (8/8 contrôles ; 7/7 sur 6502).
Le cas avec modificateur était refusé par le coordinateur avant la correction ;
le signalement utilisateur sans modificateur n'a pas été reproduit.
`media.py` vérifie également que les flèches ne redemandent pas l'accord AUX
pour Extasie, 816/Paint HGR/DHGR, PACKFOT et DHGR brut, puis que réouvrir le
lecteur exige un nouvel accord et que le refus conserve AUX : 44/44 sur chaque CPU.


`pt3_dual.py` checks standard `02TS` pairs on both actual AY chips. It covers
an unaligned second module, distinct old/new tables, unequal endings, pause,
Escape, navigation, malformed footer, stack bounds and unchanged AUX/source.
The cache-resident fixture keeps 50 Hz at 1 MHz. The sparse stress fixture
reports its slower duration separately and verifies every decoded frame.
It also reports runtime disk misses through the decoder's 16-bit counter,
reset after initialization. On enhanced IIe at 1 MHz, instrument-priority
replacement reduces this fixture from 156 to 105 misses and 9.15 to 8.20 s;
the compact pair takes 5.78 s. Timings exclude the later panel reread.
Run with the temporary trace host built by `build_pt3_trace.py`.

`purple.py` checks all ten saved GR modes, exact MAIN/AUX planes, refusal
before AUX writes, Escape and pair-aware navigation with one consent per
session. It reads original DOS samples from `A2FC_PURPLE_CORPUS` (default
`~/src/pom2/disks_5.4/chatmauve`) when present, copying them to a disposable
ProDOS image. Missing originals leave the generated fixtures active. Default
RGB variant is EVE; `A2FC_RGB=feline` selects Feline. Original JIM1 and DDD
screenshots are written to `/tmp`. Run both CPU builds using the usual
`A2FC_BUILD`, `A2FC_PRESET` and `A2FC_PORT_OFFSET` settings.

`media.py` and `purple.py` temporarily trap the disposable guest at
`switch_to_text` and restore its three instruction bytes in `finally`.
This avoids racing HTTP sampling: `Loading <target>` must already name the
incoming file before text reveal. This
covers MB1/PT3, Extasie, PACKFOT/raw DHGR, 816/Paint HGR/DHGR, LZ4FH, fonts,
Print Shop, lo-res and Purplesoft. `tools/test_media_transition.py` executes
the resident `overlay_run` C and poisons the live overlay's entry table;
it checks the pending target before text reveal and selection before redraw,
both directory-window directions,
missing targets, failed rereads, Escape and unavailable arrows.
`tools/test_raw_transition.py` executes the separate HGR/DHGR loop with
poisoned entry tables, vanished targets and read failures, including an
Open-Apple-modified arrow. Neither loop may launch a different file after
a failed lookup.

`doswrite.py` valide C de ProDOS vers un vrai Disk II DOS 3.3 dans POM2,
sur copies jetables des images XL : trois allers-retours volumes/catalogue,
refus de confirmation, copies BAS/BIN/TXT, collision, protection physique,
conservation des autres fichiers, du volume source et d'AUX. Exécuter
`A2FC_PRESET=iie_unenh python3 bench/doswrite.py` puis
`A2FC_IMG=A2FILECMD-full python3 bench/doswrite.py` après `make disk`.


### ProDOS vers DOS 3.3 : disquettes et images

`python3 bench/build_dos_host.py` construit `/tmp/a2fc-dos-host` sans modifier
POM2. Cet hôte active la persistance HDV : utiliser uniquement les médias
jetables fabriqués par les bancs. `bench/dosimage.py` l'utilise pour contrôler
les octets des images DSK et 2MG après copie BAS/BIN/TXT et sauvegarde hôte.

```sh
python3 bench/build_dos_host.py
A2FC_IMG=A2FILECMD-full python3 bench/dosimage.py
A2FC_PRESET=iie_unenh python3 bench/dosimage.py
python3 bench/build_dos_host.py --slot 5
POM2=/tmp/a2fc-slot5 A2FC_DOS_SLOT=5 A2FC_IMG=A2FILECMD-full python3 bench/doswrite.py
POM2=/tmp/a2fc-slot5 A2FC_DOS_SLOT=5 A2FC_PRESET=iie_unenh python3 bench/doswrite.py
```

Le second hôte place le Disk II en slot 5 et le disque ProDOS en slot 6,
comme la configuration du cas TIGER BIN `$2000`, 8 192 octets. Les bancs
vérifient les fichiers existants, la source, AUX, les protections, les refus
de collision et la zone sous la pile C de 192 octets. Les tests sim65 exécutent
aussi le capteur assembleur pour les slots 1–7 et les deux lecteurs.

`overlay_load.py` utilise le même hôte jetable pour refuser un MENU trop
grand, reconstruire les panneaux, puis charger HELP normalement. Il compare
le volume entier, AUX et la garde de pile de 192 octets. Le banc C
`tools/test_overlay_load.py` injecte en plus les erreurs de lecture/fermeture
et vérifie qu'un échec du menu ne relance pas une ancienne commande.

```sh
A2FC_IMG=A2FILECMD-full python3 bench/overlay_load.py
A2FC_PRESET=iie_unenh A2FC_PORT_OFFSET=1 python3 bench/overlay_load.py
```

### DOS extraction, legacy DUET and type repair

`bench/formats.py` checks DOS BIN EOF/load address, Return on untyped `M.*`,
IDENT, confirmed/cancelled FIXTYPES, old sector padding, AUX and stack guards.
It reads the flushed disposable ProDOS floppy and compares every output byte.
Run with `A2FC_BUILD=build` and with `A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh`.
`bench/fixtypes.py` also checks marked files from the right panel, suffix
renames, collisions and cancellation from the left panel.
Host regressions: `tools/test_dos_extract.py`, `tools/test_format_repair.py`,
`tools/test_file_viewers.py`, `tools/test_overlay_load.py` (including overlapping
entry snapshots). All are included in `make test`.
