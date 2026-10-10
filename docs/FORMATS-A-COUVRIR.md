# Formats Apple II pour lesquels un lecteur reste utile

État au 10 octobre 2026. Ce registre distingue une **famille à étudier** d’un format réellement identifié. Il ne prétend pas épuiser tous les logiciels privés ou toutes leurs versions.

Les priorités sont un jugement de développement : 1 = format documenté ou besoin immédiat ; 2 = documents importants à récupérer ; 3 = recherche avec échantillons ; 4 = IIgs, conservé hors priorité actuelle. Les nombres ci-dessous sont des **entrées de l’inventaire public Asimov**, pas des documents, ni des fichiers uniques.

## Lecteurs manquants et variantes

| Famille / format | Priorité | État A2FC | Inventaire public | Travail utile |
| --- | ---: | --- | ---: | --- |
| Bordures Print Shop / Print Shop Companion | 1 | partiel | 131 | PSBORDER lit BIN 144/148 et ProDOS $F5 aux $2000 (264 octets), trois motifs 24×14. Restent assemblage, options et masques. |
| Polices Print Shop / Companion | 1 | partiel | 131 | PSFONT lit BIN aux $6000/$5FF4 et ProDOS $F5 aux $1000 (95 entrées), avec défilement. Reste le texte composé. |
| Magic Window / Magic Window II | 1 | partiel | 4 | MAGWIN lit les BIN .MW en texte paginé, directement en DOS. Restent typographie, en-têtes/pieds et versions non qualifiées. |
| LISA v3 | 1 | partiel | 14 | LISAV3 lit symboles et jetons standard, jusqu’à 512 symboles. Restent dialectes ANIX et comparaison complète à l’original. |
| LISA v4/v5 (LISA 8/16) | 2 | partiel | 14 | LISAV4 lit LISA 8/16 INT aux $4000–$5FFF : symboles, macros, nombres 24/32 bits, adressage et commentaires. Table de symboles limitée à 2816 octets. Restent variantes non qualifiées et comparaison complète au logiciel original. |
| Fichiers texte DOS à accès aléatoire | 1 | partiel | 988 | DOSREC inspecte les enregistrements de longueur choisie, NUL et trous (--), directement en DOS/DSK/2MG. Restent schémas de champs ; EOF exact et longueur absents du format, espace logique limité à 560 secteurs. |
| WordPerfect Apple II | 2 | partiel | 11 | WORDPERF : texte ProDOS $A0/$0000, contrôles connus et notes ; mise en page, autres familles et commandes multioctets inconnues restent hors profil. |
| PFS:Write | 2 | partiel | 8 | PFSWRITE lit les documents ProDOS $16 aux $0002 : texte paginé et contrôles visibles. Huit contenus distincts testés. Restent mise en forme, fusion et variantes anciennes. |
| PFS:File / PFS:Report | 2 | partiel | 6 | PFSFILE lit formulaires et fiches actives ProDOS $16/$0001 A2CD00 : 49 fiches de deux bases qualifiées. Restent rapports, anciens disques et variantes ; 256 KiB, 8 cellules par fiche/formulaire, 32 noms de champs. |
| PFS:Plan | 2 | partiel | 2 | PFSPLAN lit les six feuilles ProDOS $16/$0004 B00 : libellés principaux, valeurs enregistrées et formules de lignes/colonnes sans recalcul. Restent titres de groupes, formats, formules propres aux cellules et autres profils ; 32 lignes, 16 colonnes. |
| Quick File / Quick File II | 2 | à étudier | 6 | Format exact et documents de données à établir. |
| Bank Street Filer | 2 | partiel | 3 | BSFILER : bases AFILER 1.0 extraites en BIN, champs, nombres et dates ; précision flottante limitée à trois décimales, formules identifiées sans exécution. |
| DB Master | 2 | à étudier | 3 | Format exact et documents de données à établir. |
| VisiFile / VisiDex | 2 | à étudier | 6 | Format exact et documents de données à établir. |
| Microsoft Multiplan | 2 | partiel | 5 | MULTPLAN : sauvegardes normales v1.06 extraites intactes en ProDOS $F4 ; cellules et valeurs BCD, tokens de formules. Pas de recalcul, de format Symbolic ni de DOS R direct. |
| SuperCalc / SuperCalc 3a | 2 | à étudier | 5 | Distinguer les éditions Apple II natives des éditions CP/M ; formats à confirmer. |
| Magic Slate | 2 | à étudier | 29 | Format exact et documents de données à établir. |
| MouseWrite | 2 | partiel | 10 | MOUSEWR : texte ProDOS $F1/$0000, en-têtes MW 1/4/5, largeur de ligne du fichier ; polices et dessin non reproduits. |
| Zardax | 2 | à étudier | 8 | Format exact et documents de données à établir. |
| Screen Writer / Screenwriter II | 2 | à étudier | 3 | Format exact et documents de données à établir. |
| Super-Text / Super-Text II | 2 | à étudier | 6 | Format exact et documents de données à établir. |
| EasyWriter / EasyWriter II | 2 | à étudier | 6 | Format exact et documents de données à établir. |
| Letter Perfect | 2 | à étudier | 1 | Format exact et documents de données à établir. |
| Pie Writer / Apple Pie | 3 | à étudier | 5 | Format exact et documents de données à établir. |
| SpeedScript | 3 | à étudier | 1 | Format exact et documents de données à établir. |
| Cut & Paste | 3 | à étudier | 2 | Format exact et documents de données à établir. |
| Paperclip | 3 | à étudier | 1 | Format exact et documents de données à établir. |
| Word Juggler | 3 | à étudier | 4 | Format exact et documents de données à établir. |
| Bard’s Apprentice / WordBench | 3 | à étudier | 20 | Format exact et documents de données à établir. |
| FredWriter / FreeWriter / MECC Writer | 3 | à étudier | 10 | Format exact et documents de données à établir. |
| Desktop Plan / FlashCalc / MagicCalc | 3 | à étudier | 6 | Format exact et documents de données à établir. |
| GeoCalc / Practicalc / VIP Professional | 3 | à étudier | 17 | Format exact et documents de données à établir. |
| DBF dBase II (CP/M) | 2 | à étudier | 5 | Table de champs, enregistrements et marques de suppression ; nécessite le navigateur CP/M, pas l’exécution Z80. |
| WordStar (CP/M) | 3 | à étudier | 2 | Texte avec bits hauts et commandes ; lecteur possible sur 6502 après extraction CP/M. |
| Movie Maker .MVM | 2 | partiel | 7 | MVMOVIE : films de profil 01/02/03/06/05/00/07, images couleur 40×48 au clavier ; rectangles opaques, sans cadence originale ni masque transparent. Code embarqué refusé. |
| Graphics Magician .DPC | 2 | partiel | 17 | DGMAGI : DHGR 560 points, dessins/pinceaux/remplissage/palettes ; police de remplacement. Mode de ligne transitoire 7 non qualifié et refusé. |
| Graphics Magician dialectes Comprehend | 3 | partiel | 31 | Formats de jeux et stockage propre ; ne pas les assimiler aux dessins V82/V84. |
| The New Print Shop / projets de publication | 2 | à étudier | 28 | Type $F5 insuffisant : ce type sert aussi à des commandes et accessoires. Requiert de vrais projets. |
| Printographer / Printmaster / Printing Press | 3 | à étudier | 9 | Clip art, polices et projets à distinguer ; présence du programme ne prouve pas celle de documents. |
| Pinball Construction Set .PB | 3 | partiel | 39 | PCSVW : aperçu statique du décor, polygones et contours des objets LIB ; physique, scripts et sprites originaux non exécutés. |
| Music Printer / SongWriter | 3 | à étudier | 3 | Notes et portées / écoute ; formats sans rapport démontré avec MCS. |
| Partitions Music Construction Set : variantes | 2 | partiel | 14 | MCS/DOSMCS lisent exports et paires documentées ; réglages de l’éditeur et variantes non qualifiées restent ouverts. |
| Codefiles UCSD Pascal | 3 | à étudier | 121 | Sommaire des segments, procédures et références ; différent des textes déjà lus par PASTEXT. |
| Objets relocatables / bibliothèques 6502 | 3 | à étudier | 180 | Lister symboles et sections après identification du dialecte ; désassembler brut ne suffit pas. |
| AppleWorks GS : traitement de texte | 4 | hors priorité 8 bits | 0 | Format distinct d’AppleWorks classique ; convertisseur public disponible. |
| AppleWorks GS : tableur / base de données | 4 | hors priorité 8 bits | 0 | Schémas, cellules et données ; pas pris en charge par AWDATA classique. |
| SHR / APF / Paintworks / DreamGrafix / 3200 couleurs | 4 | hors priorité 8 bits | 4 | Aperçu réduit possible, avec limites de palette/résolution à définir ; formats documentés. |
| Animations Paintworks / SHR | 4 | hors priorité 8 bits | 3 | Format exact et documents de données à établir. |
| Polices QuickDraw II et icônes Finder | 4 | hors priorité 8 bits | 59 | Types $C8/$CA ; aperçu des glyphes et masques, distinct de FONTVIEW. |
| Print Shop GS : bordures, polices, clip art | 4 | hors priorité 8 bits | 0 | Aux $C31x/$C32x : graphiques monochromes et couleur, différents du Print Shop original. |
| Ensoniq / ASIF / SoundSmith | 4 | hors priorité 8 bits | 0 | Échantillons, instruments et séquences ; lecteur 8 bits éventuel avec rendu adapté. |
| OMF et ressources GS/OS | 4 | hors priorité 8 bits | 0 | Afficher sections/symboles et index des ressources ; ne pas exécuter les objets. |

