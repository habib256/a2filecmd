# A2 File Cmd — ce qui reste à faire

`🟠 haute · 🟡 moyenne · 🟢 basse`, effort indicatif en *italique*, fichier en
`backticks`. Les mesures datent du 2026-09-08, sur la 0.6.1.

## La place disponible

| Zone | État mesuré |
| --- | --- |
| Fenêtre principale `$4000`-plancher de la pile | ~4 100 octets libres (les commandes sont passées en surcouches) |
| Fenêtre de surcouche `$1B00-$1FFF` (1 280 octets) | `IMAGE.PLG` 1 213, `HELP.PLG` 974, `ATTR.PLG` 1 088, `DELETE.PLG` 807, `HEX.PLG` 826, `RUN.PLG` 719, `TEXT.PLG` 644, `MUSIC.PLG` 585 |
| Grandes surcouches `$1B00-$3FFF` | `EDIT.PLG` 3 058, `MENU.PLG` 1 070, `DISKIMG.PLG` 5 896 |
| RAM basse `$1000-$1AFF` (BSS) | ~40 octets libres |
| Carte langage `$D400-$DFFF` | ~1 750 octets libres |
| Pile C | 86 octets utilisés sur 256 réservés |
| Disquette | 18 blocs libres sur 280 |

## Fait le 2026-09-08 — finir l'étude A2Command

La restructuration en surcouches a rendu **près de 3,5 Ko** à la fenêtre
principale (`$4000-$ADC2` au lieu de `$4000-$BADF`) : l'éditeur, la musique,
le lanceur, les attributs, la suppression, le menu et les images disque ont
quitté le résident pour des `A2FILE/*.PLG`. Ce qui a été livré, dans l'ordre
du TODO précédent :

- ✅ **Les images disque** (`DISKIMG.PLG`, `W`) : écrire un `.PO`/`.DSK`/`.DO`/
  `.2MG` sur une disquette, lire une disquette dans une image neuve, copier
  disquette à disquette (un seul lecteur : on échange les disquettes à chaque
  passe). Blocs par READ_BLOCK/WRITE_BLOCK, tampon en RAM principale
  (`$3400`) et auxiliaire (`$2000`, d'où `/RAM` refait). Le mot `ERASE`
  protège toute écriture. Le seul terrain où A2Command gagnait est comblé.
- ✅ **La convention « grande surcouche »** : l'octet de drapeaux de
  l'en-tête (`OVERLAY_BIG`, `overlay.s`/`a2fc_plugin.h`) déclare qu'une
  surcouche prend aussi `$2000-$3FFF` ; `overlay_run` met les marques de
  côté, appelle le point d'entrée, relit les deux panneaux au retour.
  L'éditeur, le menu et les images disque en sont.
- ✅ **La table de services** (`struct A2fcApi`, `a2fc_plugin.h`) : l'ABI
  stable qu'une surcouche d'un tiers reçoit à son point d'entrée (`fopen`,
  `message`, `confirm`, `prompt`, `dir_open`/`dir_next`, `read_panel`,
  `mli`...). Le noyau la passe à toute surcouche marquée `PLUGIN_MAGIC`.
- ✅ **Un menu des surcouches** (`!`, `MENU.PLG`) : la liste d'`A2FILE/*.PLG`
  avec la description d'une ligne de chaque en-tête, lancée sur la sélection.
  Une commande de plus ne demande plus ni touche ni recompilation.
- ✅ **Les chiffres comme touches de fonction** : `1`..`0` valent les dix
  boutons de la barre, dans l'ordre.
- ✅ **Tout marquer / tout démarquer** (`Ctrl-T` / `Ctrl-N`) et **relire les
  panneaux** (`Ctrl-R`).

## Fait le 2026-09-08 — l'image disque comme dossier

