# TOTAL

Un gestionnaire de fichiers ProDOS à deux panneaux, dans l'esprit de Total
Commander, pour l'Apple IIe 128 Ko. Depuis Bitsy Bye, ouvrir le dossier
**TOTAL**, sélectionner **TOTAL.SYSTEM** puis appuyer sur **Entrée**.
Le lanceur affiche **PLEASE WAIT** pendant le chargement, puis les deux
panneaux en texte 80 colonnes : à gauche `/SCOSWAMP`, à droite
`/SCOSWAMP/DHGR`.

Chaque panneau liste un dossier : nom, type ProDOS, auxtype et taille en
octets, les dossiers d'abord (avec leur nombre de blocs), puis les fichiers,
triés par nom, taille ou type selon le mode choisi (l'étoile de l'en-tête le
dit). La ligne en inverse est la sélection ; le chemin du panneau actif est
lui aussi en inverse. La ligne de séparation porte l'espace libre du volume
du panneau actif. La ligne 22 détaille l'entrée sélectionnée (type, auxtype,
blocs, octets, date de modification) et le nombre de fichiers marqués, la
ligne 23 reçoit les messages et les questions, la dernière ligne, en inverse,
rappelle les touches.

## Touches

| Touche | Action |
|---|---|
| **Haut / Bas** | déplacer la sélection |
| **< / >** (ou **- / +**) | page précédente / suivante (18 lignes) |
| **[ / ]** | première / dernière entrée |
| **TAB** | changer de panneau |
| **=** | ouvrir le dossier du panneau actif dans l'autre panneau |
| **Espace** | marquer ou démarquer le fichier sélectionné (étoile après le nom) et descendre |
| **Entrée** ou **Droite** | ouvrir : un dossier s'ouvre ; une image `.RLE` s'affiche en DHGR plein écran (une touche pour revenir) ; un TXT se lit page par page ; un SYS se lance après confirmation ; tout autre fichier s'affiche en hexadécimal |
| **Échap** ou **Gauche** | remonter au dossier parent, la sélection revient sur le dossier quitté ; depuis la racine d'un volume, la liste des volumes |
| **/** | la liste des volumes en ligne |
| **C** | copier les entrées marquées, sinon l'entrée sélectionnée, dans le dossier de l'autre panneau ; un dossier est copié entier, sous-dossiers compris ; même nom, même type et auxtype ; refuse d'écraser un fichier existant. Une barre de progression montre le fichier en cours, son rang sur le total et les octets copiés |
| **V** | déplacer : copie, puis suppression de l'original, dossiers compris |
| **R** | renommer (nom ProDOS : une lettre, puis lettres, chiffres ou points, 15 au plus) |
| **D** | supprimer les entrées marquées, sinon l'entrée sélectionnée, après une confirmation ; un dossier est supprimé avec tout son contenu |
| **K** | créer un dossier dans le panneau actif |
| **S** | changer le tri : nom, taille décroissante, type ; les deux panneaux suivent |
| **?** | l'aide, un écran qui résume toutes les touches |
| **T** | lire le fichier sélectionné comme du texte |
| **H** | afficher le fichier sélectionné en hexadécimal |
| **X** | lancer le fichier sélectionné (SYS ou BIN) après confirmation ; TOTAL ne reprend pas la main |
| **Q** | quitter vers ProDOS après confirmation : Bitsy Bye reprend |

Dans une image, **Gauche** et **Droite** passent à l'image précédente ou
suivante du même dossier sans revenir aux panneaux : le dossier DHGR se
feuillette comme un album, et le curseur suit. Toute autre touche revient.
Dans les visionneuses de texte et d'hexadécimal : **Espace**, **Entrée** ou
**Bas** page suivante, **B** ou **Haut** page précédente, **Échap** retour aux
panneaux.
La visionneuse de texte affiche 22 lignes par page, coupe les lignes au-delà
de 80 caractères et mémorise les débuts de page rencontrés, jusqu'à 96 pages.
La visionneuse hexadécimale affiche 320 octets par page, adresse, seize
octets et leur rendu ASCII.

## Ce que TOTAL ne fait pas

- Il n'écrase jamais : pour remplacer un fichier, le supprimer d'abord.
- Il refuse de copier un dossier dans lui-même, et un arbre dont un chemin
  cumule plus de 120 entrées (la réserve des parcours récursifs).
- Il ne lance pas les programmes BASIC (BAS) : BASIC.SYSTEM n'est pas sur le
  volume, le jeu occupe sa mémoire.
- Il liste au plus 96 entrées par dossier ; au-delà, l'en-tête du panneau
  se termine par un signe plus.
- Il ne modifie aucun fichier de lui-même : seules les commandes C, V, R, D
  et K écrivent sur le disque.

## Fichiers sur le disque

| Nom ProDOS | Fonction |
|---|---|
| `TOTAL/TOTAL.SYSTEM` | Programme SYS sélectionnable dans Bitsy Bye (`loader.c`, comme DIAPO) |
| `TOTAL/TOTAL.CODE` | Le gestionnaire lui-même (`SCOSWAMP/SRC/total.c`, plus `total_mli.s` pour l'appel GET_FILE_INFO qui mesure l'espace libre) |

Les noms tiennent dans les quinze caractères de ProDOS.

## Construction et mémoire

`make -C SCOSWAMP/SRC total` construit les deux fichiers ;
`make -C SCOSWAMP/SRC hdv` les embarque. TOTAL réutilise le lanceur, la
disposition LC/MAIN, le décodeur DHGR (`hgr_loader.s`) et les bascules vidéo
(`memory_swap.c`) du jeu, sans la musique ni les catalogues de DIAPO. Le code
tourne à `$4000`, les images occupent `$2000-$3FFF` dans MAIN et AUX ; la RAM
basse `$1000-$15B5` reçoit le tampon RLE et les tampons de travail (chemins,
copie, débuts de page du texte, réserve des parcours récursifs), ce qui
laisse la fenêtre principale aux deux tables de 96 entrées. La pile C fait
768 octets et il reste environ 890 octets de tas, dont `opendir` prend un peu
plus de 500 à chaque lecture de dossier : c'est la limite qui a fixé la
taille des tables. Les deux fichiers ouverts pendant une copie utilisent les tampons
ProDOS `$0800` et `$0C00` ; TOTAL n'utilise pas MAPBSS. Le programme est
compilé avec `-Cl` (variables locales statiques) comme le jeu ; les trois
parcours récursifs (compte, copie, suppression d'un arbre) repassent leurs
variables sur la pile par `#pragma static-locals`, sans quoi le niveau
interne écrase la longueur de chemin du niveau externe. La sortie suit le QUIT ProDOS du démarrage cc65. Le lancement d'un
programme passe par `exec()` de cc65, qui charge un SYS en `$2000` ou un BIN à
son auxtype et y saute.

Les preuves POM2 headless sont dans
[VALIDATION-TOTAL](../../DOCS/VALIDATION-TOTAL/result.json) :
lancement depuis Bitsy Bye, barre inverse, espace libre, aide, images
`N000.RLE` puis `N001.RLE` (flèches) vérifiées octet à octet dans les deux
banques, tri, lecture de `TITLE`, hexadécimal de `MAP`, création d'un
dossier, copie simple et copie de deux fichiers marqués, suppression des
fichiers marqués, copie d'un dossier entier avec ses types et tailles, refus
de copier un dossier dans lui-même, copie puis suppression d'un arbre à deux
niveaux, renommage, liste des volumes, retour à Bitsy Bye, puis lancement de
`DIAPO.SYSTEM` depuis TOTAL : 39 contrôles. Le banc travaille sur
une copie du disque ; `SCOSWAMP/DHGR` n'est jamais modifié.
