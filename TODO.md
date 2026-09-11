# A2 File Cmd — feuille de route

Ce fichier ne contient que le travail restant. Les fonctions livrées sont
documentées dans le [CHANGELOG](CHANGELOG.md). Les priorités sont `🟠 haute`,
`🟡 moyenne` et `🟢 basse`; `💾` indique une fonction à intégrer aussi dans
BOOT/les disquettes. Les nouveaux plugins vont sur EXTRA et XL, séparément en
6502 et 65C02.

## Contraintes actuelles

- Le résident est plein : toute nouvelle fonction doit être une surcouche ou
  économiser de la place ailleurs.
- Les petites surcouches ont 1 280 octets maximum. BINARY2, IMGFS, ATTR,
  DELETE et IMAGE sont les plus proches de cette limite.
- Les essais matériels manquants sont le IIgs, une vraie Super Serial Card,
  un //c réel et les lecteurs Disk II physiques.
- Chaque nouvelle fonction doit avoir un test adapté, une entrée de manuel si
  nécessaire et une vérification des six images.

## Prochain lot : meilleur retour sur effort

- 🟠 **`FIXIT`** — grande surcouche de réparation ProDOS après confirmation
  `ERASE` : allocation, compteurs, pointeurs de répertoire, types, dates et
  effacements incomplets. Signaler les blocs partagés ou hors volume sans les
  modifier; reconstruire aussi un répertoire racine perdu et isoler les blocs
  défectueux.
- 🟡 **`MOVE` : les fichiers marqués** — `MOVE` ne déplace que l’entrée sous
  le curseur : une grande surcouche couvre les tables d’entrées à $2000, et
  les marques sont des index DANS ces tables, donc plus traduisibles en noms.
  Il faudrait soit une petite surcouche (1 280 octets, très juste pour la
  marche des répertoires), soit que le cœur passe la liste des noms marqués.
- 🟡 **`MOVE` : un arbre entre volumes** — entre deux volumes, `MOVE` copie
  puis efface, mais seulement un FICHIER : un répertoire et sa descendance
  demandent la marche récursive que `V` fait déjà dans le cœur. Soit `MOVE`
  la refait, soit le cœur lui passe la main.
- 🟡 **`MOVE` : agrandir un répertoire plein** — la cible sans entrée libre
  est refusée. L’agrandir demande d’allouer un bloc dans la table binaire du
  volume et de réécrire la taille du répertoire dans sa propre entrée : un
  travail différent, et plus risqué, que la réécriture d’entrée.
- 🟠 💾 **`NIBCOPY`** — copie brute piste par piste entre deux lecteurs 5¼
  Disk II, avec mode à un lecteur, synchronisation, vérification et rapport
  d’erreurs. Le cœur doit rester en RAM après le retrait du disque BOOT pour
  permettre les échanges source/cible sur un seul lecteur.
- 🟠 💾 **Cœur nibble 3½** — ajouter un transport séparé pour les lecteurs
  3½ (SmartPort/drive adapté), sans mélanger ses timings avec le flux Disk II
  5¼; réutiliser le tampon, la vérification et le rapport de NIBCOPY.
- 🟠 💾 **`ADTPRO`** — client du serveur ADTPro réel : dossiers, envoi/réception
  d’images, CRC, reprise sur NAK et mode nibble après NIBCOPY.
- 🟠 💾 **`NIBREAD` / `NIBWRITE`** — lecture et écriture d’une image `.NIB`
  complète, avec validation piste par piste.

## Compléments des outils existants

- 🟡 💾 **`DATE`** — dates de création et de volume; étudier un pilote
  d’horloge de session.
- 🟡 💾 **`VERIFY CERTIFY`** — écrire puis relire un motif après `ERASE`, avec
  confirmation et rapport des blocs défectueux.
- 🟡 💾 **`TAGPAT`** — plages de dates et confirmation fichier par fichier lors
  d’une copie ou d’une suppression.
- 🟡 💾 **`DIRSORT`** — trier physiquement un dossier ProDOS en conservant les
  blocs et les liens, avec sauvegarde et vérification.
- 🟡 💾 **`DRIVESPD`** — mesurer un tour de Disk II, afficher RPM et durée.
- 🟡 **`DISKIMG`** — compléter copie brute, vérification et reprise des erreurs.
- 🟡 **Décodeurs robustes** — préciser les sorties partielles de UNSHRINK,
  BINARY2, IMGFS et DOS33 sur données corrompues.

## Vérification et intégration

- 🟡 Porter `bench/run.py` sur les images XL publiées, en 6502 et 65C02.
- 🟡 Compléter le banc //c avec `run.py`, `memory.py`, souris et disquette.
- 🟡 Tester VDrive sur une vraie Super Serial Card et un //c.
- 🟡 Vérifier automatiquement les URL de crédits du manuel et ses dix pages.

