# A2 File Cmd — ce qui reste à faire

`🟠 haute · 🟡 moyenne · 🟢 basse`, effort indicatif en *italique*, fichier en
`backticks`. `💾` marque ce qui va **aussi** dans l'édition disquette ; le reste
n'est que dans l'édition complète (voir « Les deux éditions »). Les mesures datent du 2026-09-09, sur la 0.7 (version stable).
Ce qui est fait est dans le [CHANGELOG](CHANGELOG.md), avec le détail
technique de chaque version.

## Où en est-on

La 0.7 est **testée** sur un vrai Apple IIe enhanced, sur Virtual II, et
sous POM2 en //c (`preset='iic'`) comme en IIe non enhanced avec la version
6502 (`preset='iie_unenh'`). Seul le IIgs n'a jamais été essayé.

## La place disponible

Mesurée sur `build/a2fc.map` de la 0.7 (65C02). Le résident est **plein** :
tout ce qui s'ajoute au noyau doit être payé par une surcouche ou par une
économie ailleurs.

| Zone | État mesuré |
| --- | --- |
| Fenêtre principale `$4000`-plancher de la pile (`$BE40`) | **~240 octets libres** après `INIT` (`$BD51`) ; `ONCE` finit à `$BE47` et le lanceur charge jusqu'à `$BEE0` : ~150 octets de marge avant de heurter le lanceur (`check_layout.py` veille). Version 6502 : ~900 octets. |
| RAM basse `$1000-$1AFF` (BSS) | ~50 octets libres (6502 : ~75) |
| Carte langage `$D400-$DFFF` | **16 octets libres** (`vsdrive.s` a pris le reste depuis la 0.6.7) |
| Pile C | 192 octets réservés (`A2FC_STACK`), creux maximal mesuré 94 (`bench/memory.py`) |
| Petites surcouches `$1B00-$1FFF` (1 280 octets) | `BINARY2` 1 270, `IMGFS` 1 247, `MUSIC` 1 246, `MENU` 1 212, `DOS33` 1 211, `DELETE` 1 194, `ATTR` 1 193, `IMAGE` 1 187, `RUN` 1 152, `AWP` 980, `HELP` 974, `SEARCH` 838, `HEX` 826, `COMPARE` 768, `TEXT` 644 |
| Grandes surcouches (plafond dans `src/a2fc.cfg`) | `DISKIMG` 6 068 / 6 400, `UNSHRINK` 5 208 / 5 376, `EDIT` 3 227 / 3 328, `BASLIST` 1 369 / 3 328 ; `BINARY2` passe grande en 6502 (3 328) |
| Disquette `A2FILECMD.po` | **12 blocs libres** sur 280 (6502 : 11). Le `.2mg` `/A2FILEHD` porte `DEMO` et `IMGHGR`, 64 584 blocs libres |

Trois petites surcouches sont à moins de 40 octets du plafond (`BINARY2`,
`IMGFS`, `MUSIC`) : la prochaine ligne qu'on y ajoute les fait passer
grandes, ou demande de sortir leurs chaînes dans une table.

## Les deux éditions

Décidé le 2026-09-09 : deux produits, pas quatre paires d'images.

| | **Édition disquette** | **Édition complète** |
| --- | --- | --- |
| Image | `A2FILECMD.po` et `.dsk`, 140 Ko | `A2FILECMD.2mg`, 32 Mo, `/A2FILEHD` |
| Processeur | **6502** (`make disk ARCH=6502`) : tourne sur tout Apple II 128 Ko à 80 colonnes, IIe de 1983 compris ; sans souris | **65C02** : IIe enhanced, //c, IIgs ; souris, MouseText |
| Contenu | le gestionnaire et les **outils disque** : ce qu'un utilisateur à deux Disk II et sans disque dur ne peut faire autrement | **tout** : les dix-neuf surcouches, `DEMO/`, `IMGHGR/`, `BASIC.SYSTEM` |
| Public | la machine d'origine, la disquette qu'on prête | l'émulateur, la CFFA, le disque dur |

