# A2 File Cmd — feuille de route

Ce fichier suit le travail restant et les chantiers en cours. Les fonctions
implémentées sont décrites dans le [CHANGELOG](CHANGELOG.md), qui distingue
les changements non publiés des versions livrées. Priorités : `🟠 haute`,
`🟡 moyenne`, `🟢 basse`. `💾` signale un besoin propre aux disquettes ou aux
lecteurs physiques.

La préservation des données prime sur toute fonctionnalité : appliquer
[AGENTS.md](AGENTS.md) et consulter le [rapport de sécurité](docs/DATA-SAFETY.md).
La reconstruction de `/RAM` reste permise, avec avertissement et confirmation
avant toute destruction de son contenu.

## Contraintes à vérifier à chaque modification native

- **Résident et carte langage** : marges très faibles. Relever les résultats
  du lien courant pour les deux processeurs ; ne pas réutiliser les anciennes
  mesures du TODO. `tools/check_layout.py` contrôle notamment le plafond
  `$BEE0` du fichier résident, la pile et la disposition mémoire.
- **Surcouches** : une petite fenêtre contient 1 280 octets. Les grandes
  surcouches ont des limites propres à leurs tampons ; code et BSS doivent
  rester dans les bornes imposées par le lieur.
- **Disquettes** : 280 blocs par support. Mesurer chaque catégorie après
  fabrication et contrôler la présence de tous les plugins attendus.
  [config/packages.mk](config/packages.mk) définit les catégories ; chaque
  nouveau plugin doit y être classé explicitement.

## Évaluation d'architecture et consolidation — 12 septembre 2026

Évaluation d'étape fondée sur le code et les résultats examinés, sans constituer
un nouvel audit exhaustif : A2FC est un logiciel sérieux dont la richesse
fonctionnelle dépasse désormais la marge de maintenance du résident.

Points forts à préserver : architecture en surcouches adaptée à la machine,
lecteurs au premier plan, ergonomie commune (Entrée, flèches, Échap), garanties
de conservation des données et tests du vrai code avec erreurs injectées,
comparaison des octets et exécution sur les deux processeurs.

Risques principaux : saturation mémoire, dépendances implicites entre services,
buffers et banques, profondeur limitée des parcours récursifs et couverture
encore inégale des interactions. La dernière qualification du
[bug hunt](docs/BUG-HUNT-0.7.6.md) relevait cinq octets avant le plafond MAIN
enhanced et aucune marge en carte langage : ce sont des mesures historiques,
à recalculer après chaque modification native. Un lecteur qui produit du son
n'est pas, à lui seul, la preuve que l'équilibre de ses canaux est correct.
La livraison et ses métadonnées font également partie du logiciel à valider.

Orientation recommandée : **0.8.0** pour le périmètre fonctionnel acquis depuis
0.7.5, puis consolidation avant de nouvelles fonctions natives. Cette
recommandation ne change ni le numéro construit ni l'état de publication.
Procéder par extractions progressives guidées par les risques et les mesures,
sans réécriture générale.

- 🟠 **Réserve mémoire** — définir un budget explicite par zone et récupérer
  une réserve mesurable avant d'ajouter des fonctions natives. Fixer les
  objectifs à partir des cartes de lien des deux architectures, sans relâcher
  les plafonds, pour pouvoir corriger sans déplacer systématiquement le code.
- 🟠 **Services de fichiers sûrs** — centraliser progressivement les créations
  exclusives, remplacements récupérables et copies vérifiées derrière des
  contrats communs. Éviter les variantes de garanties entre surcouches ;
  conserver les tests de pannes et mesurer le coût mémoire des extractions.
- 🟠 **Qualification d'une révision figée** — associer version, révision,
  empreintes des artefacts, versions des outils et résultats de validation.
  Distinguer explicitement les essais locaux, CI, émulateur et matériel pour
  identifier exactement le contenu prêt à publier.
- 🟡 **Contrats des services et plugins** — documenter les buffers prêtés,
  leur durée de validité, les banques modifiées, les états à restaurer et les
  erreurs possibles. Rendre explicites les dépendances entre résident et
  surcouches, y compris l'utilisation d'AUX et le consentement préalable.
- 🟡 **Parcours itératifs** — remplacer progressivement la récursivité par un
  parcours à état borné et consommation mémoire prévisible. Préserver les
  refus sûrs et la vérification complète avant suppression ; tester les arbres
  profonds et les échecs à chaque étape sur des supports jetables.
