# A2 File Cmd — ce qui reste à faire

`🟠 haute · 🟡 moyenne · 🟢 basse`, effort indicatif en *italique*, fichier en
`backticks`. Les mesures datent du 2026-09-07, sur la 0.5.

## La place disponible

| Zone | État mesuré |
| --- | --- |
| Fenêtre principale `$4000`-plancher de la pile | ~1 100 octets libres, souris comprise |
| Fenêtre de surcouche `$1B00-$1FFF` (1 280 octets) | `IMAGE.PLG` 1 144, `HELP.PLG` 920, `DELETE.PLG` 750, `HEX.PLG` 699, `TEXT.PLG` 579 |
| RAM basse `$1000-$1AFF` (BSS) | ~250 octets libres |
| Carte langage `$D400-$DFFF` | ~1 300 octets libres |
| Pile C | 86 octets utilisés sur 256 réservés |
| Disquette | 46 blocs libres sur 280 |

## Étude 2026-09-07 — faire mieux qu'A2Command

A2Command (Payton Byrd, 2011-2013, CodePlex, v1.1 « stable » du 19 août
2013, dérivé de CBM-Command) est le seul autre gestionnaire à deux panneaux
de l'Apple II. Ce que sa page annonce : deux panneaux, visionneuse de texte,
copie et suppression en lot, renommage, dossiers (créer, supprimer,
parcourir), **écriture d'une image disque sur une disquette, d'une
disquette dans une image, copie disquette à disquette** ; touches à la
Norton, `1` aide, `2` quitter, `5` copier, `6` renommer, `7`/`M` dossier,
`8` supprimer, `9`/`RET` entrer, `0`/`ESC` sortir, `D` et `OA-D` choix du
lecteur par panneau, `A` tout sélectionner, `S` tout désélectionner,
`ESPACE` sélectionner, crochets pour les pages, `W` écrire une image, `C`
créer une image, `O` copier un disque ; machines : //e 65C02 80 colonnes
**avec carte souris exigée**, //c, //c+, IIgs ROM01/03.

Ce que A2FC a déjà en plus : hexa, images HGR/DHGR, musique, éditeur, tri,
verrou, type et auxtype, marquage des différences, formateur, lanceur SYS/
BIN/BAS, souris facultative, et surtout **les surcouches** : un module lu à
la demande en `$1B00`, lié au programme, qui ne coûte rien au résident.
C'est par là qu'on dépasse A2Command sans toucher au noyau. Par ordre :

- 🟠 **Les images disque** (`DISKIMG.PLG`) : écrire un `.PO`/`.DSK`/`.2MG`
  sur une disquette, lire une disquette dans une image, copier disquette à
  disquette — le seul terrain où A2Command gagne. Tout existe déjà : le
  formatage physique de `format_diskii.s`, READ_BLOCK/WRITE_BLOCK de
  `format.c`, l'ordre des secteurs de `po2dsk.py`. Le tampon : la page
  graphique `$2000-$3FFF`, 16 blocs par passe, les panneaux relus après
  comme au retour d'une image. Demande la convention de **« grande
  surcouche »** ci-dessous. *2 à 3 jours.*
- 🟠 **Une image disque comme dossier** (`IMGFS.PLG`) : Entrée sur un
  `.PO`/`.2MG`/`.DSK` l'ouvre en lecture comme un dossier, et `C` en
  extrait les fichiers. `dir_open`/`dir_next` lisent déjà un répertoire
  bloc par bloc : il suffit d'un `read_block` qui fait un `fseek` dans le
  fichier (et la permutation de secteurs pour un `.DSK`). A2Command ne sait
  pas faire ça. *2 jours.*
- 🟡 **DOS 3.3** (`DOS33.PLG`) : le catalogue d'une disquette DOS 3.3 et la
  copie de ses fichiers vers ProDOS. Les secteurs physiques sont les mêmes :
  READ_BLOCK sur le pilote Disk II, la table `SECTORS` de `po2dsk.py` à
  l'envers, VTOC en piste 17, et les fichiers T/A/I/B se relisent par leurs
  listes de secteurs. *2 jours.*