**Le budget de la disquette**, en blocs de 512 octets (280 sur le disque,
dont 7 de structure ; un fichier de plus de 512 octets coûte un bloc d'index
en plus de ses données) :

| | Blocs |
| --- | --- |
| Socle : `PRODOS`, `A2FILE.SYSTEM`, `A2FILE.CODE`, `A2FILE.HELP`, `MENU`, `HELP`, `DELETE`, `ATTR`, `RUN`, `TEXT`, `HEX`, `DISKIMG`, `FORMAT.SYS`, `DOS33`, `IMGFS` | 168 |
| Sortent de la disquette : `EDIT`, `MUSIC`, `IMAGE`, `AWP`, `BASLIST`, `COMPARE`, `SEARCH`, `UNSHRINK`, `BINARY2` (45) et `BASIC.SYSTEM` (21) | −66 |
| **Libre pour les outils disque à venir** | **78** |
| À venir, marqué `💾` : `NIBCOPY` 17, `ADTPRO` 13, `FIXIT` 7, `UNDELETE` 4, `VOLINFO` 4, `NIBBLE` 4, `DIRSORT` 4, `RESCUE` 4, `DOS33W` 4, `VERIFY` 3, `DATE` 3, `TXTCONV` 3, `TAGPAT` 3, `DRIVESPD` 3, `WIPE` 2 (estimations d'après les surcouches actuelles) | 78 |
| `BLKEDIT` (grande surcouche, ~13), s'il doit y tenir aussi | +13 |

C'est juste : zéro bloc de marge avant `BLKEDIT`. Deux façons de respirer,
à faire dans cet ordre :

- 🟠 **`FORMAT` en surcouche** : `FORMAT.SYS` est un programme SYS à part avec
  son propre crt0 et sa bibliothèque, 24 blocs. En grande surcouche
  (`$1B00-$3FFF`, ses tampons `$6700-$8000` passent en mémoire auxiliaire ou
  dans la page graphique), il en coûterait 6 : **18 blocs rendus**, et le
  formateur ne quitte plus le programme. *1 jour.*
- 🟡 **La seconde disquette** : `A2FILECMD-EXTRAS.po` avec les neuf surcouches
  sorties, et `load_overlay` qui, après `A2FILE/` sur le disque de démarrage,
  cherche aussi `A2FILE/` sur le lecteur 2. L'utilisateur à deux lecteurs a
  tout ; celui à un lecteur échange. *½ jour.*
- 🟠 **Les deux éditions dans le Makefile et le CI** : `make disk` produit la
  disquette 6502 minimale (liste `PLUGINS_FLOPPY`, sans `BASIC.SYSTEM`) et le
  `.2mg` 65C02 complet ; plus de `.2mg` 6502 ni de disquette 65C02 (le banc
  `run.py` tourne sur le `.2mg`, `smoke.py` et les bancs disque sur la
  disquette avec `A2FC_BUILD=build-6502`) ; le README et la page de titre
  disent l'édition. *½ jour.*

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

## Palier 1 — le meilleur rendement : quelques heures chacune, effet immédiat

Des petites surcouches ou des vérifications, sans risque, qui changent
l'usage quotidien ou lèvent un doute. À faire dans cet ordre, en commençant
par ce qui débloque les transferts depuis le PC.

- 🟠 💾 **`TXTCONV`** : convertir un texte sur place ou vers l'autre panneau :
  CR ↔ LF ↔ CRLF, bit 7 posé ou ôté, tabulations, accents UTF-8
  translittérés en ASCII. Un fichier venu d'un Mac ou de Linux par VDrive ou
  par image est illisible sans cela, un source Merlin aussi. *½ jour.*
- 🟠 **`FIXTYPES`** : poser le type ProDOS d'après le suffixe sur les
  fichiers marqués (`.SHK` → `$E0/$8002`, `.BNY` → `$E0/$8000`, `.PO` →
  `$E0/$0005`, `.AWP` → `$1A`, `.BAS` → `$FC`, `.SYS` → `$FF`), et retirer le
  suffixe si on veut. *½ jour.*
- 🟡 **`GOTO`** : des chemins favoris dans `A2FILE.CFG`, atteints en deux
  touches. *½ jour.*
- 🟡 💾 **`DATE`** : entrer la date dans `$BF90-$BF93` sans horloge, poser une
  date de création ou de modification sur les fichiers marqués
  (`SET_FILE_INFO`) et sur le volume (Cat Doctor « change file date »). Et
  garder la date pour la session : un pilote d'horloge minimal installé dans
  `$BF06` qui rend la date entrée, pour que ProDOS date les fichiers créés
  ensuite, ce qu'un `$BF90` seul ne fait qu'une fois. *½ jour.*
- 🟡 💾 **`VERIFY`** : lire tous les blocs d'un volume ou d'un fichier marqué et
  signaler ceux qui rendent une erreur (Copy II Plus « verify disk »,
  « verify files »). Et `CERTIFY`, destructif après `ERASE` : écrire un motif
  sur chaque piste et le relire, pour qualifier une disquette neuve ou
  douteuse (Locksmith). *½ jour.*
- 🟡 💾 **`TAGPAT`** : marquer par motif avec `=` et `?` (les jokers de Copy II
  Plus), par type, par date, par taille ; la copie « avec confirmation
  fichier par fichier ». *½ jour.*
- 🟡 **`FIND`** : chercher un fichier par nom ou motif dans tout le volume,
  récursivement, et sauter dessus ; et chercher un texte dans tous les
  fichiers d'un volume ou d'un dossier, filtrés par type et par date, avec
  le contexte de chaque occurrence (ProSel `FIND.FILE`). `SEARCH` ne cherche
  que dans un fichier. *1 jour.*
- 🟡 **`CRC`** : CRC-32 du fichier sélectionné, pour vérifier un transfert
  contre le PC (`tools/` en oracle). *½ jour.*
- 🟡 💾 **Renommer un volume** : à vérifier ; s'il manque, une ligne dans
  `ATTR` ou dans `VOLINFO` (`RENAME` sur `/VOL`, comme Copy II Plus et Cat
  Doctor). *¼ jour.*
- 🟡 💾 **Déplacer sans copier** : à vérifier que `V` dans un même volume
  déplace l'entrée de répertoire au lieu de copier puis effacer (Cat Doctor
  « move files » : instantané, même pour un dossier entier). *½ jour si
  ce n'est pas le cas.*