## Déjà présents, à ne pas recompter comme manquants

AppleWorks classique (AWP, base et tableur AWDATA), VisiCalc, Epistole, Papyrus, HomeWord, Bank Street Writer, textes Pascal, Merlin, S-C Assembler, LISA v2/v3 standard, Magic Window (texte), Gutenberg extrait, Teach (fourche de données), MultiScribe TXT/WPF et Apple Writer ont un lecteur. MultiScribe et Apple Writer donnent un aperçu texte, pas une reproduction typographique de l’impression. BeagleWrite présente au moins un document avec le même en-tête MultiScribe ; cela ne qualifie pas toutes ses versions.

Les images HGR/DHGR, Dazzle Draw, PACKFOT, LZ4FH, Extasie, 816/Paint, Arlequin, Purplesoft, Graphics Magician HGR, MacPaint, formes Applesoft, clip art Print Shop, Fontrix, HRCG/MGTK, Newsroom, Fantavision et Take 1 ont déjà une prise en charge avec leurs limites documentées. MB1, PT3, Electric Duet et Music Construction Set ont des lecteurs sonores.

## Suites de lecteurs existants

- PASTEXT : raccorder le choix automatique du navigateur Pascal.
- Newsroom PN/PG : rendu graphique de la page assemblée et polices d’origine ; la structure et le texte sont déjà lisibles.
- DOCVIEW : qualification Bank Street Writer contre l’original, caractères nationaux Papyrus et variantes ; pagination imprimante et quelques calculs Epistole.
- MULTISCR : polices proportionnelles, couleurs/styles et règles ; autres versions et caractères non ASCII.
- APPLEWR : justification complète, paramètres d’impression, en-têtes/pieds, publipostage/WPL. Ces commandes restent visibles et ne sont jamais exécutées.
- FONTRIX : aperçu HGR à la taille originale, au-delà de l’aperçu texte existant.