## Fonctions utiles mais secondaires

- 🟡 **`LAUNCHER`** — favoris de programmes et retour automatique à A2FC.
- 🟡 **`BACKUP`** — sauvegarde/restauration d’un volume sur disquettes numérotées.
- 🟡 **`DOS33W` / `DOS33FMT`** — écrire ProDOS vers DOS 3.3 et formater 16 secteurs.
- 🟡 **`PASCALFS`**, **`SHR`**, **`TOKENIZE`** — formats Apple Pascal, IIgs et
  Applesoft tokenisé.
- 🟢 Écrire vers une image disque ouverte comme dossier.
- 🟢 **`PRINT`**, **`SETUP`**, **`SYSINFO`** — impression, configuration et
  diagnostic matériel.
- 🟢 Évaluer le support IIgs et VDrive sur Uthernet II.
- 🟢 **`TFTP` / `NTP`** — réseau et synchronisation de l’heure.
- 🟢 Table de reconnaissance type/aux-type/suffixe/en-tête.

## Formats et extensions de niche

- 🟡 **`FOT` LZ4FH** — décoder le troisième codage des images ProDOS `$08`,
  l’aux-type `$8066` (compression LZ4FH d’Andy McFadden, en-tête `66 E0`).
  `PACKFOT` lit désormais `$4000` et `$4001`; celui-ci reste à faire, et son
  décodeur ne tiendra pas dans la même fenêtre de 1 280 octets — prévoir une
  surcouche séparée. Corpus :
  `GISTDATA/IMG/SAMPLE.MEDIA/DIP.CHIPS` (3 785 o).