- 🟡 **Tests de séquences** — couvrir image → musique → copie, annulation →
  nouvelle opération et changement de disque → reprise. Vérifier les états
  restaurés, les ressources libérées et les octets conservés, au-delà du seul
  succès de chaque fonction isolée.
- 🟢 **Contrat commun des visualiseurs** — uniformiser ouverture, navigation,
  sortie, erreurs et restauration de l'écran pour les formats existants avant
  d'en ajouter d'autres. Conserver les confirmations requises avant toute
  utilisation destructive de la mémoire auxiliaire.

## Priorité : sécurité des données

- 🟠 **Décodeurs robustes** — étendre la campagne de mutations de
  `tools/fuzz_images.py`, qui couvre DGRVIEW, EXTASIE, PACKFOT,
  PAINT816, FONTVIEW, PRINTSHOP et LZ4FH, aux autres décodeurs ainsi qu'à UNSHRINK, BINARY2,
  IMGFS et DOS33. Élargir les corpus et intégrer la campagne à la CI.
  Vérifier les bornes mémoire, la conservation des fichiers existants et
  le signalement des sorties partielles et des erreurs d'E/S. Les tests
  existants ne constituent pas une preuve exhaustive de robustesse.
- 🟡 **Reprise après coupure** — étudier une sauvegarde persistante ou un
  journal pour les écritures brutes, notamment MOVE et BOOTBLK. Distinguer
  la restauration sur erreur signalée, déjà implémentée, de la reprise après
  perte d'alimentation ; tester les interruptions à chaque étape.
- 🟡 **Conversions : relecture du résultat** — compléter les conversions
  qui contrôlent les écritures et fermetures sans encore comparer
  intégralement le résultat relu sur le support.
- ✅ **Configuration de session** — sauvegarde exclusive dans un temporaire,
  relecture de contrôle et conservation d'une sauvegarde récupérable de
  `A2FILE.CFG`, avec tests de pannes et de collisions.

## Disques, réparation et transferts

- 🟠 **`FIXIT`** — préparer un diagnostic et un plan de réparation ProDOS
  vérifiables avant toute écriture. Conserver les blocs d'origine, demander
  confirmation pour les corrections retenues et vérifier chaque écriture :
  allocation, compteurs, pointeurs de répertoire, types, dates et
  effacements incomplets. Signaler les blocs partagés ou hors volume sans les
  modifier; reconstruire aussi un répertoire racine perdu et isoler les blocs
  défectueux. `VOLINFO` signale déjà, sans rien écrire, les blocs occupés
  mais marqués libres, les références partagées, les pointeurs invalides, les
  compteurs faux et les blocs perdus : c'est son rapport que `FIXIT` doit
  savoir corriger, poste par poste. Les types, les dates et les effacements
  incomplets restent à diagnostiquer aussi.
- 🟠 💾 **`NIBCOPY`** — copie brute piste par piste entre deux lecteurs 5¼
  Disk II, avec mode à un lecteur, synchronisation, vérification et rapport
  d'erreurs. Le cœur doit rester en RAM après le retrait du disque BOOT pour
  permettre les échanges source/cible sur un seul lecteur.
- 🟠 💾 **Cœur nibble 3½** — ajouter un transport séparé pour les lecteurs
  3½ (SmartPort/drive adapté), sans mélanger ses timings avec le flux Disk II
  5¼; réutiliser le tampon, la vérification et le rapport de NIBCOPY.
- 🟠 💾 **`NIBREAD` / `NIBWRITE`** — lecture et écriture d'une image `.NIB`
  complète, avec validation piste par piste.
- 🟠 💾 **`ADTPRO`** — client du serveur ADTPro réel : dossiers, envoi/réception
  d'images, CRC, reprise sur NAK et mode nibble après NIBCOPY.
- ✅ **`MOVE` : les fichiers marqués** — manifeste exclusif et vérifié
  `A2MOVE.LST`, orchestration par BATCH, arrêt sur erreur/annulation et
  restauration des marques restantes par nom. Voir `bench/roi.py`.
- 🟡 **`MOVE` : un arbre entre volumes** — entre deux volumes, `MOVE` copie
  puis efface, mais seulement un FICHIER : un répertoire et sa descendance
  demandent la marche récursive que `V` fait déjà dans le cœur. Soit `MOVE`
  la refait, soit le cœur lui passe la main.