- 🟡 **Comparer deux dossiers** : à vérifier que le marquage des différences
  entre panneaux couvre les types et les dates de modification, pas
  seulement les noms (Cat Doctor « compare directories »). *¼ jour.*
- 🟡 **`IDENT`** : dire ce qu'est un fichier d'après son contenu, comme
  `file(1)` : archive, image, Applesoft, AppleWorks, texte à bit 7, fins de
  ligne, nombre de lignes. Partage la table de reconnaissance du TODO.
  *½ jour.*
- 🟡 **`MDVIEW`** : lire un Markdown ou tout texte à lignes longues : repli à
  80 colonnes, titres en inverse, listes, code tel quel. *½ jour.*
- 🟢 **`RENAME`** par motif sur les fichiers marqués : préfixe, suffixe,
  extension, majuscules. *½ jour.*
- 🟢 **`IMGCONV`** : `.DSK` ↔ `.PO` ↔ `.2MG` sur l'Apple, même table que
  `po2dsk.py`. *½ jour.*
- 🟢 **`BOOTBLK`** : réécrire les blocs d'amorce ProDOS (données dans
  `data/`). *¼ jour.*
- 🟢 💾 **`DRIVESPD`** : la vitesse d'un lecteur Disk II, mesurée sur le temps
  d'un tour, affichée en tours par minute avec la cible de 300, ou en
  millisecondes (198 à 202) comme Copy II Plus, pour régler le
  potentiomètre. *½ jour.*