- 🟡 **a2dgrx : bitmaps et fontes** — `DGRVIEW` lit les écrans lo-res et
  double lo-res, et les pixmaps a2dgrx (un octet par pixel) dont il demande
  la largeur. Restent les deux autres dispositions de
  [a2dgrx](https://github.com/iolo/a2dgrx) : le bitmap (1 bit par pixel) et
  la fonte (3 octets par glyphe, 4x6 dans une boîte 3x5, ASCII `$20`-`$7F`,
  donc 288 octets — la seule des trois qu’une taille suffise à reconnaître).
  Rappel : a2dgrx est une bibliothèque de dessin, pas un format de fichier —
  aucun en-tête, aucune signature, aucune dimension, aucun type ProDOS.
- 🟡 **Polices Apple II (`$07`)** — afficher le jeu de caractères d’un fichier
  de police ProDOS type `$07` : trois octets d’en-tête (drapeau, dernier code
  `$7E`/`$7F`, hauteur) puis des glyphes de taille fixe. Corpus :
  `GISTDATA/IMG/SAMPLE.MEDIA/FONTS`, trente-cinq polices de 1 155 à 4 194
  octets (`MOUSEPAINT`, `MINI`, `ATHENS`, `VENICE`, les `SYSTEM.*` et
  `MONACO.*` de dix langues, les `MAGDALENA`/`MCMILLEN`/`MONTEREY`).
- 🟢 **`PT3` / ProTracker** — jouer un module AY ProTracker 3 sur la
  Mockingboard, à côté du lecteur `MB1` existant. Corpus :
  `GISTDATA/IMG/SAMPLE.MEDIA/AUTUMN.PT3` (type `$00`, 4 461 o, en-tête ASCII
  « ProTracker 3.3 compilation of »).
- 🟡 **`PURPLESOFT` / `GRLOAD`** — visualiser les images sauvegardées par
  Purplesoft/Féline et détecter leur mode graphique; traiter Purplesoft comme
  une bibliothèque de routines (`PURPLESOFT`, `PURPLESOFT*`), pas comme un
  format d’image ou d’animation unique. Référence : [manuel EVE/Purplesoft](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/hardware/video/lechatmauve_eve_manuel_ocr.pdf).
- 🟡 **`FANTAVISION` Apple II** — visionneuse de films vectoriels avec objets,
  images-clés, interpolation (*tweening*), écrans, sons et polices associés;
  analyser les fichiers des disques Fantavision pour documenter le format
  Apple II. Ne pas réutiliser directement le format `FANT`/IFF, qui concerne
  surtout Amiga; séparer aussi la variante IIGS. Références : [manuel
  Fantavision](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/applications/misc/Fantavision-Manual.pdf),
  [images de référence](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/graphics/fantavision).
- 🟢 **`ANIMATE` / `MOVIE MAKER`** — étudier les formats d’animations qui
  séparent personnages, fonds, scènes et séquences; ajouter des détecteurs et
  une lecture image par image après obtention d’échantillons. Référence :
  [manuel Animate Apple II](https://www.cvxmelody.net/Animate%20manual%20for%20Apple%20II%20%281986%20Broderbund%29.pdf).
- 🟢 **Échantillons et reverse engineering** — conserver pour chaque format
  une image `.dsk`/`.po`, le catalogue ProDOS ou DOS 3.3, les types/aux-types,
  les tailles, les signatures et une capture de rendu; ne pas supposer que le
  format Amiga ou IIGS est compatible avec l’Apple II 8 bits. Corpus de
  référence : `GISTDATA/IMG/SAMPLE.MEDIA` (`~/src/pom2/hdv/GISTDATA.hdv`), qui
  réunit pages brutes, `FOT` empaquetés, polices, musiques et un `$D5` non
  identifié.

- 🟢 **`MACPAINT`, `BMP`, `GIF`, `GR`, `PRINTSHOP`, `SHAPES`, `SLIDESHOW`** —
  visionneuses d’images supplémentaires. Corpus `PRINTSHOP` :
  `GISTDATA/IMG/SAMPLE.MEDIA/BBROS.MINI` (BIN `$5800`, 576 o, lignes de onze
  octets soit 88 pixels — vignette 88x52 à confirmer).
- 🟢 **`INTLIST`, `ADB`, `ASP`, `AWRITER`, `CALC`** — lecteurs Apple II et
  AppleWorks supplémentaires. `INTLIST` comble un vrai trou : un `$FA` tombe
  sur l’hexadécimal (Return) ou sur le lecteur texte (`T`), qui affichent ses
  jetons en clair, alors que `BASLIST` ne sert que le `$FC`. Corpus :
  `GISTDATA/IMG/SAMPLE.MEDIA/WOZ.BREAKOUT` (1 859 o), `APPLEVISION` (5 964 o).
- 🟢 **`DUET`, `SAMPLE`** — musique et échantillons audio additionnels.
- 🟢 **`TERM`, `XMODEM`, `CPMFS`, `SPLIT`** — communication série et formats
  de disquettes supplémentaires.
- 🟢 **`PASSWORD`, `LCASE`, `PLGINFO`** — confort et diagnostic.
- 🟢 Créer l’archive inverse **`SHRINK`**.
- 🟢 Découper `src/a2fc.c` en modules sans augmenter le résident.
- 🟢 Traduire les outils et bancs Python en anglais; le TODO reste français.
- 🟢 Défragmentation après FIXIT et VERIFY.
- 🟢 Déplacer le pilote Mockingboard dans une surcouche si l’espace le permet.
- 🟢 Étendre les parcours aux très grands répertoires.

## Visionneuse Extasie / Chat Mauve

`EXTASIE` décode et affiche désormais les images `$F2` : deux plans de
quarante colonnes de 192, auxiliaire d’abord, et le DHGR mixte 560/140 de la
carte. Reste ce qui ne tient pas dans la fenêtre :

- 🟡 **Feuilleter les images `$F2` avec Gauche/Droite** — mesuré : la
  surcouche fait 1 164 octets sur 1 280, et parcourir le panneau
  (`read_panel`, retrouver l’entrée, `build_full`, voisin suivant) en coûte
  environ 720. Le cœur sait déjà feuilleter, dans `view_image`, mais il ne
  charge que `IMAGE`; router un `$F2` vers `EXTASIE` demande de la place dans
  le résident, qui finit à `$BEDF` pour une limite de `$BEE0`. Trois voies :
  libérer une centaine d’octets dans `EXTASIE`, libérer de quoi router dans
  le cœur, ou rendre au cœur la liste des voisins par l’API.
- 🟡 **`$F2` dans `IMAGE`** — même obstacle : `IMAGE` occupe 1 167 octets sur
  1 280, et le décodeur Extasie seul en demande un peu plus de 1 100. Tant
  que le résident et `IMAGE` sont pleins, la visionneuse `$F2` reste une
  surcouche à part, lancée depuis le menu `!`.
- Références de format et de rendu : [manuel Extasie](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/non_english/french/crealude_extasie_manuel_ocr.pdf),
  [notes Chat Mauve/POM2](https://github.com/habib256/pom2/blob/main/docs/chatmauve_plan.md)
  et les disques de test `Extasie disk1.dsk` / `Extasie disk2.dsk` du corpus
  POM2.

## Règle de livraison

Pour chaque entrée terminée : ajouter un banc reproductible, mettre à jour le
manuel et le changelog, reconstruire les six images, lancer les tests hôtes,
committer sur une branche, fusionner dans `main`, pousser et attendre la CI.
