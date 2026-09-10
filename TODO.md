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
- 🟠 💾 **`BLKEDIT`** — éditeur de blocs inspiré de Block Warden/Copy II Plus :
  navigation, suivi de fichiers, hexa/ASCII, décodage répertoire/index,
  écriture après `ERASE`, extraction et recherche d’octets.
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
- 🟡 💾 **Déplacement sans copie** — surcouche MOVE réécrivant les entrées et
  corrigeant les pointeurs de parent.
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

- 🟡 **`EXTASIE`** — visionneuse des images Chat Mauve/Féline : détecter les
  images normales `IMA` (16 Ko), les images compactées `CMP` (souvent 8–12 Ko)
  et les sections enregistrées séparément; décoder le mode COL 140/560×192.
  Référence : [manuel Extasie](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/non_english/french/crealude_extasie_manuel_ocr.pdf).
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
  format Amiga ou IIGS est compatible avec l’Apple II 8 bits.

- 🟢 **`MACPAINT`, `BMP`, `GIF`, `GR`, `PRINTSHOP`, `SHAPES`, `SLIDESHOW`** —
  visionneuses d’images supplémentaires.
- 🟢 **`INTLIST`, `ADB`, `ASP`, `AWRITER`, `CALC`** — lecteurs Apple II et
  AppleWorks supplémentaires.
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

- 🟡 **`EXTASIE`** — ajouter à IMAGE la détection du type ProDOS `$F2`, la
  décompression du flux Extasie (compteur, répétitions, écriture colonne par
  colonne AUX puis MAIN) et l’affichage du DHGR mixte 560/140 de la carte
  Féline. Feuilleter les images `$F2` d’un dossier avec Gauche/Droite, signaler
  les flux tronqués et préserver le retour aux panneaux.
- Références de format et de rendu : [manuel Extasie](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/non_english/french/crealude_extasie_manuel_ocr.pdf),
  [notes Chat Mauve/POM2](https://github.com/habib256/pom2/blob/main/docs/chatmauve_plan.md)
  et les disques de test `Extasie disk1.dsk` / `Extasie disk2.dsk` du corpus
  POM2.

## Règle de livraison

Pour chaque entrée terminée : ajouter un banc reproductible, mettre à jour le
manuel et le changelog, reconstruire les six images, lancer les tests hôtes,
committer sur une branche, fusionner dans `main`, pousser et attendre la CI.