- ✅ **Une image disque comme dossier** (`IMGFS.PLG`) : Entrée sur un
  `.PO`/`.2MG`/`.DSK`/`.DO` l'ouvre en lecture comme un dossier, on y navigue
  (sous-dossiers, `..`, sortie), et `C` extrait les fichiers marqués vers le
  dossier ProDOS de l'autre panneau. La lecture des blocs (`img_read_block`,
  résident, avec la permutation DOS 3.3 pour un `.DSK` et l'en-tête d'un
  `.2MG`) réutilise le lecteur de répertoire ProDOS bloc par bloc ; les
  champs `fs`/`img_len`/`dir_key` de `struct Panel` portent l'état. Les
  fichiers germe et plant (≤ 128 Ko) sont extraits ; les rares fichiers
  arborescents sont refusés. Le noyau ne fait que naviguer et lister ; la
  lecture des fichiers (germe/plant, index) est la surcouche `IMGFS.PLG`,
  lancée par `C`. A2Command ne sait pas faire ça.

## Fait le 2026-09-08 — DOS 3.3, image et vrai disque

- ✅ **DOS 3.3** : le catalogue d'une disquette DOS 3.3 et la copie de ses
  fichiers vers ProDOS, aussi bien depuis une image (`.DSK`/`.DO`/`.2MG`)
  que depuis un **vrai disque** dans un lecteur. La lecture des secteurs
  (`dos_read_sector`) réutilise READ_BLOCK sur le demi-bloc ProDOS
  correspondant (la table `DOS_TS`, l'inverse de `SECTORS`/`po2dsk.py`) pour
  un disque physique, `fseek` pour une image ; la VTOC en piste 17, le
  catalogue chaîné, les listes T/S. Un disque DOS 3.3 sans volume ProDOS
  apparaît dans la liste des volumes (`/`), reconnu à sa VTOC ; Entrée
  l'ouvre comme un dossier plat, `C` extrait les fichiers (l'en-tête DOS d'un
  Applesoft, Integer ou binaire est ôté). L'extraction est la surcouche
  `DOS33.PLG`, le catalogue est résident. Le banc lit une image DOS 3.3 et
  en extrait un fichier, comparé octet à octet.

## Fait le 2026-09-08 — le retour du BASIC, fiable

- ✅ **Revenir d'Applesoft** (`-A2FILE.SYSTEM`) sans figer la machine. Une
  version antérieure restait sur un écran noir juste après le passage en 80
  colonnes, sur vrai IIe comme au banc où A2FC rouvrait sur la liste des
  volumes. Deux causes, deux corrections :
  - **La pile C.** `crt0`, voyant `BASIC.SYSTEM` résident à la relance,
    posait la pile sur son `HIMEM` (~`$9600`) — au milieu du code qu'on lit
    jusqu'à `$BE40`, que la pile écrasait en grandissant. `src/crt0.s` (A2FC)
    et le nouveau `src/crt0_loader.s` (le lanceur) placent toujours la pile
    en `$BF00` et quittent par le répartiteur ProDOS. Le banc vérifie que le
    pointeur de pile revient bien à `$BEFC`, comme à froid.
  - **Le préfixe.** `BASIC.SYSTEM` vide le préfixe ProDOS en lançant un SYS.
    Le lanceur le refait (`src/loader_mli.s` : `ON_LINE` sur `$BF30` puis
    `SET_PREFIX` en `/VOLUME`) avant de sauter dans A2FC, qui rouvre ses
    panneaux et relit `A2FILE.CFG` comme au démarrage à froid. Le banc exige
    le retour sur les panneaux, pas sur la liste des volumes.

## Fait le 2026-09-08 — la surcouche d'exemple d'un tiers

- ✅ **Une surcouche d'exemple pour un tiers** (`sdk/`), compilée HORS de
  l'arbre avec le seul `src/a2fc_plugin.h`, pour prouver que l'ABI tient et
  donner un modèle. `sdk/hello.c` porte son en-tête `struct Overlay` signé
  `PLUGIN_MAGIC` dans le segment `OVLHDR` (en tête, `$1B00`) et un point
  d'entrée `plugin_entry(const struct A2fcApi*)` qui ne touche au programme
  que par la table de services : il lit l'entrée sélectionnée et en écrit le
  nom, le type et le chemin en ligne de message. `sdk/build.sh` le lie avec
  `ld65` sur `sdk/plugin.cfg` et `apple2enh.lib`, **sans** crt0 ni
  `A2FILE.CODE` (`make example` → `build/HELLO.PLG`, 593 octets). `bench/`
  `plugin.py` le construit, le pose sous `A2FILE/HELLO.PLG` sur une disquette,
  l'ouvre par `!` et vérifie qu'il paraît dans le menu (décrit par son
  en-tête) puis qu'il tourne (6 contrôles). `sdk/README.md` explique tout.

