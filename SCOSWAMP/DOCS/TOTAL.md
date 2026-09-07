# TOTAL

Un gestionnaire de fichiers ProDOS à deux panneaux, dans l'esprit de Total
Commander, pour l'Apple IIe 128 Ko ; son nom complet est **Apple Total
Commander 1.0** (le numéro vit dans `TOTAL_VERSION` du Makefile, repris par
le lanceur, la ligne de statut et l'aide). C'est un logiciel libre sous
licence GNU GPL v3, d'Arnaud Verhille, comme le reste du dépôt ; le lanceur
et l'aide le rappellent. Trois façons de le lancer : la touche **T** de l'écran-titre de
SCOSWAMP (la ligne « Utilitaires », en bas, propose aussi **D** pour DIAPO) ;
depuis Bitsy Bye, le dossier **TOTAL** puis **TOTAL.SYSTEM** et **Entrée** ;
ou la disquette dédiée décrite plus bas.
Le lanceur affiche un écran d'attente pendant le chargement : le titre, la
mention « ProDOS 8 only », la date et l'heure si une horloge est présente
(bit 0 de MACHID, `$BF98`) ou « No clock » sinon, puis **PLEASE WAIT**. Suivent
les deux panneaux en texte 80 colonnes : à gauche `/SCOSWAMP`, à droite
`/SCOSWAMP/DHGR` la première fois ; ensuite les deux dossiers, le tri et le
panneau actif de la session précédente, lus dans `TOTAL/TOTAL.CFG`.

Chaque panneau liste un dossier : nom, type ProDOS, auxtype et taille en
octets, les dossiers d'abord (avec leur nombre de blocs), puis les fichiers,
triés par nom, taille ou type selon le mode choisi (l'étoile de l'en-tête le
dit). La ligne en inverse est la sélection ; le chemin du panneau actif est
lui aussi en inverse. La ligne de séparation porte l'espace libre du volume
du panneau actif. La ligne 22 détaille l'entrée sélectionnée (type, auxtype,
blocs, octets, date de modification) et le nombre de fichiers marqués, la
ligne 23 reçoit les messages et les questions, la dernière ligne est la
barre de touches, façon Norton Commander : chaque touche dans un bloc
inverse, son libellé en clair juste après. Les visionneuses ont la leur,
avec le chemin et la page à gauche.

## Touches