Les conteneurs SHK/BNY/ZIP/AppleSingle/BinSCII et les images de disque ne sont pas des formats de documents : ils demandent un navigateur ou une extraction, puis le lecteur du contenu. Aucun support WOZ comme dossier n’est ajouté (exclusion demandée).

## Sources et méthode

- [Inventaire des traitements de texte Asimov](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/word_processing/) et [productivité](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/) : présence des logiciels et disquettes, sans inférer leur codage interne.
- [Index technique CiderPress II](https://ciderpress2.com/doc-index.html) : formats documentés ; [LISA](https://ciderpress2.com/formatdoc/LisaAsm-notes.html), [Print Shop](https://ciderpress2.com/formatdoc/PrintShop-notes.html), [Magic Window](https://ciderpress2.com/formatdoc/MagicWindow-notes.html).
- [Manuel Apple Writer original](https://www.vintageapple.org/apple_ii/pdf/Minute_Manual_For_Apple_Writer_lle_1983.pdf) et [convertisseur MultiScribe public](https://github.com/nexvium/prodosfs/blob/master/util/wpf2txt).
- Registre exploitable : `data/viewer_formats.json` ; mesures locales et exclusions : [recensement du corpus](CORPUS-CENSUS.md).

Avant de choisir un lecteur, vérifier la présence de **données**, l’encodage de chaque version et un rendu dans le logiciel d’origine. Un nom de logiciel, une extension ou un type ProDOS générique n’est pas une preuve de format.

DOSREC complète le texte DOS pour les enregistrements fixes : [usage et limites](DOS-RECORDS.md). Les formats $F5 Print Shop couverts sont détaillés dans [PRINTSHOP-FORMAT.md](PRINTSHOP-FORMAT.md).

LISA 8/16 v4/v5 : [LISAV4 et ses limites](LISA4-FORMAT.md).

Le [recensement PFS séparé](PFS-WRITE.md) compte des documents réels ; il ne modifie pas les nombres historiques d’entrées de l’inventaire public ci-dessus.

PFS:Plan B00 : [PFSPLAN et ses limites](PFS-PLAN.md).

Les sept profils retenus pour la **1.0** sont désormais implémentés :
[WordPerfect, MouseWrite, Bank Street Filer, Multiplan, Movie Maker, DHGR DPC et PCS](V1-FORMATS.md).
Le tableau historique ci-dessus n’est plus une liste de sept lecteurs manquants ;
les limites de chaque profil et les suites sont dans ce rapport et le registre JSON.