- 🟢 💾 **`WIPE`** : effacer les blocs libres d'un volume, ou un disque entier
  (Locksmith « erase disk », Copy II Plus « delete disk »), après `ERASE`.
  *¼ jour.*

## Palier 2 — ce qui fait d'A2FC l'outil disque complet

Un à trois jours chacune : la réparation et la récupération, la copie brute,
le client ADTPro, et la robustesse. C'est le cœur de l'objectif. La
réparation d'abord (`UNDELETE`, `VOLINFO`, `FIXIT`, `BLKEDIT` partagent la
lecture de la table d'allocation), puis `ADTPRO` et `NIBCOPY`, qui
partagent la lecture brute de piste avec `NIBREAD` et `NIBBLE`.

- 🟠 💾 **`UNDELETE`** : ProDOS efface un fichier en mettant son type de
  stockage à zéro, l'entrée reste lisible. Lister les entrées effacées du
  dossier, vérifier que leurs blocs sont encore libres, restaurer. Aussi sur
  une disquette DOS 3.3 (l'entrée du catalogue marquée `$FF`). Comme Copy
  II Plus : marquer `?` un fichier dont des blocs ont été réalloués depuis
  (« lost file »), et montrer les caractères de contrôle cachés dans un nom
  DOS 3.3. Petite surcouche. *1 jour.*
- 🟠 💾 **`VOLINFO`** : carte des blocs du volume en 80 colonnes (libres,
  occupés, fragmentation), la liste des blocs d'un fichier, et le contrôle
  de la table d'allocation contre les listes de blocs de tous les fichiers :
  blocs perdus, blocs partagés, compteurs d'entrées faux. Aussi la carte
  piste/secteur d'une disquette DOS 3.3 avec les secteurs d'un fichier
  (flèches, comme Copy II Plus). Les cinq sorties d'Info Desk, à l'écran,
  sur l'imprimante ou dans un fichier texte : catalogue en arbre, blocs par
  fichier, fichiers par bloc, carte, arbre des dossiers (avec `TREE`). La
  moitié de Mr. Fixit. *1 jour.*
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
- 🟡 💾 **`RESCUE`** : relire un bloc ou un secteur illisible jusqu'à trente
  fois, garder ce qui passe, remplir de zéros le reste et le dire ; copier
  un fichier ou un disque entier ainsi (Locksmith « advanced disk
  recovery »). *1 jour.*
- 🟡 💾 **`DISKCMP`** : comparer deux disquettes ou deux images bloc à bloc, et
  la copie de disquette avec relecture (Copy II Plus, Locksmith « 16-sector
  compare »). Dans `DISKIMG`. *½ jour.*
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
- 🟡 **`SYNC`** : ne copier que les fichiers manquants ou plus récents entre
  les deux panneaux. *1 jour.*
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
- 🟢 **`MKIMAGE`** : créer une image `.PO` ou `.2MG` vide et formatée.
  *½ jour.*
- 🟢 **Écrire dans une image disque** ouverte comme dossier (copier VERS un
  `.PO`/`.2MG`) : la lecture existe (`IMGFS.PLG`), l'écriture demande la
  carte des blocs libres et l'allocation, c'est-à-dire un mini-ProDOS. Une
  grande surcouche. *2 jours.*
- 🟢 **`PRINT`** : catalogue ou texte vers l'imprimante du slot 1, avec
  numéro de page (Copy II Plus, ProSel). *½ jour.*
- 🟢 **`TREE`** : l'arborescence avec la taille cumulée des dossiers.
  *½ jour.*
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
