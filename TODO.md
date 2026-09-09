# A2 File Cmd — ce qui reste à faire

`🟠 haute · 🟡 moyenne · 🟢 basse`, effort indicatif en *italique*, fichier en
`backticks`. `💾` marque ce qui va **aussi** dans l'édition disquette ; le reste
va sur EXTRA et dans XL (voir « Les deux éditions »). Les mesures datent du 2026-09-09, sur les images candidates 0.7.5.
Ce qui est fait est dans le [CHANGELOG](CHANGELOG.md), avec le détail
technique de chaque version.

## Où en est-on

La 0.7 est **testée** sur un vrai Apple IIe enhanced, sur Virtual II, et
sous POM2 en //c (`preset='iic'`) comme en IIe non enhanced avec la version
6502 (`preset='iie_unenh'`). Seul le IIgs n'a jamais été essayé.

## La place disponible

Mesurée après la séparation BOOT / EXTRA / XL (`build/a2fc.map`, 65C02). Le résident est **plein** :
tout ce qui s'ajoute au noyau doit être payé par une surcouche ou par une
économie ailleurs.

| Zone | État mesuré |
| --- | --- |
| Fenêtre principale `$4000`-plancher de la pile (`$BE40`) | 86 octets libres après `INIT` (`$BDE9`) ; fin de `ONCE` à `$BEDF`, 1 octet avant le plafond du lanceur `$BEE0`. |
| RAM basse `$1000-$1AFF` (BSS) | 48 octets libres (6502 : 73) |
| Carte langage `$D400-$DFFF` | **16 octets libres** (`vsdrive.s` a pris le reste depuis la 0.6.7) |
| Pile C | 192 octets réservés (`A2FC_STACK`), creux maximal mesuré 86 (`bench/memory.py`) |
| Petites surcouches `$1B00-$1FFF` (1 280 octets) | `BINARY2` 1272, `IMGFS` 1270, `MUSIC` 668, `DOS33` 1216, `DELETE` 1218, `ATTR` 1246, `IMAGE` 1203, `RUN` 1064, `AWP` 1020, `HELP` 1061, `SEARCH` 847, `HEX` 901, `COMPARE` 1194, `TEXT` 1176 |
| Grandes surcouches | `FORMAT` 8020 / 8448, `DISKIMG` 6079 / 6400, `UNSHRINK` 5212 / 5376, `EDIT` 3308 / 3328, `BASLIST` 1419 / 3328, `MENU` 1901 / 5376 ; `VOLINFO` 6369 octets fichier, code et BSS jusqu’à `$3D6E` ; `BINARY2` est grande en 6502 (3 328). |
| BOOT / EXTRA / XL | BOOT : 24 blocs libres sur les deux processeurs. EXTRA : 57 / 58 blocs libres. XL : 64 401 / 64 402 blocs libres. |

Certaines petites surcouches restent proches du plafond (`BINARY2`,
`IMGFS`, `ATTR`) : leur agrandissement doit être vérifié au lien.

## Les deux éditions

Décidé le 2026-09-09 : deux processeurs, chacun avec BOOT, EXTRA et XL.
Les noms `A2FILECMD-6502-{BOOT,EXTRA,XL}-0.7.5` puis
`A2FILECMD-65C02-{BOOT,EXTRA,XL}-0.7.5` regroupent les images par processeur
au tri alphabétique. BOOT et EXTRA sont des disquettes 140 Ko (`.po` et
`.dsk`), XL est un disque complet de 32 Mo (`.2mg`). Le 6502 fonctionne
sans souris sur le IIe de 1983 ; le 65C02 ajoute MouseText et la souris.
EXTRA garde 57 blocs libres en 6502, 58 en 65C02, pour les nouveaux plugins : ne pas
mélanger les deux processeurs sur une même disquette.

- ✅ **`FORMAT` en surcouche** : `FORMAT.PLG` remplace le programme SYS sur
  BOOT et XL. Gain mesuré : 8 blocs en 6502, 6 en 65C02 (39 libres sur
  chaque BOOT), inférieur aux 18 blocs initialement estimés. Retour direct
  aux panneaux, protections et confirmation ERASE conservées. Le tampon
  de piste préserve le résident via AUX ; le vidage de `/RAM` est annoncé
  avant confirmation. Bancs Disk II, protection en écriture, RAM, SmartPort
  et intégrité mémoire sur les deux processeurs.
- ✅ **La seconde disquette** : chaque `A2FILECMD-<CPU>-EXTRA.po` contient les 23 outils
  absents du disque principal et `BASIC.SYSTEM`. Chargement depuis S6,D2,
  ou échanges sur S6,D1 : l'invite nomme le volume attendu et le lecteur,
  `1`/`2` change le lecteur, Retour réessaie, Échap annule. Le catalogue
  conserve tous les outils dans le menu ; le disque du fichier est
  redemandé après chargement de la surcouche s'il a été retiré. Le choix
  du slot (autre que 6) et la copie entre deux disquettes dans un seul
  lecteur restent hors de ce mécanisme de chargement.