| Touche | Action |
|---|---|
| **Haut / Bas** | déplacer la sélection |
| **< / >** (ou **- / +**) | page précédente / suivante (18 lignes) |
| **[ / ]** | première / dernière entrée |
| **TAB** | changer de panneau |
| **=** | ouvrir le dossier du panneau actif dans l'autre panneau |
| **Espace** | marquer ou démarquer le fichier sélectionné (étoile après le nom) et descendre |
| **\*** | inverser les marques du panneau |
| **'** puis une touche | sauter à l'entrée suivante dont le nom commence par cette lettre ou ce chiffre, comme dans Bitsy Bye |
| **Entrée** ou **Droite** | ouvrir : un dossier s'ouvre ; une image s'affiche plein écran, en HGR ou en DHGR selon son contenu (une touche pour revenir, la ligne de message dit le format reconnu) ; un TXT se lit page par page ; un SYS se lance après confirmation ; tout autre fichier s'affiche en hexadécimal |
| **Échap** ou **Gauche** | remonter au dossier parent, la sélection revient sur le dossier quitté ; depuis la racine d'un volume, la liste des volumes |
| **/** | la liste des volumes en ligne |
| **C** | copier les entrées marquées, sinon l'entrée sélectionnée, dans le dossier de l'autre panneau ; un dossier est copié entier, sous-dossiers compris, un sous-dossier déjà présent est complété ; même nom, même type et auxtype. Quand le fichier existe, TOTAL demande : **O** écraser, **S** passer, **A** tout écraser, **N** ne rien écraser. Une barre de progression montre le fichier en cours, son rang sur le total et les octets copiés ; le message final compte les fichiers copiés et passés |
| **V** | déplacer : copie, puis suppression de l'original, dossiers compris |
| **R** | renommer (nom ProDOS : une lettre, puis lettres, chiffres ou points, 15 au plus) |
| **D** | supprimer les entrées marquées, sinon l'entrée sélectionnée, après une confirmation ; un dossier est supprimé avec tout son contenu |
| **K** | créer un dossier dans le panneau actif |
| **S** | changer le tri : nom, taille décroissante, type ; les deux panneaux suivent |
| **M** | marquer les fichiers absents de l'autre panneau ou de taille différente : suivi de C, c'est une synchronisation |
| **A** | changer le type et l'auxtype d'un fichier, en hexadécimal |
| **L** | verrouiller ou déverrouiller ; un fichier verrouillé porte un L après son nom et refuse la suppression et le renommage |
| **?** | l'aide, un écran qui résume toutes les touches, sous le titre « Apple Total Commander » |
| **T** | lire le fichier sélectionné comme du texte |
| **H** | afficher le fichier sélectionné en hexadécimal |
| **X** | lancer le fichier sélectionné après confirmation ; TOTAL ne reprend pas la main. Un SYS est lu en `$2000`, un BIN à son auxtype s'il tient sous `$4000` |
| **E** | éditer le fichier sélectionné comme du texte ; sur un dossier ou `..`, créer un fichier texte neuf dans le dossier courant |
| **I** | afficher le fichier sélectionné comme une image, quel que soit son nom : HGR ou DHGR, brut ou compressé RLE |
| **P** | mettre en pause ou reprendre la musique Mockingboard ; Entrée sur un fichier `.MB` la lance |
| **F** | ouvrir le formateur, `TOTAL/FORMAT.SYS`, qui revient à TOTAL en sortant |
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

## Les images

À l'ouverture, TOTAL lit les huit premiers octets et la taille :

| Contenu | Format reconnu | Affichage |
|---|---|---|
| `DHRR` 1 0 0 $40 | DHGR compressé RLE (flux DHRR v1, celui du jeu), 16 384 octets décompressés | DHGR |
| `HGRR` 1 0 0 $20 | HGR compressé RLE (flux HGRR v1, celui de SPACETRIP), 8 192 octets | HGR |
| 8 192 ou 8 184 octets | page HGR brute | HGR |
| 16 384 octets | page DHGR brute, banque AUX puis MAIN (l'ordre des fichiers A2FC et du jeu) | DHGR |

Le décodeur RLE est écrit en C et sert aux deux flux ; une répétition qui
chevauche la frontière des deux banques est coupée au passage de `$4000`.
Dans un dossier, Gauche et Droite passent à l'image précédente ou suivante
parmi les fichiers qui ressemblent à une image (type FOT, ou BIN de la
taille d'une page, ou nom en `.RLE`). Un banc à part,
`validate_images.py`, monte un volume avec les quatre formats et compare la
page graphique octet à octet : 12 contrôles.

## Formater un disque

`F` (ou `TOTAL/FORMAT.SYS` depuis Bitsy Bye) lance le formateur, un
programme à part qui revient à TOTAL en sortant. Il liste les lecteurs que
ProDOS connaît, avec slot, lecteur, type (Disk II 5,25 pouces, SmartPort,
/RAM, périphérique de bloc), volume actuel s'il en a un et taille en blocs.
Le disque d'où tourne le programme est marqué IN USE et refusé. Trois
étapes : choisir un lecteur par son numéro, nommer le volume (BLANK par
défaut), puis lire l'avertissement, qui nomme le lecteur, son volume actuel
et sa taille, et taper le mot ERASE en capitales suivi d'Entrée. Rien n'est
écrit avant ce mot ; Échap annule à chaque étape.

Une disquette Disk II est formatée physiquement, piste par piste avec la
progression à l'écran : c'est le ProDOS Hyper-FORMAT de Jerry Hewett (1985,
domaine public) et Gary Desrochers (1989) tel qu'ADTPro l'a repris,
découpé en trois appels pour afficher l'avancement (`format_diskii.s`). Le
GAP1 de tête est allongé de 512 octets de synchro pour qu'une piste écrite
recouvre un tour complet, quel que soit le lecteur ou l'émulateur. Un
SmartPort qui le permet reçoit l'ordre de formatage bas niveau, le /RAM
celui de son pilote, un disque dur rien. Puis, pour tous, les structures
ProDOS sont écrites par WRITE_BLOCK (`format.c`) : l'amorce d'Hyper-FORMAT
au bloc 0, le catalogue racine aux blocs 2 à 5 avec la date de l'horloge,
la table d'allocation à partir du bloc 6. L'amorce et l'en-tête sont relus
et comparés. Le banc `validate_format.py` formate une disquette vierge dans
le Disk II émulé et le /RAM, vérifie le refus du disque en usage et d'un
mot inexact, le retour à TOTAL, la création d'un dossier sur le volume neuf
et, l'émulateur arrêté, l'image `.dsk` elle-même : 17 contrôles.

## La musique Mockingboard

Entrée sur un fichier `.MB` (flux MB1, 2 304 octets au plus) le monte en
mémoire auxiliaire par le lecteur six voix du jeu et le joue une fois, en
interruption : la navigation, les visionneuses et l'éditeur continuent
pendant la musique, et les lectures disque ne l'arrêtent pas (vérifié dans
l'émulateur : le curseur du flux avance pendant la lecture des dossiers et
le chargement d'une image). Sur une disquette 5,25 pouces, le pilote Disk II
de ProDOS coupe les interruptions pendant chaque lecture de bloc : le lecteur
se fige le temps de la lecture, puis reprend ; TOTAL n'y peut rien. P la met
en pause et la reprend, un autre `.MB` la remplace, Q et X la coupent ; une
fois le morceau fini, P le dit. La carte est cherchée dans les slots 1 à 7 à la
première demande ; sans carte, TOTAL le dit.

## L'éditeur de texte

`E` ouvre le fichier dans un éditeur plein écran de 22 lignes : flèches,
Suppr pour effacer à gauche, Ctrl-D à droite, Ctrl-A et Ctrl-E début et fin
de ligne, Ctrl-P et Ctrl-N page précédente et suivante, Ctrl-T et Ctrl-B
début et fin du texte, Entrée coupe la ligne, Tab insère quatre espaces.
La barre du bas donne le chemin, la ligne, la colonne, la taille et une
étoile si le texte a changé. Échap ouvre le menu : S sauver, X sauver et
sortir, Q quitter sans sauver (avec confirmation si le texte a changé),
Échap continuer. Le fichier garde son type et son auxtype ; le texte tient
dans la page graphique, donc 8 Ko au plus, fins de ligne CR, bit 7 ôté au
chargement. Les lignes plus longues que l'écran ne sont pas repliées.

## Ce que TOTAL ne fait pas

- Il refuse de copier un dossier dans lui-même, et un arbre dont un chemin
  cumule plus de 120 entrées (la réserve des parcours récursifs).
- Il ne lance pas les programmes BASIC (BAS) : BASIC.SYSTEM n'est pas sur le
  volume, le jeu occupe sa mémoire.
- Un dossier de plus de 139 entrées est lu par fenêtres, dans l'ordre du
  disque et sans tri : l'en-tête indique le rang de la première entrée
  suivi d'un signe plus, et le curseur passe d'une fenêtre à l'autre en
  franchissant les bords. Aucun dossier du volume n'atteint cette taille ;
  ce mode n'est pas couvert par le banc.
- Il ne modifie aucun fichier de lui-même : seules les commandes C, V, R, D
  et K écrivent sur le disque.

## Fichiers sur le disque

| Nom ProDOS | Fonction |
|---|---|
| `TOTAL/TOTAL.SYSTEM` | Programme SYS sélectionnable dans Bitsy Bye (`loader.c`, comme DIAPO) |
| `TOTAL/TOTAL.CODE` | Le gestionnaire lui-même (`SCOSWAMP/SRC/total.c`, plus `total_mli.s` pour GET_FILE_INFO et SET_FILE_INFO : espace libre, type, auxtype, verrou) |
| `TOTAL/TOTAL.CFG` | Écrit par TOTAL en quittant : les deux dossiers, le tri et le panneau actif, trois lignes de texte |
| `TOTAL/FORMAT.SYS` | Le formateur (`format.c`, `format_diskii.s`, `format_mli.s`). Pas de suffixe .SYSTEM : ProDOS amorce le premier fichier .SYSTEM du catalogue, et F passe avant S |
| `TOTAL/TOTAL.HELP` | Le texte de la page d'aide (`SCOSWAMP/TOTAL/TOTAL.HELP.TXT`), une ligne par élément : `x,y,TOUCHE,libellé`, `x,y,=TITRE` pour une section, `x,y,-texte` pour du texte en clair. Il passe par la page graphique, rien de l'aide ne reste en mémoire |

Les noms tiennent dans les quinze caractères de ProDOS.

## La disquette 5,25 pouces

`make -C SCOSWAMP/SRC floppy` produit `dist/APPLE.TOTAL.po` (ordre ProDOS)
et `dist/APPLE.TOTAL.dsk` (ordre DOS 3.3, celui d'ADTPro et de la plupart
des émulateurs), une disquette amorçable de 280 blocs, volume `/APPLE.TOTAL` :

| Fichier | Contenu |
|---|---|
| `PRODOS` | ProDOS 8 2.4.3, la dernière version stable (identique à celle du volume du jeu, vérifiée contre l'image officielle du dépôt ProDOS-8) |
| `TOTAL.SYSTEM` | le lanceur, seul programme `.SYSTEM` : la disquette démarre directement dans TOTAL. Compilé avec `NO_CHDIR`, il se fie au préfixe du volume amorcé |
| `TOTAL/TOTAL.CODE`, `TOTAL/TOTAL.HELP` | le même binaire et la même aide que sur le volume du jeu ; `TOTAL.CFG` sera écrit à côté |
| `TEST/` | de quoi essayer : `HGR.RAW` (page HGR brute de SPACETRIP), `HGR.RLE` (la même en HGRR), `DHGR.RLE` (une image du jeu en DHRR), `WELCOME.MB` (une musique) et `README`. Une DHGR brute de 16 Ko aurait pris 33 des blocs restants |

Il reste 88 blocs libres. Au démarrage, le panneau gauche montre la racine
de la disquette et le panneau droit la liste des volumes, faute de dossier
`DHGR`. `build_prodos_volume` taille ses volumes au contenu ;
`make_floppy.py` porte ensuite le compte de blocs à 280, libère les blocs
ajoutés dans la table d'allocation et écrit les deux ordres de secteurs. Le
banc a démarré cette image comme disque dur dans POM2 : TOTAL s'ouvre sur
`/APPLE.TOTAL`, Q rend la main à Bitsy Bye sur ce volume. Une version 2.5
alpha 8 de ProDOS existe ; elle n'est pas retenue, faute d'être publiée.

## Construction et mémoire

`make -C SCOSWAMP/SRC total` construit les deux fichiers ;
`make -C SCOSWAMP/SRC hdv` les embarque. TOTAL réutilise le lanceur, la
disposition LC/MAIN, le décodeur DHGR (`hgr_loader.s`) et les bascules vidéo
(`memory_swap.c`) du jeu, sans la musique ni les catalogues de DIAPO. Le code
tourne à `$4000`. Les deux tables de 140 entrées occupent la page graphique
MAIN `$2000-$3FFF`, libre tant qu'aucune image n'est affichée : une image
la recouvre, et les deux panneaux sont relus au retour, marques conservées.
La RAM basse `$1000-$1EF9` reçoit le tampon RLE et les tampons de travail
(chemins, copie, débuts de page du texte, réserve des parcours récursifs).
Les visionneuses, les saisies et le fichier de préférences vivent dans la
carte langage, `$D400-$DF56` en banque 2, copiés par `crt0.s` comme pour le
jeu ; avant de lancer un programme, TOTAL remet la ROM en lecture. La pile C
fait 512 octets ; le lecteur Mockingboard (1,5 Ko) a pris presque tout le
reste, il ne demeure que quelques octets libres. Les programmes lancés par
X et F le sont par un talon recopié en page `$0300` (`chain.s`), qui lit le
fichier entier à son adresse et y saute : aucune limite de taille, et
FORMAT.SYS revient à TOTAL par le même talon. TOTAL n'utilise plus ni
`opendir` ni `malloc` : les dossiers sont lus comme des fichiers, bloc par
bloc, dans le tampon de copie, ce qui est aussi plus rapide. Pour loger
l'éditeur et le visionneur, il a aussi rendu `hgr_loader.s` (le décodeur C
le remplace, par tranches `memset`/`memcpy` jusqu'à la frontière des
banques), `qsort` (un tri par insertion) et `exec()` (un lanceur de
quelques lignes) ; les messages répétés sont partagés et l'aide vit sur le
disque. Les deux fichiers ouverts pendant une copie utilisent les tampons
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
fichiers marqués, question d'écrasement (passer puis écraser), marquage des
différences et inversion, saut par lettre, verrou refusant la suppression,
changement de type et d'auxtype, copie d'un dossier entier avec ses types et
tailles, refus de copier un dossier dans lui-même, copie puis suppression
d'un arbre à deux niveaux, renommage, liste des volumes avec slot et espace
libre, retour à Bitsy Bye, restauration des panneaux par `TOTAL.CFG`, puis
lancement de `DIAPO.SYSTEM` depuis TOTAL : 50 contrôles. Le banc travaille sur
une copie du disque ; `SCOSWAMP/DHGR` n'est jamais modifié.