## Compléments des outils existants

- 🟡 💾 **`DATE`** — dates de création et de volume; étudier un pilote
  d'horloge de session.
- 🟡 💾 **`VERIFY CERTIFY`** — écrire puis relire un motif après `ERASE`, avec
  confirmation et rapport des blocs défectueux.
- 🟡 💾 **`TAGPAT`** — plages de dates et confirmation fichier par fichier lors
  d'une copie ou d'une suppression.
- 🟡 💾 **`DIRSORT`** — trier physiquement un dossier ProDOS en conservant les
  blocs et les liens, avec sauvegarde et vérification.
- 🟡 💾 **`DRIVESPD`** — mesurer un tour de Disk II, afficher RPM et durée.
- 🟡 **`DISKIMG` : reprise des erreurs** — définir une politique de nouvelles
  tentatives et de reprise après interruption. La copie de disques et la
  relecture de contrôle existent déjà ; préserver la validation des sources
  et le refus de cibler le volume qui contient l'image.
- 🟢 Défragmentation, après `FIXIT` et `VERIFY`.
- 🟢 Étendre les parcours aux très grands répertoires.

## Formats et extensions de niche

- ✅ **Images Extasie : feuilletage** — Gauche/Droite passe d'une image
  du même type à l'autre, y compris entre fenêtres de catalogue. L'ouverture
  directe par Entrée et I et la confirmation avant utilisation destructive
  d'AUX sont conservées ; les parcours sont validés sur les deux processeurs.
  - Références : [manuel Extasie](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/non_english/french/crealude_extasie_manuel_ocr.pdf),
    [notes Chat Mauve/POM2](https://github.com/habib256/pom2/blob/main/docs/chatmauve_plan.md),
    disques `Extasie disk1.dsk` / `Extasie disk2.dsk` du corpus POM2.
- 🟡 **a2dgrx : bitmaps et fontes** — `DGRVIEW` lit les écrans lo-res et
  double lo-res, et les pixmaps a2dgrx (un octet par pixel) dont il demande
  la largeur. Restent les deux autres dispositions de
  [a2dgrx](https://github.com/iolo/a2dgrx) : le bitmap (1 bit par pixel) et
  la fonte (3 octets par glyphe, 4x6 dans une boîte 3x5, ASCII `$20`-`$7F`,
  donc 288 octets — la seule des trois qu'une taille suffise à reconnaître).
  Rappel : a2dgrx est une bibliothèque de dessin, pas un format de fichier —
  aucun en-tête, aucune signature, aucune dimension, aucun type ProDOS.
- 🟡 **`PURPLESOFT` / `GRLOAD`** — visualiser les images sauvegardées par
  Purplesoft/Féline et détecter leur mode graphique; traiter Purplesoft comme
  une bibliothèque de routines (`PURPLESOFT`, `PURPLESOFT*`), pas comme un
  format d'image ou d'animation unique. Référence : [manuel EVE/Purplesoft](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/hardware/video/lechatmauve_eve_manuel_ocr.pdf).
- 🟡 **`FANTAVISION` Apple II** — visionneuse de films vectoriels avec objets,
  images-clés, interpolation (*tweening*), écrans, sons et polices associés;
  analyser les fichiers des disques Fantavision pour documenter le format
  Apple II. Ne pas réutiliser directement le format `FANT`/IFF, qui concerne
  surtout Amiga; séparer aussi la variante IIGS. Références : [manuel
  Fantavision](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/applications/misc/Fantavision-Manual.pdf),
  [images de référence](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/graphics/fantavision).
- 🟢 **PT3 : étendre la compatibilité** — modules de plus de 4 608 octets,
  anciennes tables de fréquences autres que ST, effets spéciaux multiples
  par ligne et TurboSound. Le lecteur au premier plan existe désormais.
- 🟢 **`ANIMATE` / `MOVIE MAKER`** — étudier les formats d'animations qui
  séparent personnages, fonds, scènes et séquences; ajouter des détecteurs et
  une lecture image par image après obtention d'échantillons. Référence :
  [manuel Animate Apple II](https://www.cvxmelody.net/Animate%20manual%20for%20Apple%20II%20%281986%20Broderbund%29.pdf).
- 🟢 **`MACPAINT`, `BMP`, `GIF`, `SHAPES`, `SLIDESHOW`** —
  visionneuses d'images supplémentaires.
- 🟢 **`ADB`, `ASP`, `AWRITER`, `CALC`** — lecteurs Apple II et AppleWorks
  supplémentaires. Corpus : `GISTDATA/SAMPLE.MEDIA/APPLEVISION`
  (5 964 o), déjà lisible par `INTBASIC`.
- 🟢 **`DUET`, `SAMPLE`** — musique et échantillons audio additionnels.
- 🟢 **`TERM`, `XMODEM`, `CPMFS`, `SPLIT`** — communication série et formats
  de disquettes supplémentaires.
- 🟢 **`PASSWORD`, `LCASE`, `PLGINFO`** — confort et diagnostic.
- 🟢 **Échantillons et reverse engineering** — conserver pour chaque format
  une image `.dsk`/`.po`, le catalogue ProDOS ou DOS 3.3, les types/aux-types,
  les tailles, les signatures et une capture de rendu; ne pas supposer que le
  format Amiga ou IIGS est compatible avec l'Apple II 8 bits. Corpus de
  référence : `GISTDATA/SAMPLE.MEDIA` (`~/src/pom2/hdv/GISTDATA.hdv`), qui
  réunit pages brutes, `FOT` empaquetés, polices, musiques et un `$D5` non
  identifié.

## Fonctions utiles mais secondaires

- 🟡 **`LAUNCHER`** — favoris de programmes et retour automatique à A2FC.
- 🟡 **`BACKUP`** — sauvegarde/restauration d'un volume sur disquettes numérotées.
- 🟡 **`DOS33W` / `DOS33FMT`** — écrire ProDOS vers DOS 3.3 et formater 16 secteurs.
- 🟡 **`PASCALFS`**, **`SHR`**, **`TOKENIZE`** — formats Apple Pascal, IIgs et
  Applesoft tokenisé.
- 🟢 Créer l'archive inverse **`SHRINK`**.
- 🟢 Écrire vers une image disque ouverte comme dossier.
- 🟢 **`PRINT`**, **`SETUP`**, **`SYSINFO`** — impression, configuration et
  diagnostic matériel.
- 🟢 Évaluer VDrive sur Uthernet II.
- 🟢 **`TFTP` / `NTP`** — réseau et synchronisation de l'heure.
- 🟢 Généraliser la reconnaissance type/aux-type/suffixe/en-tête aux
  formats autres que les images, à partir de l'aiguillage existant.

## Chantiers internes

- 🟢 Découper `src/a2fc.c` en modules sans augmenter le résident.
- ✅ Pilote MB1 dans MUSIC.PLG : lecteur au premier plan, pause/reprise,
  retour par Échap ou fin du morceau, 4 Ko en MAIN, sans toucher AUX.
- 🟢 Traduire les outils et bancs Python en anglais; le TODO reste français.

## Vérification et intégration

- 🟡 Porter `bench/run.py` sur les images XL publiées, en 6502 et 65C02.
- 🟡 Compléter le banc //c avec `run.py`, `memory.py`, souris et disquette.
- 🟡 💾 Étendre la validation matérielle au IIgs ; documenter les lecteurs
  Disk II et tester VDrive avec une vraie Super Serial Card et sur un //c.
  Le fonctionnement sur //c, IIe enhanced et IIe unenhanced est confirmé
  sur matériel réel le 12 septembre 2026.
- 🟡 Vérifier automatiquement les liens de crédits et la génération du manuel PDF.

## Règle de livraison

Pour chaque entrée terminée, retirer le travail accompli de cette liste et
mettre à jour le manuel et le changelog. Pour les modifications natives,
ajouter les régressions pertinentes, valider les deux architectures et
exécuter les bancs émulateur concernés sur des volumes jetables. Toute
correction d'un risque de perte de données doit contrôler les octets
préservés, y compris lors des pannes injectées.

Exécuter `make test`, reconstruire les **sept supports** de la distribution
retenue (BOOT, FILES, MEDIA, DISKTOOLS et DEVTOOLS en 6502 ; XL en 6502 et
65C02), puis les contrôler avec `tools/check_images.py`. Vérifier les
demandes de catégorie et les échanges sur un lecteur avec `bench/extras.py`.
Lors de la livraison Git : committer sur une branche, fusionner dans `main`,
pousser et vérifier le résultat de la CI, y compris les bancs POM2 lorsque
l'exécuteur est configuré.