- 🟡 **La convention « grande surcouche »** : une surcouche déclare (un
  octet après l'adresse de `main`) qu'elle prend aussi `$2000-$3FFF` ; le
  noyau met les marques de côté, l'appelle, relit les deux panneaux au
  retour. C'est ce que fait déjà `view_image` à la main. Et la **table de
  services** en tête de fenêtre (`fopen`, `view_getc`, `message`,
  `confirm`, `prompt`, `progress_bar`, `dir_open`/`dir_next`, `read_panel`)
  pour qu'une surcouche d'un tiers survive à une reconstruction : c'est
  l'ABI stable déjà notée plus bas, elle devient prioritaire dès qu'on
  écrit trois surcouches de plus. *1 jour.*
- 🟡 **Un menu des surcouches** (`!`) : la liste d'`A2FILE/*.PLG`, chacune
  lancée sur la sélection — une commande de plus ne demande plus de touche
  ni de recompilation. *½ journée, une fois l'ABI en place.*
- 🟡 **//c et IIgs** : A2Command tourne dessus, A2FC ne l'a jamais essayé.
  Rien ne suppose un slot (souris cherchée par signature, Mockingboard par
  sonde), mais le //c n'a pas de Mockingboard et son /RAM est le même ;
  vérifier dans POM2 avec les presets `iic` et `iigs` s'ils existent, puis
  l'écrire dans les prérequis. *1 jour.*
- 🟢 **Les chiffres comme touches de fonction** : `1`..`0` valent les dix
  boutons de la barre, dans l'ordre (`bar_key` sait déjà les compter) ; c'est
  l'habitude Norton et A2Command. *40 octets.*
- 🟢 **Tout marquer / tout démarquer** (`Ctrl-T` / `Ctrl-U`, `*` inverse
  déjà) et **relire les panneaux** sur demande (`Ctrl-R`) : disquette
  changée, /RAM refait. *60 octets.*
- 🟢 **Lister un BAS** (`BASLIST.PLG`) : `T` sur un programme Applesoft le
  détokenise (la table des 107 mots, ~700 octets) au lieu de l'afficher en
  hexa. *1 jour.*
- 🟢 **Chercher un texte** dans les fichiers du panneau (`SEARCH.PLG`), et
  **comparer deux fichiers** octet à octet (`M` ne compare que les tailles).
  *1 jour les deux.*

## Fait le 2026-09-07 — les surcouches et la souris

Le segment `LOWEXE` est devenu la **fenêtre de surcouche** : le chargeur et
le décodeur d'images (`A2FILE/IMAGE.PLG`) et la page d'aide (`HELP.PLG`)
sont liés avec le programme mais écrits à part, lus en `$1B00` à la demande
(`overlay()`), reconnus à l'adresse de `main` en tête ; puis les visionneuses
de texte et d'hexadécimal (`TEXT.PLG`, `HEX.PLG`, sorties de la carte
langage) et la suppression (`DELETE.PLG`) ont suivi. Près d'un kilo-octet
rendu à la fenêtre principale, qui a payé **la souris** (`mouse.s`, mode
passif, pointeur MouseText, clic = sélection, second clic = ouvrir, barre de
touches cliquable, tri et dossier parent par l'en-tête). Reste de l'idée :

- 🟡 **La musique en surcouche** (`play_music`, ~390 octets, le pilote AY
  restant résident) : elle joue pendant qu'on navigue, la surcouche devrait
  rester en place tant que `P` n'a pas arrêté la lecture, et une image
  demandée entre-temps devrait attendre ou couper la musique. *1 jour.*
- 🟢 **Une table de reconnaissance** (type, auxtype, suffixe, en-tête → nom
  de surcouche) à la place de `looks_like_image` et de l'aiguillage
  d'`open_selected`, pour qu'un format de plus ne coûte qu'une ligne.
- 🟢 **Une ABI stable** (table de services en tête de la fenêtre) pour
  qu'une surcouche d'un tiers survive à une reconstruction ; aujourd'hui
  `.CODE` et `.PLG` vont par ensemble.
- 🟢 **La souris dans les visionneuses** : un clic pour tourner la page ou
  revenir, et le double-clic à la durée plutôt qu'au second clic sur la
  sélection.

## Étude 2026-09-07 — la souris (réalisée le soir même, voir ci-dessus)

**Verdict : faisable, ~0,7 Ko de code, et il faut d'abord ouvrir la place.**
🟡 moyenne · *2 à 3 jours* — mesuré : 868 octets, la place ouverte par les
surcouches.

**Le matériel.** Carte Apple Mouse II (341-0270). Ne jamais supposer un
slot : POM2 la met en **slot 2** par défaut (`mouseaw`, la carte AppleWin
haut niveau ; la carte MC68705 `mouse` existe aussi) et le **slot 4 est
occupé par la Mockingboard**. Balayage des slots 7→1 sur la signature du
firmware (`$Cn05=$38`, `$Cn07=$18`, `$Cn0B=$01`, `$Cn0C=$20`, `$CnFB=$D6`).
Les points d'entrée se lisent dans la table d'offsets `$Cn12..$Cn1B`
(SETMOUSE, SERVEMOUSE, READMOUSE, CLEARMOUSE, POSMOUSE, CLAMPMOUSE,
HOMEMOUSE, INITMOUSE) ; l'appel se fait `SEI`, ROM en lecture, `X=$n0` et
`Y=$Cn` comme le firmware l'exige, et il faut relâcher `$C800` par `$CFFF`
après coup — le firmware 80 colonnes du //e s'en sert aussi.

**Mode passif, aucune interruption.** `SETMOUSE` mode `$01` : la carte
compte toute seule, `READMOUSE` à chaque tour de boucle suffit. On évite
`ALLOC_INTERRUPT` (ProDOS n'a que quatre entrées et la musique en prend
une) et tout risque dans les temps critiques du Disk II. `CLAMPMOUSE` à
0..79 et 0..23 rend la position directement en cases de l'écran 80
colonnes : aucun calcul. L'état arrive dans les *screen holes* de la page
texte principale (`$0478+s`, `$0578+s`, `$04F8+s`, `$05F8+s`, statut
`$0778+s`).

**Ce que ça change dans le programme.** La boucle principale attend sur `cgetc()`,
bloquant : il faut une attente `kbhit()` + scrutation qui sorte sur touche
ou sur clic, dans la boucle principale et dans les visionneuses. Le curseur
est un caractère inversé (on est en texte, pas de sprite) : un octet
sauvegardé, réécrit à chaque déplacement. Actions : clic sur une ligne =
sélection, et changement de panneau actif si c'est l'autre ; double-clic =
Entrée ; clic sur la barre de touches ligne 23 = la commande ; clic sur la
ligne de titre = tri.

**Le prix.** Détection et init ~80 o, scrutation et curseur ~200 o,
cartographie des clics ~300 à 500 o : **0,6 à 0,8 Ko**. La place existe
désormais : le segment `LOWEXE` (`$1C00-$1FFF`, ouvert le 2026-09-07 pour
loger le décodeur d'images et payer le reformatage de `/RAM`) garde **~350
octets libres**, et la fenêtre principale **~1 100** sous le plancher de la
pile. De quoi tenir sans rien sacrifier — la carte langage, elle, reste
pleine à 26 octets près.

**Le banc.** POM2 émule les deux cartes et son API AI-control a un point
`/mouse` (déplacements et boutons, deltas accumulés) : un
`validate_mouse.py` cliquera comme les autres bancs frappent des touches.

**Étapes.** (1) `mouse.s` : détection, init, clamp, `READMOUSE`, curseur
texte, un `M` dans la ligne de statut quand la souris est vue ;
(2) scrutation dans la boucle principale ; (3) clic = sélection,
double-clic = ouvrir ; (4) barre de touches cliquable ; (5) le banc. Tout doit rester intégralement au
clavier : la majorité des machines n'a pas de souris.

---