- ✅ **Deux processeurs, trois supports chacun dans le Makefile et le CI** :
  `make disk` produit les six volumes ; `ARCH=6502` ou `ARCH=enh` sélectionne
  les trois volumes du processeur. BOOT et XL ont chacun leur page de titre.
  Les bancs EXTRA et XL vérifient les images publiées pour les deux CPU.
  La régression générale utilise encore `build/A2FILECMD-full.po` : porter
  entièrement `run.py` sur les XL publiées reste à faire. *½ jour.*

## L'objectif : Copy II Plus, Locksmith et ProSel en un seul outil

**L'objectif** : sur un vrai Apple IIe ou //c, A2FC seul doit suffire à
toute opération sur disquette, y compris sauvegarder ses propres disquettes
protégées d'un lecteur 5¼ à l'autre (fixé le 2026-09-09). Aucune fonction de
ces trois outils ne doit donc manquer, hors le traceur d'amorce et le langage
LPL de Locksmith, qui servent à analyser une protection, pas à copier un
disque. Inventaire relu le 2026-09-09 dans les manuels :
Copy II Plus 8 (archive.org, `A2_Copy_II_Plus_8_manual` ; le 9 n'ajoute que
le bit copy 3,5"), Locksmith 6.0 (archive.org, `locksmith-6.0-manual`) et
ProSel-8 (Asimov, `ProSel8CompleteDocs.pdf`). Ce qu'A2FC a déjà n'est pas
répété (catalogue, copie, tri en mémoire, attributs, verrou, formatage
ProDOS, copie de disquette, images, DOS 3.3 en lecture, ShrinkIt,
visionneuses, comparaison, recherche, lancement, création de dossier).
Écartés aussi : le chiffrement de fichiers de Locksmith, ses utilitaires de
carte RAM et son analyseur de bits de cadrage ; et, de ProSel, le cache
disque, les pilotes de cartes RAM, la file d'attente programmée (QUEUEP), la
partition DOS 3.3 sur disque dur (UNODOS) et les versions Videoterm.

## Palier 1 — livré dans la prochaine version, et compléments restants

Les quinze surcouches en cours sont intégrées : `TXTCONV`, `FIXTYPES`,
`GOTO`, `DATE`, `VERIFY`, `TAGPAT`, `FIND`, `CRC`, `VOLNAME`, `IDENT`,
`MDVIEW`, `RENAME`, `IMGCONV`, `BOOTBLK`, `WIPE`. Leurs commandes sont
précisées dans le [manuel](docs/MANUAL.md#more-tools-in-the--menu).
`TXTCONV`, `DATE`, `VERIFY`, `TAGPAT`, `VOLNAME` et `WIPE` sont aussi sur
la disquette. Le résident n'a pas grandi : ces outils utilisent la table
publique de services. `S` et `M` fonctionnent dans les deux éditions.

Ce lot couvre les usages de base ; les extensions suivantes restent à faire :

- 🟡 💾 **`DATE`** : modifier les dates de création et du volume ; installer
  le pilote de date de session. Aujourd'hui `S` pose la date système et `F`
  la date de modification des fichiers marqués, en conservant leur création.
- 🟡 💾 **`VERIFY`** : vérifier tous les fichiers marqués ; ajouter `CERTIFY`,
  écriture puis relecture d'un motif après `ERASE`. Aujourd'hui : lecture
  du volume entier ou du fichier sélectionné, avec compte des erreurs.
- 🟡 💾 **`TAGPAT`** : plages de dates (aujourd'hui : date système avec `D`)
  et copie avec confirmation fichier par fichier. Motifs, type et taille
  sont disponibles.
- 🟡 **`FIND`** : filtres par type/date, contexte de chaque occurrence et
  poursuite au-delà des 20 résultats ; aujourd'hui : nom ou contenu dans
  le volume, saut au résultat et signalement des limites de la file.
- 🟡 💾 **Déplacer sans copier** : vérifié le 2026-09-09, `V` copie puis
  efface, même dans un volume. Le `RENAME` de ProDOS 8 ne change qu'un nom
  dans son dossier, il ne déplace pas ; Cat Doctor déplace en réécrivant les
  blocs de répertoire (l'entrée copiée dans le dossier cible, effacée dans
  la source, le pointeur de parent d'un sous-dossier corrigé). C'est la
  même chirurgie que `DIRSORT` et `FIXIT` : à faire avec eux, en grande
  surcouche `MOVE`. *½ jour après `DIRSORT`.*
- 🟢 💾 **`DRIVESPD`** : la vitesse d'un lecteur Disk II, mesurée sur le temps
  d'un tour, affichée en tours par minute avec la cible de 300, ou en
  millisecondes (198 à 202) comme Copy II Plus, pour régler le
  potentiomètre. *½ jour.*

## Palier 2 — ce qui fait d'A2FC l'outil disque complet

Un à trois jours chacune : la réparation et la récupération, la copie brute,
le client ADTPro, et la robustesse. C'est le cœur de l'objectif. La
réparation d'abord (`UNDELETE`, `VOLINFO`, `FIXIT`, `BLKEDIT` partagent la
lecture de la table d'allocation), puis `ADTPRO` et `NIBCOPY`, qui
partagent la lecture brute de piste avec `NIBREAD` et `NIBBLE`.

- ✅ **`UNDELETE`**, EXTRA / XL : copie les candidats ProDOS seedling,
  sapling et tree vers un autre volume, sans modifier la source. Vérifie
  les blocs libres, les doublons, les comptes et les index inversés par
  DESTROY ; refuse les interprétations ambiguës et les effacements partiels
  incohérents. **Reste :** DOS 3.3 et fichiers étendus.
- 🟠 💾 **`VOLINFO`** : première version ProDOS en lecture seule livrée sur
  BOOT et XL, 6502 et 65C02 : espace libre, fragmentation, carte paginée,
  allocations partagées/perdues/marquées libres et compteurs. Parcours
  seedling/sapling/tree, deux forks et sous-dossiers ; résultats incomplets
  explicitement signalés. **Reste :** liste des blocs d'un fichier, carte
  piste/secteur DOS 3.3, rapports catalogue/arbre/blocs par fichier/fichiers
  par bloc vers écran, imprimante ou fichier texte (avec `TREE`).
- 🟠 💾 **`FIXIT`** : réparer ce que `VOLINFO` a trouvé : reconstruire la table
  d'allocation, corriger les compteurs, détacher un bloc partagé, après
  `ERASE`. La liste de Mr. Fixit, à reprendre telle quelle : pointeurs
  d'en-tête et de parent des sous-dossiers, chaînage arrière des blocs de
  répertoire, blocs utilisés marqués libres, caractères illégaux dans les
  noms, longueur d'entrée et entrées par bloc, compte de fichiers, effacements
  incomplets, types de stockage, comptes de blocs, dates illégales ; signalés
  sans correction : blocs à deux propriétaires, numéros hors volume. Plus
  ses deux modes à part : reconstruire le répertoire racine quand le bloc 2
  est détruit (en relisant tout le disque, à partir des blocs d'index), et
  les blocs défectueux (les recenser, puis les isoler dans un fichier
  `BAD.BLOCKS` en déplaçant ce qui se lit encore). Côté DOS 3.3 : vérifier
  et refaire la VTOC, corriger les comptes de secteurs du catalogue
  (Locksmith « fix sector counts »). *2 jours.*
- 🟠 💾 **`BLKEDIT`** : l'éditeur de blocs de Block Warden et Copy II Plus :
  aller au bloc N, suivre les blocs d'un fichier, hexa et ASCII, décodage
  d'un bloc de répertoire ou d'index, modifier, écrire après `ERASE`,
  extraire une suite de blocs vers un fichier (récupérer un fichier dont
  l'entrée est détruite). Chercher une suite d'octets sur tout le disque
  (Copy II Plus « scan for bytes », Block Warden `^S`), voir un bloc en
  désassemblé (avec `DISASM`) ou un fichier suivi en ASCII, montrer les
  paramètres de l'entrée de répertoire d'un fichier, copier un bloc d'un
  disque à un autre, l'imprimer, et lister tous les blocs qui ressemblent à
  un bloc d'index ou de répertoire pour reconstruire un répertoire perdu
  (Block Warden `^`). Grande surcouche. *2 jours.*
- 🟠 💾 **`ADTPRO`** : le client ADTPro dans A2FC, face au **vrai serveur
  ADTPro** du PC, sans le modifier, pour faire des images de disques de
  l'Apple II vers un PC ordinaire et les ramener, par la Super Serial Card ou
  le port 2 du //c à 115 200 bauds (fixé le 2026-09-09 ; l'Uthernet II
  suivra avec son transport, ADTPro y parle en UDP). L'objectif : un vrai
  Apple II et un PC avec ADTPro suffisent, sans ADTPro sur l'Apple. Ce qui
  existe : le transport 6551 et l'enveloppe VSDrive de `vsdrive.s`. Le
  protocole, relu dans `CommsThread.java` et `serproto.asm` d'ADTPro :
  - chaque commande est une lettre à bit 7 posé : `C` (`$C3`) changer de
    dossier sur le PC, `D` (`$C4`) lister le dossier par pages de 1 Ko,
    `Z` (`$DA`) taille d'un fichier, `Y` (`$D9`) ping, `X` (`$D8`) retour à
    l'accueil ;
  - `P` (`$D0`) envoyer un disque vers le PC et `G` (`$C7`) en recevoir un,
    bloc par bloc avec compression RLE, CRC-16 par paquet, acquittement `K`
    (`$CB`) ou demande de renvoi, dans une enveloppe `A` (`$C1`) + longueur
    sur deux octets + charge + octet de contrôle ; `B` (`$C2`) le lot,
    plusieurs disques à la suite ; le serveur nomme `.dsk` une image de
    140 Ko, `.po` les autres, et sait générer les noms ;
  - `N` (`$CE`) envoyer une disquette **en nibbles** (35 pistes de 6 656
    octets, le `.nib` du PC), `V` (`$D6`) en demi-pistes, `M` (`$CD`)
    plusieurs disquettes en nibbles : c'est l'archivage des disquettes
    protégées vers le PC, sur la lecture brute de piste de `NIBCOPY` ;
  - `E` (`$C5`) l'enveloppe VSDrive, déjà faite.

  Dans A2FC : une grande surcouche `ADTPRO.PLG` avec le dossier du PC comme
  un panneau (liste par `D`, `C` pour descendre), « envoyer ce volume ou
  cette disquette » (`P`, ou `N` pour le brut) et « recevoir cette image sur
  ce lecteur » (`G`), barre de progression et reprise sur NAK. Tampons en
  mémoire auxiliaire. Le banc : le vrai `ADTPro.jar` en mode serveur série
  sur le pont TCP de la SSC de POM2 (`pom2_playtest --ssc`), une image
  envoyée puis reçue, comparée octet à octet ; le nibble contre un `.woz`
  monté dans POM2. *2 jours pour `P`/`G`/`D`/`C`, 1 jour pour `N` après
  `NIBCOPY`.*
- 🟠 💾 **`NIBCOPY`** : copier une disquette piste à piste, brute, d'un lecteur
  Disk II à l'autre, ou sur un seul lecteur avec échanges. Le cœur :
  - **lire** une piste par les bascules du contrôleur (`$C08C,X` / `$C08E,X`),
    un tour complet et un peu plus, dans un tampon de `$1A00` (6 656 nibbles
    à 300 tours/min) ; la mémoire auxiliaire tient six pistes par passe,
    comme `DISKIMG` ;
  - **trouver le début** de la piste : la plus longue série de `$FF`, la zone
    de synchronisation ; sans elle (piste non standard), prendre la longueur
    d'un tour mesurée ;
  - **écrire** en un tour, à partir de ce début, en reconstituant les
    nibbles de synchronisation en 10 bits : le contrôleur ne rend que 8 bits
    à la lecture, c'est toute la difficulté, et le « sync » de Copy II Plus ;
    la longueur écrite doit tenir dans le tour de la cible (vitesse des deux
    lecteurs : `DRIVESPD` d'abord) ;
  - **relire et comparer** la piste écrite ;
  - **demi-pistes** par les phases du moteur pas-à-pas (`$C080-$C087,X`), et
    la copie partielle d'une plage de pistes ;
  - **des paramètres par titre**, comme Copy II Plus : pistes, demi-pistes,
    synchronisation, longueur, dans `A2FILE/NIBCOPY.PRM`, un fichier texte
    que l'on complète.

  À dire honnêtement dans le manuel : les bits faibles, les pistes en spirale
  et les protections par temps de rotation ne se recopient pas avec un Disk
  II, Copy II Plus et Locksmith non plus. Sur un //c, le lecteur interne et
  l'externe sont les deux lecteurs du slot 6, même code. Base : `Seek`,
  `Wait20` et `Trans` de `format_diskii.s`. Le banc : POM2 lit les `.woz` et
  les `.nib` avec un séquenceur cycle-exact (`DiskIICard.cpp`), donc copier
  une image `.woz` protégée du lecteur 1 vers une `.nib` en lecteur 2 et
  vérifier que la copie amorce, sur quelques protections classiques. Grande
  surcouche, `$1B00-$3FFF`, tampons en AUX. *3 jours.*
- 🟠 💾 **`NIBREAD` / `NIBWRITE`** : lire une disquette entière en image `.NIB`
  (35 × 6 656 = 232 960 octets) sur le disque dur ou sur VDrive, et écrire
  un `.NIB` sur une disquette. C'est l'archivage des disquettes protégées
  vers le PC et vers les émulateurs, sans autre matériel qu'un Apple II. En
  lecture d'image, accepter aussi le `.WOZ` (plus riche : quarts de piste,
  bits faibles) ; en écriture, produire du `.NIB` seulement, ce qu'un Disk
  II sait reproduire. Dans `DISKIMG`. *1 jour après `NIBCOPY`.*
- 🟡 💾 **`NIBBLE`** : lire une piste brute et la montrer nibble par nibble,
  avec les marques d'adresse repérées, pour diagnostiquer une disquette qui
  ne se lit plus ; la vue « scan » de Locksmith, une ligne par piste avec la
  longueur des zones de synchronisation et les secteurs trouvés ; puis,
  avec `NIBCOPY`, l'édition : marquer un nibble comme synchronisation,
  insérer, supprimer, réécrire la piste (le disk editor de Locksmith).
  *1 jour, sur la lecture et l'écriture de piste de `NIBCOPY`.*
- 🟡 💾 **`DIRSORT`** : trier physiquement un dossier sur le disque, par nom,
  type, date de création ou de modification, type puis nom, ou à l'envers,
  et déplacer une entrée à la main avant d'écrire (Cat Doctor « sort
  directory »), en réécrivant ses blocs. Un dossier de plus de 139 entrées,
  qu'A2FC ne trie pas en mémoire, se retrouve trié pour de bon. Et le geste
  caché de Cat Doctor : retirer une entrée abîmée du répertoire sans toucher
  aux blocs, `FIXIT` faisant le reste. *1 jour.*
- ✅ **`RESCUE`**, EXTRA / XL : copie fichier ou volume ProDOS vers un
  autre volume, trente tentatives de lecture par bloc, zéros et journal
  pour les blocs illisibles. **Reste :** récupération brute DOS 3.3.
- ✅ **`DISKCMP`**, EXTRA / XL : comparaison exacte de volumes ou d'images
  PO, DSK, HDV et 2MG. Mode Disk II à un lecteur avec noms des disques et
  choix D1/D2 à chaque échange. **Reste :** vérification intégrée à DISKIMG.
- 🟡 💾 **`DISKIMG`, ce qui lui manque face à Copy II Plus** : formater la cible
  pendant la copie ; continuer après une erreur de lecture en listant les
  pistes ou blocs fautifs au lieu de s'arrêter ; plusieurs copies de suite
  quand l'image tient en mémoire ; ne copier que les blocs utilisés d'un
  volume, et accepter une cible plus grande en agrandissant le volume
  (ProSel `COPY`) ; et vérifier qu'un lecteur 3,5" SmartPort de 800 Ko passe
  en copie et en image. *1 jour.*
- 🟡 💾 **Les décodeurs face à des données corrompues.** `UNSHRINK`, `BINARY2`,
  `AWP`, `DOS33` et `IMGFS` lisent des fichiers qu'on ne contrôle pas, sans
  protection mémoire. Une archive ou une image tronquée ou malformée peut
  figer la machine. Compiler ces décodeurs sur l'hôte (ils sont déjà isolés
  en surcouches ; le cœur LZW est en assembleur, à couvrir par
  `tools/mkshk.py` en oracle inversé) et les passer au fuzz. *1 à 2 jours.*
- 🟡 💾 **Le //c au banc complet.** Les panneaux arrivent sous `preset='iic'` ;
  reste à faire tourner `bench/run.py` et `bench/memory.py` dessus et à
  regarder ce qui casse. Sans Mockingboard, la fanfare doit se taire
  proprement ; `/RAM` est le même. Rappel POM2 : le lecteur intégré du //c
  EST le Disk II du slot 6, le disque dur du banc est l'unité SmartPort du
  port arrière (slot 5, `DEVLST` `$5B`), et le //c doit garder son Disk II
  branché sinon le firmware attend à `$CC2C`. *½ jour.*
- 🟡 💾 **VDrive sur une vraie Super Serial Card et sur un //c.** Le pilote
  (`src/vsdrive.s`) passe 6/6 au banc (`bench/vdrive.py`, `pom2_playtest
  --ssc`), avec son gestionnaire d'interruption pour la chute de DCD.
  Reste un retour d'utilisateur sur une SSC réelle, derrière un câble USB
  série (sans lignes modem) et derrière un modem (avec). *Selon retour.*

## Palier 3 — utile, pour un public plus restreint

Un à deux jours chacune, ou une étude. Le sélecteur de programmes et la
sauvegarde de ProSel, les autres systèmes de fichiers, le IIgs, l'Uthernet
II, et les formats qui ouvrent la production du IIgs et des hackers.

- 🟡 **`LAUNCHER`** : une liste de programmes favoris, chacun avec un titre,
  un préfixe, un chemin et un paramètre de démarrage (le programme BASIC à
  lancer par `BASIC.SYSTEM`, comme ProSel), des lignes de titre pour grouper,
  le saut au premier titre par sa lettre, et le remplissage automatique par
  balayage d'un dossier à la recherche des SYS et des BAS. Dans
  `A2FILE.CFG` ; le retour par `-A2FILE.SYSTEM` existe déjà. Le cœur de
  ProSel. *1 jour.*
- 🟡 **Revenir à A2FC quand un programme quitte** : ProSel se réinstalle comme
  code de sortie de ProDOS ; voir ce que ProDOS 8 2.4 permet (Bitsy Bye est
  son code de sortie) pour qu'un `QUIT` ramène sur les panneaux sans taper
  `-A2FILE.SYSTEM`. *½ jour d'étude.*
- 🟡 **`BACKUP`** : sauvegarde d'un volume vers des disquettes numérotées
  `BACKUP.001`... ou vers un fichier image, restauration, et récupération
  d'un seul fichier depuis le jeu de sauvegarde (ProSel `BACKUP`, `RESTORE`,
  `RECOVER` : par blocs utilisés, avec relecture après écriture et formatage
  automatique des disquettes). En variante par fichiers, l'incrémental de
  Cat Doctor (`^C`, `^E` : ne copier que les plus récents), qui est `SYNC`.
  Avec VDrive, vers le PC. *2 jours.*
- ✅ **`SYNC`**, EXTRA / XL : copie récursive des fichiers absents ou plus
  récents entre les panneaux, relecture avant remplacement, sauvegarde et
  restauration si installation impossible. Fichiers destination seuls conservés.
- 🟡 💾 **`DOS33W`** : copier un fichier ProDOS vers une disquette DOS 3.3, avec
  l'en-tête Applesoft ou binaire ajouté et le nom converti ; changer le
  programme d'amorce (`HELLO`) ; retirer le DOS d'une disquette pour gagner
  ses deux pistes (« delete DOS »). Le sens inverse de `DOS33.PLG`. *1 jour.*
- 🟡 💾 **`DOS33FMT`** : initialiser une disquette 16 secteurs. Sans DOS écrit
  dessus (le DOS 3.3 n'est pas librement redistribuable, ProDOS 8 2.4 l'est
  par John Brooks) : une disquette de données, VTOC et catalogue vides, que
  `DOS33W` remplit. Pour la rendre amorçable, « copy DOS » : recopier les
  pistes 0 à 2 d'une disquette DOS 3.3 que l'utilisateur possède, comme Copy
  II Plus. *½ jour, sur `format_diskii.s`.*
- 🟡 **`PASCALFS`** : les disquettes Apple Pascal, en image ou en vrai
  lecteur, ouvertes comme dossier, extraction des `.TEXT` (pages de 1 Ko,
  indentation par DLE) en texte ProDOS. *1 jour.*
- 🟡 **`SHR`** : le Super Hi-Res du IIgs (`$C1`, 320 × 200, seize palettes)
  rendu en DHGR 140 × 192 : lire les tables de contrôle de lignes et les
  palettes en fin de fichier, puis les lignes une à une (160 octets), réduire
  320 vers 140 et prendre la couleur DHGR la plus proche. Les variantes
  suivent : `$C0/$0001` Paintworks et `$C0/$0002` APF en PackBytes,
  `$C1/$0002` 3 200 couleurs à palette par ligne. Grande surcouche, tables en
  mémoire auxiliaire. *2 jours.*
- 🟡 **`DISASM`** : désassembleur 6502 et 65C02 d'un BIN ou d'un SYS, depuis
  son adresse de chargement, page par page comme `BASLIST`. *1 jour.*
- 🟡 **`TOKENIZE`** : texte → Applesoft tokenisé, table des mots-clés
  partagée avec `BASLIST` ; avec l'éditeur, on écrit un programme BASIC sans
  quitter A2FC. *1 jour.*
- ✅ **`MKIMAGE`**, EXTRA / XL : images de données ProDOS `.PO` et `.2MG`
  vides, de 140 Ko à 32 767 blocs (limite de taille d’un fichier ProDOS).
- 🟢 **Écrire dans une image disque** ouverte comme dossier (copier VERS un
  `.PO`/`.2MG`) : la lecture existe (`IMGFS.PLG`), l'écriture demande la
  carte des blocs libres et l'allocation, c'est-à-dire un mini-ProDOS. Une
  grande surcouche. *2 jours.*
- 🟢 **`PRINT`** : catalogue ou texte vers l'imprimante du slot 1, avec
  numéro de page (Copy II Plus, ProSel). *½ jour.*
- ✅ **`TREE`**, EXTRA / XL : arborescence paginée et tailles cumulées des dossiers.
- 🟢 **`SETUP`** : éditer `A2FILE.CFG` depuis le programme. *½ jour.*
- 🟢 **`SYSINFO`** : les cartes par slot d'après les ROM, la mémoire,
  l'identifiant machine, l'horloge ; et un test de la mémoire auxiliaire
  (Locksmith « RAM card test »). *½ jour.*
- 🟡 **Le IIgs.** Jamais essayé ; POM2 n'a pas de profil IIgs, donc un autre
  émulateur (ou une vraie machine). À vérifier en premier : le contrôle de
  machine du lanceur, MouseText, la souris ADB, `/RAM5`. *½ jour, selon
  émulateur.*
- 🟡 **VDrive par l'Uthernet II** : le même protocole sur une prise TCP du
  W5100 *(demandé le 2026-09-08 ; POM2 est prêt : `pom2_playtest --uthernet`
  branche une Uthernet II en slot 3 du //e avec le loopback ouvert,
  `Pom2(..., uthernet=True)` dans `bench/pom2.py` passe le drapeau)*.
  À écrire, `src/vsdrive_w5100.s`, la moitié transport du pilote —
  l'enveloppe, les XOR, l'installation dans `DEVADR`/`DEVLST` et le talon
  sont à partager avec `vsdrive.s` :
  1. trouver la carte, qui n'a pas de ROM : sur chaque slot 1..7, écrire le
     registre de mode par la fenêtre `$C0n4` (mode) / `$C0n5-6` (adresse) /
     `$C0n7` (donnée), poser l'auto-incrément (`MR = $02`) et relire `MR` —
     c'est ce que font IP65 et AppleWin ;
  2. un reset logiciel (`MR = $80`), `RMSR`/`TMSR = $55` (2 Ko par prise),
     une adresse source quelconque dans `SIPR` (les prises sont celles de
     l'hôte sous POM2 ; sur une vraie carte l'adresse vient de la
     configuration) ;
  3. la prise 0 en TCP : `S0_MR = $01`, `S0_PORT` quelconque, `S0_DIPR` =
     l'adresse du serveur, `S0_DPORT` = son port, `S0_CR = OPEN ($01)` puis
     `CONNECT ($04)`, attendre `S0_SR = $17` (ESTABLISHED) avec un délai ;
  4. `putc` = écrire au pointeur `S0_TX_WR` dans le tampon `$4000+` (2 Ko,
     modulo), avancer le pointeur, `S0_CR = SEND ($20)` — grouper
     l'enveloppe et le bloc en un seul SEND ; `getc` = attendre
     `S0_RX_RSR ≠ 0`, lire à `S0_RX_RD` dans `$6000+`, avancer, `S0_CR =
     RECV ($40)` ; l'hôte parti se voit à `S0_SR = $00` (CLOSED) ou à un
     délai, et donne `E_IO` comme le 6551 ;
  5. l'adresse et le port du serveur : une ligne `vdrive=127.0.0.1:6740`
     dans `A2FILE/A2FILE.CFG`, lue par `load_config` ;
  6. `bench/vsdrive_server.py --listen` : ici c'est l'Apple qui se connecte,
     le serveur doit écouter au lieu d'aller au pont de la SSC ;
     `bench/vdrive_net.py` = `vdrive.py` avec `uthernet=True` et ce serveur,
     mêmes six contrôles.

  Sur une vraie Uthernet II le même code parle à `surl-server` ou à un
  `vsdrive_server` sur un Raspberry. **La place** : la carte langage n'a
  plus que 16 octets ; le transport W5100 devra soit remplacer le 6551 au
  chargement (un seul pilote résident, choisi par `A2FILE.CFG`), soit vivre
  en mémoire auxiliaire. *1 jour, plus la question de la place.*
- 🟡 **`TFTP`** : recevoir ou envoyer un fichier par TFTP, dès que l'Uthernet
  II a son transport. *½ jour après le transport.*
- 🟡 **`NTP`** : demander l'heure et la poser dans `$BF90` ; sur la liaison
  série, le même service par une commande de plus dans `vsdrive_server.py`.
  *¼ jour.*
- 🟢 **Une table de reconnaissance** (type, auxtype, suffixe, en-tête → nom
  de surcouche) à la place de `looks_like_image` et de l'aiguillage
  d'`open_selected`, pour qu'un format de plus ne coûte qu'une ligne.
  *½ jour.*

## Palier 4 — niche, plaisir, ou dette sans urgence

À prendre quand l'envie ou une demande vient. Rien ici ne bloque personne.

- 🟡 **`MACPAINT`** : 576 × 720 monochrome en PackBits, sur le DHGR
  monochrome 560 × 192 avec défilement vertical. *1 jour.*
- 🟢 **`BMP`** puis **`GIF`** : un BMP 8 bits se réduit comme le SHR ; le GIF
  réutilise le LZW d'`UNSHRINK` à code variable. *1 jour, puis 2.*
- 🟢 **`GR`** : les images lo-res et double lo-res (`$08`). *¼ jour.*
- 🟢 **`PRINTSHOP`** : les graphismes Print Shop, 88 × 52 monochromes.
  *½ jour.*
- 🟢 **`SHAPES`** : visionneuse de tables de formes Applesoft. *½ jour.*
- 🟢 **`SLIDESHOW`** : `IMAGE` avec un délai et la musique en fond, pour un
  dossier entier. *¼ jour.*
- 🟢 **`INTLIST`** : lister l'Integer BASIC. *½ jour.*
- 🟢 **`ADB`** et **`ASP`** : la base de données et le tableur AppleWorks,
  sur le modèle d'`AWP.PLG`, avec `tools/mkadb.py` pour le banc. *1 jour
  chacun.*
- 🟢 **`AWRITER`** : les fichiers Apple Writer, texte à bit 7 et quelques
  codes. *¼ jour.*
- 🟢 **`CALC`** : hexa, décimal, binaire, arithmétique 32 bits. *¼ jour.*
- 🟢 **`DUET`** : les musiques Electric Duet, deux voix par le haut-parleur.
  *½ jour.*
- 🟢 **`SAMPLE`** : un échantillon 8 bits mono par le haut-parleur, converti
  côté hôte. *¼ jour.*
- 🟢 **`TERM`** : un terminal 80 colonnes sur la Super Serial Card. *1 jour.*
- 🟢 **`XMODEM`** : un seul fichier par la SSC avec n'importe quel terminal.
  *1 jour.*
- 🟢 **`CPMFS`** : les disquettes CP/M de la Softcard, répertoire et
  extraction par extents. *1 jour.*
- 🟢 **`SPLIT`** : couper un gros fichier en morceaux de 140 Ko et les
  recoller. *½ jour.*
- 🟢 **`PASSWORD`** : un mot de passe au démarrage, trois essais puis blocage,
  et son changement depuis A2FC ; une protection de salon, pas de sécurité,
  à dire clairement (ProSel `PASSWORD`). *¼ jour.*
- 🟢 **`LCASE`** : les minuscules de ProDOS 2.4 dans les noms. *¼ jour.*
- 🟢 **`PLGINFO`** : l'en-tête d'un `.PLG`, sa taille contre son plafond, sa
  version d'API ; et un `apitest.c` dans le SDK, banc de l'ABI. *½ jour.*
- 🟢 **Créer un ShrinkIt** (SHRINK) : l'inverse d'`UNSHRINK`, le LZW en
  compression. *2 jours, place en mémoire auxiliaire.*
- 🟢 **Éclater `src/a2fc.c`** (4 466 lignes, 92 bascules de segment) en un
  fichier par surcouche. Les segments existent déjà, `-Cl` et les
  `#pragma static-locals` restent ; c'est de la mécanique, à faire un jour
  sans autre changement, binaire identique avant/après. *1 jour.*
- 🟢 **L'anglais partout.** Le code (`src/`, `Makefile`, `sdk/`) et
  `sdk/README.md` sont passés en anglais le 2026-09-09. Restent en français
  les outils `tools/*.py` et les bancs `bench/*.py`, ainsi que ce TODO, qui
  reste en français par choix. *½ jour pour les scripts.*

## À laisser

Décidé, pour ne pas y revenir.

- 🟢 **Défragmenter** (Beach Comber) : à laisser tant que `FIXIT` et `VERIFY`
  ne sont pas éprouvés ; c'est l'outil qui détruit un disque quand il se
  trompe. *2 jours, plus tard.*
- 🟢 **La musique entièrement en surcouche** : le chargement d'un `.MB` est
  déjà `MUSIC.PLG`, mais le pilote AY reste résident. Le rendre surcouche
  demanderait qu'elle survive à la navigation, ce que la fenêtre unique
  interdit. *À laisser.*
- 🟢 **Les grands répertoires** : au-delà de 139 entrées, lecture par
  fenêtres dans l'ordre du disque, sans tri. Trier une fenêtre est possible ;
  trier tout le répertoire demanderait la page graphique. *À laisser tant
  que personne ne le demande.*

## Repères

Les surcouches : `A2FILE/NOM.PLG`, lues en `$1B00` à la demande, en-tête
`struct Overlay` et table de services `struct A2fcApi` dans
`src/a2fc_plugin.h` ; la convention d'un tiers dans `sdk/README.md`. Dix-neuf
surcouches dans la 0.7, plafonds dans `src/a2fc.cfg`, vérifiés par
`tools/check_layout.py` à chaque lien.
