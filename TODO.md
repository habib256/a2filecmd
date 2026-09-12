# A2 File Cmd — feuille de route après la 0.8.0

La [0.8.0 est publiée](https://github.com/habib256/a2filecmd/releases/tag/v0.8.0).
Ce fichier organise le travail **restant** ; l'axe 1, consolidation, est engagé.
Les fonctions livrées sont résumées dans le [CHANGELOG](CHANGELOG.md).

## Choisir la prochaine étape

| Axe | Résultat recherché | Premier chantier proposé |
| --- | --- | --- |
| **1. Consolidation** | Retrouver de la marge pour faire évoluer A2FC | Récupérer une réserve mémoire mesurable |
| **2. Fichiers et ergonomie** | Mieux gérer dossiers, favoris et documents | MOVE d'une arborescence entre volumes |
| **3. Disques et réparation** | Diagnostiquer, réparer et préserver les supports | FIXIT : plan de réparation avant écriture |
| **4. Images et musique** | Lire davantage de médias | Étendre PT3 ou choisir un nouveau format |
| **5. Transferts et réseau** | Échanger avec d'autres machines | Définir le premier parcours ADTPro |
| **6. Qualification** | Renforcer les preuves de fiabilité | Étendre les mutations et les tests de séquences |

**Axe retenu : commencer par l'axe 1**, puis choisir une évolution visible.
La qualification 0.8.0 laisse 5 octets avant le plafond MAIN enhanced et aucun
libre en carte langage. Ces mesures doivent être recalculées à chaque lien.

## 1. Consolidation : mémoire et architecture

- [x] **Réserve mémoire** — fixer des budgets par zone à partir des deux cartes
  de lien, puis récupérer une réserve sans relâcher les plafonds.
  Premier relevé et objectifs dans [MEMORY-BUDGETS.md](docs/MEMORY-BUDGETS.md) ;
  les réserves sont affichées à chaque lien. Après consolidation de l'affichage :
  MAIN libre 290/835 octets, LC 172/169 (65C02/6502). Les premiers objectifs
  sont atteints sans relever les plafonds ; les petites surcouches restent serrées.
- [ ] **Services de fichiers sûrs** — centraliser progressivement les créations
  exclusives, remplacements récupérables et copies vérifiées ; conserver les
  tests de pannes et mesurer le coût de chaque extraction.
- [ ] **Contrats des plugins** — documenter buffers prêtés, durée de validité,
  banques modifiées, états à restaurer, erreurs et consentement AUX.
- [ ] **Parcours itératifs** — remplacer progressivement la récursivité par un
  état borné ; conserver les refus sûrs et la vérification avant suppression.
- [ ] **Découpage du résident** — extraire des modules de `src/a2fc.c` sans
  augmenter sa taille, au fil des chantiers précédents ; pas de réécriture globale.

## 2. Fichiers et ergonomie

- [ ] **MOVE d'un arbre entre volumes** — prendre en charge les répertoires et
  leur descendance ; ne supprimer aucune source après une copie partielle.
  Dépend du parcours borné de l'axe 1 ou d'un mécanisme équivalent vérifié.
- [ ] **Conversions** — compléter la comparaison intégrale du résultat relu
  pour les conversions qui ne vérifient encore que les écritures et fermetures.
- [ ] **Très grands répertoires** — étendre les scénarios et traiter les limites
  restantes ; le retour au dossier quitté et la navigation entre fenêtres sont acquis.
- [ ] **LAUNCHER** — favoris de programmes et retour automatique à A2FC.
  À isoler dans POM2 //e non amélioré : le scénario `bench/extras.py` lance
  bien Applesoft depuis DEVTOOLS, mais après `HOME` le relancement manuel
  `-/A2FC6502/A2FILE.SYSTEM` produit parfois `SYNTAX ERROR`. Le scénario
  sans `HOME` a passé ; ni l'attente de l'invite, ni `CALL 976`, ni un essai
  de passage en 40 colonnes n'ont fiabilisé le cas d'origine. Le changement
  de mode vidéo a été retiré. Le banc complet n'est donc pas validé.
- [ ] **Reconnaissance des fichiers** — généraliser l'aiguillage par type,
  aux-type, suffixe et en-tête aux formats autres que les images.
- [ ] **DATE** — dates de création et de volume ; étudier une horloge de session.
- [ ] **TAGPAT** — plages de dates et confirmation fichier par fichier lors
  d'une copie ou d'une suppression.
- [ ] **Documents** — lecteurs ADB, ASP, AWRITER et CALC ; TOKENIZE pour Applesoft.
- [ ] **Archives** — créer l'archive inverse SHRINK.
- [ ] **Confort et diagnostic** — PASSWORD, LCASE, PLGINFO, PRINT, SETUP et SYSINFO.

## 3. Disques, réparation et sauvegarde

Les travaux sur lecteurs physiques sont signalés par **💾**.

- [ ] **FIXIT : diagnostic et plan** — partir du rapport sans écriture de VOLINFO :
  allocation, références partagées, pointeurs invalides, compteurs et blocs perdus.
  Compléter le diagnostic des types, dates et effacements incomplets.
- [ ] **FIXIT : corrections** — conserver les blocs d'origine, faire choisir et
  confirmer les corrections, puis vérifier chaque écriture. Signaler les blocs
  partagés ou hors volume sans les modifier. Étudier séparément la reconstruction
  d'une racine perdue et l'isolement des blocs défectueux.
- [ ] **Reprise après coupure** — étudier sauvegarde persistante ou journal pour
  les écritures brutes, notamment MOVE et BOOTBLK. La restauration sur erreur
  signalée existe ; elle ne garantit pas la reprise après perte d'alimentation.
- [ ] **DISKIMG : reprise** — nouvelles tentatives après erreur et reprise après
  interruption ; conserver la validation des sources et le refus d'auto-écrasement.
- [ ] **💾 VERIFY CERTIFY** — écrire puis relire un motif après ERASE, avec
  confirmation et rapport des blocs défectueux.
- [ ] **💾 DIRSORT** — tri physique d'un dossier ProDOS avec sauvegarde des blocs,
  conservation des liens et vérification.
- [ ] **💾 NIBCOPY 5¼** — copie brute piste par piste, à un ou deux lecteurs Disk II,
  avec synchronisation, vérification et rapport. Garder le cœur en RAM pour
  permettre les échanges source/cible après retrait de BOOT.
- [ ] **💾 NIBREAD / NIBWRITE** — images `.NIB` complètes, validées piste par piste ;
  s'appuyer sur le transport NIBCOPY.
- [ ] **💾 Transport nibble 3½** — établir les possibilités du matériel et du
  contrôleur, puis un transport distinct des timings Disk II 5¼ ; partager les
  tampons, vérifications et rapports lorsque c'est applicable.
- [ ] **💾 DRIVESPD** — mesure d'un tour Disk II, RPM et durée.
- [ ] **BACKUP** — sauvegarde/restauration d'un volume sur disquettes numérotées.
- [ ] **DOS33W / DOS33FMT** — écriture ProDOS vers DOS 3.3 et formatage 16 secteurs.
- [ ] **PASCALFS / CPMFS** — accès aux formats Apple Pascal et CP/M.
- [ ] **Écriture dans les images** — modifier une image ouverte comme dossier.
- [ ] **Défragmentation** — après FIXIT et VERIFY.

## 4. Images, animations et musique

- [x] **PT3 : grands modules** — jusqu'à 65 535 octets, cache en mémoire
  principale, source en lecture seule et préservation de `/RAM`.
- [ ] **PT3 : compatibilité** — anciennes tables de fréquences autres que ST,
  effets multiples par ligne et TurboSound.
  Le lecteur, les crédits, le feuilletage et la vérification des volumes sont acquis.
- [ ] **Contrat commun des visualiseurs** — uniformiser ouverture, navigation,
  erreurs, sortie et restauration de l'écran ; conserver le consentement AUX.
- [ ] **a2dgrx** — bitmaps et fontes, au-delà des pixmaps déjà lus par DGRVIEW.
  Bibliothèque sans en-tête ni dimensions : définir les paramètres nécessaires
  à l'ouverture. La fonte décrite dans les références contient 288 octets.
- [ ] **PURPLESOFT / GRLOAD** — identifier le mode des images Purplesoft/Féline ;
  distinguer les bibliothèques de routines des données graphiques sauvegardées.
- [ ] **FANTAVISION Apple II** — analyser les fichiers, puis lire objets,
  images-clés, interpolation, écrans, sons et polices. Ne pas confondre les
  variantes Apple II 8 bits, IIGS et Amiga (`FANT`/IFF).
- [ ] **ANIMATE / MOVIE MAKER** — obtenir des échantillons, distinguer personnages,
  fonds, scènes et séquences, puis commencer par une lecture image par image.
- [ ] **Autres images** — MACPAINT, BMP, GIF, SHAPES, SLIDESHOW et SHR (IIgs).
- [ ] **Autres sons** — DUET et SAMPLE.
- [ ] **Corpus et rétro-ingénierie** — conserver image disque, catalogue,
  type/aux-type, taille, signature et capture pour chaque format. Identifier le
  `$D5` restant dans `GISTDATA/SAMPLE.MEDIA` ; ne pas présumer la compatibilité
  des variantes Amiga ou IIGS avec l'Apple II 8 bits.

Corpus de référence : `~/src/pom2/hdv/GISTDATA.hdv`, utilisé en lecture seule.
Voir [l'inventaire des médias](docs/SAMPLE-MEDIA.md). APPLEVISION (5 964 octets)
est déjà lisible par INTBASIC et n'est pas un nouveau lecteur à implémenter.

Références conservées pour l'étude des formats :

- [a2dgrx](https://github.com/iolo/a2dgrx).
- [Manuel EVE/Purplesoft](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/hardware/video/lechatmauve_eve_manuel_ocr.pdf).
- [Manuel Fantavision](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/applications/misc/Fantavision-Manual.pdf)
  et [images disque](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/graphics/fantavision).
- [Manuel Animate](https://www.cvxmelody.net/Animate%20manual%20for%20Apple%20II%20%281986%20Broderbund%29.pdf).
- [Manuel Extasie](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/non_english/french/crealude_extasie_manuel_ocr.pdf),
  [notes Chat Mauve/POM2](https://github.com/habib256/pom2/blob/main/docs/chatmauve_plan.md)
  et disques `Extasie disk1.dsk` / `Extasie disk2.dsk` du corpus POM2.

## 5. Transferts, communication et réseau

- [ ] **💾 ADTPRO** — client du serveur réel : navigation dans les dossiers,
  envoi/réception d'images, CRC et reprise sur NAK. Ajouter le mode nibble
  après NIBCOPY, indépendamment des premiers transferts par blocs.
- [ ] **TERM / XMODEM** — terminal et transferts série.
- [ ] **SPLIT** — découpage et réassemblage pour les transferts.
- [ ] **VDrive** — évaluer le transport sur Uthernet II ; qualification matérielle
  avec une vraie Super Serial Card et sur //c dans l'axe 6.
- [ ] **TFTP / NTP** — transferts réseau et synchronisation de l'heure.

## 6. Qualification, automatisation et documentation

- [ ] **Mutations** — étendre `tools/fuzz_images.py` aux autres décodeurs,
  à UNSHRINK, BINARY2, IMGFS et DOS33 ; enrichir les corpus et intégrer la
  campagne à la CI. Sept décodeurs d'images sont déjà couverts.
- [ ] **Tests de séquences** — image → musique → copie, annulation → nouvelle
  opération, changement de disque → reprise ; vérifier états, ressources et octets.
- [ ] **Images XL publiées** — porter la session complète `bench/run.py` sur
  les éditions 6502 et 65C02.
- [ ] **Banc //c** — compléter session, pile et disquette ; vérifier la souris
  sur les configurations équipées.
- [ ] **💾 Matériel** — étendre au IIgs, documenter les lecteurs Disk II et tester
  VDrive avec Super Serial Card et sur //c. Les retours matériels sur //c et
  les deux IIe sont acquis, sans valoir qualification de chaque future révision.
- [ ] **Manuel et crédits** — automatiser la vérification des liens et la
  génération du PDF.
- [ ] **Langue des outils** — traduire outils et bancs Python en anglais ;
  conserver le TODO en français.

## Acquis de la 0.8.0

Retirés des tâches ouvertes : sauvegarde sûre des préférences, MOVE des fichiers
marqués, menu par catégories, questions inversées, ouverture automatique des
images, feuilletage Extasie et autres médias, retour au dossier quitté,
lecteurs MB1 et PT3 au premier plan. La qualification de la révision publiée
et sa CI ont été effectuées ; ce processus reste obligatoire pour les suivantes.
Voir le [changelog](CHANGELOG.md) et le [rapport de qualification](docs/BUG-HUNT-0.8.0.md).

## Règles communes à tous les axes

La préservation des données prime : appliquer [AGENTS.md](AGENTS.md) et consulter
[DATA-SAFETY.md](docs/DATA-SAFETY.md). Toute destruction du contenu de `/RAM`
nécessite un avertissement et une confirmation **avant** le premier accès destructif.

Pour chaque modification native :

- Identifier fichiers, volumes, buffers et banques pouvant être écrits.
- Ajouter les régressions pertinentes et contrôler les octets conservés lors
  des pannes ; utiliser uniquement des supports jetables pour les essais destructifs.
- Valider les deux architectures, la pile, le BSS et toutes les surcouches.
  Une petite fenêtre contient 1 280 octets ; les grandes ont leurs propres limites.
- Mesurer les disquettes (280 blocs) et classer tout nouveau plugin dans
  [config/packages.mk](config/packages.mk), sans assouplir les contrôles mémoire.

Pour terminer un chantier : retirer sa tâche ouverte, actualiser manuel et
changelog, puis exécuter les tests adaptés. Avant livraison : `make test`,
construction des sept supports, `tools/check_images.py` et échanges de catégories
avec `bench/extras.py`. Associer révision, version, empreintes, outils et résultats.
Committer sur une branche, fusionner dans `main`, pousser et vérifier la CI,
y compris POM2 lorsque l'exécuteur est configuré. Distinguer essais locaux,
émulateur, CI et matériel ; ne pas promettre l'atomicité des écritures physiques.