## Ce qui reste

- 🟡 **//c et IIgs** : A2Command tourne dessus, A2FC ne l'a jamais essayé.
  Rien ne suppose un slot (souris cherchée par signature, Mockingboard par
  sonde), mais le //c n'a pas de Mockingboard et son `/RAM` est le même. Le
  banc sait choisir la machine (`Pom2(..., preset=...)`, `bench/pom2.py`) et
  `pom2_playtest` a maintenant un vrai `--preset iic` (2026-09-08) : sur un
  //c, le lecteur intégré EST le Disk II du slot 6 — POM2 amorce bien
  `A2FILECMD.po` depuis ce slot, par le scan de la ROM comme par `--boot 6`
  (vérifié : les panneaux arrivent sur les deux presets). Le disque dur du
  banc est servi par le firmware SmartPort du //c (slot 5, unité 0 sur le
  port arrière) et ProDOS le liste (`DEVLST` : `$5B`) ; le //c a toujours
  son Disk II branché, sans quoi le port arrière ne voit pas les lignes de
  phase et le firmware attend à `$CC2C`. Reste à faire tourner `run.py` et
  `memory.py` sous `preset='iic'` et à regarder ce qui casse (pas de
  Mockingboard : la fanfare doit se taire proprement). Le IIgs n'a pas de
  profil dans POM2 : cette moitié se fera avec un autre émulateur. *½ jour.*
- 🟢 **La musique en surcouche résidente le temps de la lecture** : le
  chargement d'un `.MB` est déjà une surcouche (`MUSIC.PLG`), mais le pilote
  AY reste résident. Le rendre entièrement en surcouche demanderait qu'elle
  survive à la navigation, ce que la fenêtre unique interdit. *À laisser.*
- 🟢 **Lister un BAS** (`BASLIST.PLG`), **chercher un texte** (`SEARCH.PLG`),
  **comparer deux fichiers** octet à octet : chacune est maintenant une
  surcouche de plus sur le modèle de `sdk/hello.c` (l'ABI et le SDK sont
  prouvés). Le seul coût résident est un aiguillage — que la table de
  reconnaissance ci-dessous supprimerait. *1 à 2 jours les trois.*
- 🟢 **Une table de reconnaissance** (type, auxtype, suffixe, en-tête → nom
  de surcouche) à la place de `looks_like_image` et de l'aiguillage
  d'`open_selected`, pour qu'un format de plus ne coûte qu'une ligne.

## Les surcouches, telles qu'elles sont

Le segment `LOWEXE` est la **fenêtre de surcouche**. Une surcouche est un
`A2FILE/NOM.PLG`, un BIN lu en `$1B00` à la demande (`load_overlay`), reconnu
par l'en-tête `struct Overlay` (`a2fc_plugin.h`) : la signature (l'adresse de
`main`, ou `PLUGIN_MAGIC` pour un tiers), un octet de drapeaux, l'adresse du
point d'entrée, une description d'une ligne. Le code d'une surcouche est dans
son segment `NOM`, ses chaînes dans `NOMRO` : les deux vont dans le même
fichier, code d'abord, pour que les mots à zéro que cc65 pose en tête d'une
`.proc` (`-Cl`) n'atterrissent pas sur le point d'entrée. Treize surcouches
du programme : `IMAGE`, `TEXT`, `HEX`, `HELP`, `DELETE`, `MUSIC`, `RUN`,
`ATTR`, `IMGFS`, `DOS33` (petites, `$1B00-$1FFF`) ; `EDIT`, `MENU`, `DISKIMG`
(grandes, jusqu'à `$3FFF`). `check_layout.py` vérifie que chacune tient sous
son plafond.

Une surcouche d'un TIERS suit la même convention mais signe `PLUGIN_MAGIC`,
se lie hors de l'arbre (`sdk/`, sans crt0 ni `A2FILE.CODE`) et ne touche au
programme que par la table de services `struct A2fcApi` — voir `sdk/README.md`.
