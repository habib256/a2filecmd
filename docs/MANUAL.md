# Le manuel d'A2 File Cmd

Un gestionnaire de fichiers ProDOS à deux panneaux, dans l'esprit de Total
Commander, pour l'Apple IIe 128 Ko ; à l'écran il se nomme **A2 FILE CMD
0.6** (le numéro vit dans `A2FC_VERSION` du Makefile, repris par le lanceur,
la ligne de statut et l'aide). C'est un logiciel libre sous licence GNU GPL
v3, d'Arnaud Verhille ; le lanceur et l'aide le rappellent. Deux façons de le
lancer : amorcer la disquette `/A2FILECMD`, ou choisir `A2FILE.SYSTEM`
depuis un sélecteur comme Bitsy Bye.

Le lanceur affiche un écran d'attente pendant le chargement : le titre, la
mention « ProDOS 8 only », la date et l'heure si une horloge est présente
(bit 0 de MACHID, `$BF98`) ou « No clock » sinon, puis **PLEASE WAIT**. Suivent
les deux panneaux en texte 80 colonnes : à gauche le volume amorcé, à droite
son dossier `DEMO` la première fois ; ensuite les deux dossiers, le tri et le
panneau actif de la session précédente, lus dans `A2FILE/A2FILE.CFG`.

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
| **Gauche / Droite** (ou **< / >**, **- / +**) | page précédente / suivante (18 lignes) : c'est le déplacement rapide dans un long dossier, le clavier de l'Apple IIe n'ayant pas de PgUp |
| **[ / ]** | première / dernière entrée |
| **TAB** | changer de panneau |
| **=** | ouvrir le dossier du panneau actif dans l'autre panneau |
| **Espace** | marquer ou démarquer le fichier sélectionné (étoile après le nom) et descendre |
| **\*** | inverser les marques du panneau |
| **'** puis une touche | sauter à l'entrée suivante dont le nom commence par cette lettre ou ce chiffre, comme dans Bitsy Bye |
| **Entrée** | ouvrir : un dossier s'ouvre ; une image disque `.PO`/`.DSK`/`.2MG`, ProDOS ou DOS 3.3, s'ouvre en lecture comme un dossier (voir « Une image disque comme dossier ») ; une image graphique s'affiche plein écran, en HGR ou en DHGR selon son contenu (une touche pour revenir, la ligne de message dit le format reconnu) ; un TXT se lit page par page ; un SYS ou un BAS se lance après confirmation ; tout autre fichier s'affiche en hexadécimal |
| **Échap** | remonter au dossier parent, la sélection revient sur le dossier quitté ; depuis la racine d'un volume, la liste des volumes |
| **/** | la liste des volumes en ligne |
| **C** | copier les entrées marquées, sinon l'entrée sélectionnée, dans le dossier de l'autre panneau ; un dossier est copié entier, sous-dossiers compris, un sous-dossier déjà présent est complété ; même nom, même type et auxtype. Quand le fichier existe, A2FC demande : **O** écraser, **S** passer, **A** tout écraser, **N** ne rien écraser. Une barre de progression montre le fichier en cours, son rang sur le total et les octets copiés ; le message final compte les fichiers copiés et passés |
| **V** | déplacer : copie, puis suppression de l'original, dossiers compris |
| **R** | renommer (nom ProDOS : une lettre, puis lettres, chiffres ou points, 15 au plus) |
| **D** | supprimer les entrées marquées, sinon l'entrée sélectionnée, après une confirmation ; un dossier est supprimé avec tout son contenu |
| **K** | créer un dossier dans le panneau actif |
| **S** | changer le tri : nom, taille décroissante, type ; les deux panneaux suivent |
| **M** | marquer les fichiers absents de l'autre panneau ou de taille différente : suivi de C, c'est une synchronisation |
| **A** | changer le type et l'auxtype d'un fichier, en hexadécimal |
| **L** | verrouiller ou déverrouiller ; un fichier verrouillé porte un L après son nom et refuse la suppression et le renommage |
| **?** | l'aide, un écran qui résume toutes les touches, sous le titre « A2 File Cmd » |
| **T** | lire le fichier sélectionné comme du texte |
| **H** | afficher le fichier sélectionné en hexadécimal |
| **X** | lancer le fichier sélectionné après confirmation ; A2FC ne reprend pas la main. Un SYS est lu en `$2000`, un BIN à son auxtype, entre `$0800` et `$BAFF` (le talon garde son tampon ProDOS en `$BB00`). Un BAS (Applesoft) passe par `BASIC.SYSTEM`, voir ci-dessous |
| **E** | éditer le fichier sélectionné comme du texte ; sur un dossier ou `..`, créer un fichier texte neuf dans le dossier courant |
| **I** | afficher le fichier sélectionné comme une image, quel que soit son nom : HGR ou DHGR, brut ou compressé RLE |
| **P** | mettre en pause ou reprendre la musique Mockingboard ; Entrée sur un fichier `.MB` la lance |
| **W** | les images disque : écrire un `.PO`/`.DSK`/`.2MG` sur une disquette, lire une disquette dans une image neuve, copier une disquette sur une autre (voir plus bas) |
| **!** | le menu des surcouches : la liste d'`A2FILE/*.PLG` avec leur description, chacune lancée sur la sélection |
| **F** | ouvrir le formateur, `A2FILE/FORMAT.SYS`, qui revient à A2FC en sortant |
| **1** … **0** | les dix boutons de la barre de touches, dans l'ordre, comme Norton Commander et A2Command |
| **Ctrl-T** / **Ctrl-N** | tout marquer / tout démarquer ; **Ctrl-R** relit les deux panneaux (disquette changée, `/RAM` refait) |
| **Q** | quitter vers ProDOS après confirmation : Bitsy Bye reprend |

Dans une image, **Gauche** et **Droite** passent à l'image précédente ou
suivante du même dossier sans revenir aux panneaux : le dossier DHGR se
feuillette comme un album, et le curseur suit. Une flèche sans voisine de
son côté ne fait rien, l'image reste. Toute autre touche revient.

## La souris

Une carte AppleMouse II, dans n'importe quel slot, est reconnue au
démarrage (`Mouse` apparaît dans la ligne de séparation) et le clavier reste
entier : rien n'exige la souris. Le pointeur, une flèche MouseText, ne
paraît qu'une fois la souris bougée, et suit ensuite la souris sur les
panneaux. Un clic sur une ligne la sélectionne — le panneau devient actif
s'il ne l'était pas — et un second clic sur la ligne sélectionnée l'ouvre,
comme Entrée. Un clic sur la ligne des colonnes d'un panneau change le tri,
un clic sur son chemin remonte au dossier parent. Un clic sur un bouton de
la barre de touches vaut la touche. Dans les visionneuses, l'éditeur et les
questions, seul le clavier répond. La carte est lue en mode passif, sans
interruption : la Mockingboard garde les siennes.
Dans les visionneuses de texte et d'hexadécimal : **Espace**, **Entrée** ou
**Bas** page suivante, **B** ou **Haut** page précédente, **Échap** retour aux
panneaux.
La visionneuse de texte affiche 22 lignes par page, coupe les lignes au-delà
de 80 caractères et mémorise les débuts de page rencontrés, jusqu'à 96 pages.
La visionneuse hexadécimale affiche 320 octets par page, adresse, seize
octets et leur rendu ASCII.

## Les images

À l'ouverture, A2FC lit les huit premiers octets et la taille :

| Contenu | Format reconnu | Affichage |
|---|---|---|
| `DHRR` 1 0 0 $40 | DHGR compressé RLE (flux DHRR v1), 16 384 octets décompressés | DHGR |
| `HGRR` 1 0 0 $20 | HGR compressé RLE (flux HGRR v1), 8 192 octets | HGR |
| 8 192 ou 8 184 octets | page HGR brute | HGR |
| 16 384 octets | page DHGR brute, banque AUX puis MAIN (l'ordre des fichiers A2FC) | DHGR |

Le décodeur RLE est écrit en C et sert aux deux flux ; une répétition qui
chevauche la frontière des deux banques est coupée au passage de `$4000`.

**Le chargement ne se voit jamais.** Écrire dans `$2000-$3FFF`, c'est écrire
dans la page affichée : tant que le décodeur travaille, l'écran reste au
texte — les panneaux, intacts en `$400-$7FF` — et l'image ne s'allume qu'une
fois complète. Sans cela, feuilleter un dossier montrait l'image précédente
se faire recouvrir par la table d'entrées relue, puis la nouvelle se peindre
bande par bande, plan AUX avant plan MAIN. `load_image` remet aussi le
routage mémoire sur la banque principale avant toute lecture : le firmware 80
colonnes laisse `80STORE` armé, et avec `HIRES` encore actif d'une image
précédente une page HGR brute serait partie en banque auxiliaire.

**Une image DHGR détruit le contenu de `/RAM`, alors A2FC le refait à
neuf.** Le disque virtuel de ProDOS vit en RAM auxiliaire, et la moitié
auxiliaire d'une page DHGR (`$2000-$3FFF` en banque AUX) lui appartient : 18
blocs, mesurés au banc, et c'est justement là que commencent les données d'un
fichier écrit sur `/RAM`. C'est la contrainte de la machine, pas un défaut de
A2FC — le double haute résolution et `/RAM` se partagent les mêmes octets —
mais elle laissait un volume à moitié faux, dont la prochaine écriture rendait
n'importe quoi.

En quittant une image DHGR, A2FC demande donc à `/RAM` de se reformater : il
reconnaît son pilote à son adresse `$FF00` dans `DEVADR` (`$BF10`), comme le
formateur, et lui envoie la commande FORMAT, carte langage commutée en banque
1 comme ce pilote l'exige (`ram_format`, dans `a2fc_mli.s` — une quarantaine
d'instructions ; le pilote reconstruit lui-même le répertoire de volume, il
n'y a aucune structure à écrire, et l'appel rend à A2FC la banque 2 de la
carte langage, pas la ROM). Le volume revient vide et cohérent, 119
blocs libres sur 127, et la ligne de message le dit : `/RAM was rebuilt
empty.` On perd ce qu'il contenait — c'était déjà perdu — mais plus rien
n'est faux.

Une image **HGR simple** n'écrit qu'en banque principale : elle ne touche pas
à `/RAM` et ne déclenche rien. Le banc `bench/run.py` vérifie les deux cas.
Dans un dossier, Gauche et Droite passent à l'image précédente ou suivante
parmi les fichiers qui ressemblent à une image (type FOT, ou BIN de la
taille d'une page, ou nom en `.RLE`). Le banc décode les deux mires de la
disquette avec le même algorithme, en Python, et compare la page graphique
octet à octet, banque auxiliaire comprise.

**L'écran texte n'est jamais effacé.** Les panneaux restent en `$400-$7FF`
pendant tout le feuilletage, et A2FC n'y réécrit que ce qui change : la ligne
de message dit `Loading NOM...` dès qu'une flèche est pressée, avant même de
relire le dossier — les noms des deux voisines sont gardés hors de la page
graphique —, puis le curseur rejoint la nouvelle image (deux lignes réécrites,
le panneau entier seulement s'il défile) et la ligne d'information suit. Au
retour, les deux tables d'entrées sont relues, mais un panneau n'est redessiné
que si sa relecture montre autre chose qu'à l'entrée : `/RAM` refait à neuf
sous un panneau, une disquette changée. C'est `panel_hash` (`a2fc_mli.s`) qui
en juge, une empreinte de la table d'entrées pliée en un mot, bien moins
chère qu'un panneau redessiné.

**Le chargeur et le décodeur sont une surcouche.** Ils ne sont pas dans le
programme résident mais dans `A2FILE/IMAGE.PLG`, que A2FC lit dans la
fenêtre `$1B00-$1FFF` à la première image et garde en place tant qu'une autre
surcouche (`TEXT.PLG`, `HEX.PLG`, `DELETE.PLG`, `HELP.PLG`) ne la remplace pas ; voir
« Construction et mémoire ». Sans ce fichier, ou avec celui d'une autre
construction, la ligne de message le dit et rien ne s'affiche.

## Lancer un programme Applesoft

Un fichier BAS ne se lance pas seul : c'est `BASIC.SYSTEM` qui l'exécute.
**X** (ou **Entrée**) sur un BAS charge donc `BASIC.SYSTEM` depuis la racine
du volume et lui passe le nom du programme dans le tampon que tous ses
lanceurs utilisent — Bitsy Bye compris : les huit premiers octets d'un
programme SYSTEM sont un saut puis un nom précédé de sa longueur, en `$2006`,
et `BASIC.SYSTEM` en fait la commande `-NOM` à son démarrage. `chain_command`
(chain.s) dépose ce nom dans le talon de la page `$0300`, qui l'écrit en
`chain_addr+6` juste avant de sauter.

Le préfixe ProDOS reste la racine du volume, et le programme est lancé par
son chemin relatif à la racine (`-SOUS/NOM`) tant qu'il y tient — un BAS
rangé dans un sous-dossier se lance donc aussi. Sans `BASIC.SYSTEM` à la
racine du volume, le lancement s'arrête sur `Run failed` et A2FC garde la
main.

**Revenir à A2 File Cmd.** Comme pour un SYS, A2FC ne reprend pas la main
tout seul. Mais depuis l'invite `]` d'Applesoft, `-A2FILE.SYSTEM` relance le
lanceur, qui recharge A2 File Cmd — le programme le rappelle à l'écran. Deux
détails rendent ce retour fiable, là où une version antérieure figeait la
machine sur un écran noir juste après le passage en 80 colonnes :

- **La pile C.** Le lanceur et A2FC prennent toute la machine : ils lisent
  `A2FILE.CODE` jusqu'à `$BE40`, par-dessus `BASIC.SYSTEM` s'il était là. Or
  `crt0`, voyant `BASIC.SYSTEM` résident, plaçait la pile C sur son `HIMEM`
  (~`$9600`) — en plein dans le code qu'on charge, que la pile écrasait
  ensuite en grandissant. `src/crt0.s` (A2FC) et `src/crt0_loader.s` (le
  lanceur) placent donc toujours la pile en `$BF00`, jamais sur le `HIMEM`
  de `BASIC.SYSTEM`, et quittent toujours par le répartiteur ProDOS.
- **Le préfixe.** `BASIC.SYSTEM` vide le préfixe ProDOS en lançant un SYS.
  Le lanceur le refait donc lui-même (`src/loader_mli.s`, `ON_LINE` sur le
  dernier périphérique `$BF30`, puis `SET_PREFIX`) avant de sauter dans
  A2FC, qui rouvre alors ses panneaux et relit `A2FILE.CFG`, comme à froid.

## Les images disque

`W` ouvre la surcouche `A2FILE/DISKIMG.PLG`, trois façons de déplacer une
disquette entière, c'est le seul terrain où A2Command gagnait encore :

- **Écrire** une image (`.PO` ordre ProDOS, `.DSK`/`.DO` ordre DOS 3.3,
  `.2MG` dont l'en-tête donne l'ordre) sur une disquette. La sélection est
  l'image ; on choisit le lecteur cible, qui doit être formaté.
- **Lire** une disquette dans une image neuve, déposée dans le dossier
  ProDOS du panneau actif, en ordre ProDOS ou DOS 3.3 au choix.
- **Copier** une disquette sur une autre. Avec un seul lecteur, on choisit
  deux fois le même : A2FC lit une passe, demande la disquette cible, écrit,
  redemande la source, et ainsi de suite.

Les blocs passent par READ_BLOCK et WRITE_BLOCK, quel que soit le pilote
(Disk II, SmartPort, /RAM). Le tampon d'une passe est en RAM principale
(`$3400`, six blocs) et, pour la copie à un lecteur, quatre-vingts blocs de
plus en RAM auxiliaire `$2000` : `/RAM` est donc refait à neuf en sortant,
comme après une image DHGR. La conversion d'ordre est celle de `po2dsk.py`.
Comme le formateur, l'écriture exige le mot `ERASE` en capitales, la
disquette du programme est refusée, et l'avertissement nomme le lecteur et
son volume ; Échap annule avant toute écriture. Le banc lit la disquette
d'amorce dans une image DOS 3.3 et la compare octet à octet, écrit une image
de 64 blocs sur une disquette vierge et vérifie la disquette après éjection,
puis mène la copie jusqu'à l'avertissement.

## Une image disque comme dossier

**Entrée** sur un fichier `.PO`, `.2MG`, `.DSK` ou `.DO` l'ouvre en lecture
comme un dossier : le panneau montre le contenu du volume ProDOS de l'image,
et l'on y navigue comme partout ailleurs — **Entrée** dans un sous-dossier,
**Échap** pour remonter, **Échap** à la racine pour sortir et retrouver le
fichier image dans son dossier. Le chemin porté par le panneau devient
`/VOL/DISK.PO/SOUS-DOSSIER`. A2Command ne sait pas faire cela.

Les blocs sont lus par `fseek` dans le fichier image (`img_read_block`) : un
`.DSK`/`.DO` est en ordre DOS 3.3, permuté secteur par secteur comme
`po2dsk.py` à l'envers ; un `.2MG` donne son ordre et le décalage de ses
données dans son en-tête. Le répertoire se lit alors bloc par bloc en
suivant le chaînage ProDOS, exactement comme un vrai dossier. Une image qui
n'est pas un volume ProDOS lisible (un DOS 3.3, par exemple) est refusée et
le panneau revient à son dossier.

Une image ouverte ainsi est en **lecture seule** : seules la navigation, le
marquage (Espace) et **C** agissent ; les commandes qui écriraient sont
refusées en clair. **C** extrait les fichiers marqués — sinon celui sous le
curseur — vers le dossier ProDOS de l'autre panneau, avec leur type et leur
auxtype. Les sous-dossiers sont à entrer et extraire un à un ; les fichiers
germe et plant (≤ 128 Ko) sont extraits, les rares fichiers arborescents
sont refusés. L'extraction est la surcouche `IMGFS.PLG` : elle lit le fichier
ProDOS (bloc de données pour un germe, bloc d'index de 256 pointeurs pour un
plant, un pointeur nul étant un trou de zéros) et l'écrit sur le disque. Le
banc ouvre `TINY.PO`, descend dans un sous-dossier, en extrait un fichier et
compare son contenu **octet à octet**.

### Une disquette DOS 3.3

A2FC lit aussi les disquettes **DOS 3.3**, aussi bien depuis une image
(`.DSK`/`.DO`, ou un `.2MG` en ordre DOS) que depuis un **vrai disque** dans
un lecteur — c'est ce que réclamaient les premiers essais. Une image `.DSK`
qui n'est pas un volume ProDOS est essayée en DOS 3.3 : si sa VTOC (piste 17,
secteur 0) est valable, son catalogue s'ouvre comme un dossier plat. Un vrai
disque DOS 3.3, qui n'a pas de volume ProDOS, apparaît dans la liste des
volumes (`/`) sous le nom `DOS 3.3`, avec son slot et son lecteur : Entrée
l'ouvre. Les types DOS (T, I, A, B) sont montrés en leur plus proche type
ProDOS (TXT, INT, BAS, BIN), et **C** extrait les fichiers marqués vers le
dossier ProDOS de l'autre panneau, l'en-tête DOS ôté (les deux octets de
longueur d'un Applesoft ou Integer, les quatre d'un binaire) pour que le
fichier soit utilisable.

Les secteurs se lisent par le même code, quelle que soit la source : `fseek`
dans une image, ou **READ_BLOCK** sur le pilote Disk II pour un vrai disque,
le secteur DOS logique traduit en demi-bloc ProDOS par la table `DOS_TS`,
l'inverse de celle de `po2dsk.py`. Le catalogue chaîné en piste 17 et les
listes secteur par secteur des fichiers font le reste. Le catalogue est lu
par le noyau, l'extraction par la surcouche `DOS33.PLG`. Le banc ouvre une
image DOS 3.3, vérifie ses types et en extrait un fichier, comparé **octet à
octet**. (POM2 ne rend lisible que la disquette d'amorce et un fichier-image ;
la lecture d'un vrai disque physique partage tout le code de la lecture d'une
image, seule la source des secteurs change.)

## Formater un disque

`F` (ou `A2FILE/FORMAT.SYS` depuis Bitsy Bye) lance le formateur, un
programme à part qui revient à A2FC en sortant. Il liste les lecteurs que
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
et comparés. Le banc ouvre le formateur, vérifie qu'il liste les lecteurs
avec leur volume et leur taille, et qu'Échap relance le gestionnaire depuis
la disquette.

## La musique Mockingboard

Entrée sur un fichier `.MB` (flux MB1, 2 304 octets au plus) le monte en
mémoire auxiliaire par le lecteur six voix et le joue une fois, en
interruption : la navigation, les visionneuses et l'éditeur continuent
pendant la musique, et les lectures disque ne l'arrêtent pas (vérifié dans
l'émulateur : le curseur du flux avance pendant la lecture des dossiers et
le chargement d'une image). Sur une disquette 5,25 pouces, le pilote Disk II
de ProDOS coupe les interruptions pendant chaque lecture de bloc : le lecteur
se fige le temps de la lecture, puis reprend ; A2FC n'y peut rien. P la met
en pause et la reprend, un autre `.MB` la remplace, Q et X la coupent ; une
fois le morceau fini, P le dit. La carte est cherchée dans les slots 1 à 7 à la
première demande ; sans carte, A2FC le dit.

**Un morceau chargé refait `/RAM` à neuf, comme une image DHGR.** Le flux
vit en `$1000-$18FF` de la banque auxiliaire, et cette mémoire appartient
au disque virtuel de ProDOS : mesuré dans l'émulateur avec ProDOS 2.4.3, son
pilote y range les blocs 9, 26, 43… (un sur dix-sept), sa carte des blocs
est en `$0C00` et son répertoire, d'un seul bloc, en `$0E00` ; il n'y a nulle
part en AUX 2 304 octets hors de sa portée. Avant le correctif du
2026-09-07, la fanfare de 56 octets suffisait à écraser le bloc 9 de
`/RAM`, en silence. Désormais A2FC monte le flux, demande à `/RAM` de se
reformater (`ram_format`, comme au retour d'une image DHGR) et l'écrit dans
la ligne de message : `Playing WELCOME.MB, slot 4. P pauses.  /RAM was
rebuilt empty.` Le volume refait ne relit jamais ses blocs libres, la
musique joue donc sans risque ; écrire sur `/RAM` pendant qu'elle joue
abîmerait le morceau, pas le volume. Refaire `/RAM` protège du même coup le
petit miroir que le lecteur recopie en banque auxiliaire à l'adresse de son
code (au-dessus de `$4000`, pour lire le flux sous interruption) : sur un
`/RAM` rempli jusque-là, ce miroir aurait été écrasé et l'IRQ serait partie
dans le décor.

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

## Ce que A2FC ne fait pas

- Il refuse de copier un dossier dans lui-même, et un arbre dont un chemin
  cumule plus de 213 entrées (la réserve des parcours récursifs, logée dans
  la table du panneau inactif pendant l'opération).
- Il ne revient pas d'un programme lancé : ce qui est chargé l'écrase. Seul
  le formateur, qui le relance en sortant, fait exception.
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
| `A2FILE.SYSTEM` | Le lanceur, à la racine : seul fichier `.SYSTEM` du volume, donc celui que ProDOS démarre (`src/loader.c`) |
| `A2FILE/A2FILE.CODE` | Le gestionnaire lui-même (`src/a2fc.c`, plus `src/a2fc_mli.s` pour GET_FILE_INFO, SET_FILE_INFO et le reformatage du /RAM) |
| `A2FILE/A2FILE.CFG` | Écrit par A2FC en quittant : les deux dossiers, le tri et le panneau actif, trois lignes de texte |
| `A2FILE/FORMAT.SYS` | Le formateur (`format.c`, `format_diskii.s`, `format_mli.s`). Pas de suffixe .SYSTEM : ProDOS amorce le premier fichier .SYSTEM du catalogue, et F passe avant S |
| `A2FILE/A2FILE.HELP` | Le texte de la page d'aide (`data/A2FILE.HELP.TXT`), une ligne par élément : `x,y,TOUCHE,libellé`, `x,y,#TITRE` pour une section, `x,y,~texte` pour du texte en clair. Il passe par la page graphique, rien de l'aide ne reste en mémoire |

Les noms tiennent dans les quinze caractères de ProDOS.

## La disquette 5,25 pouces

`make disk` produit `dist/A2FILECMD.po` (ordre ProDOS)
et `dist/A2FILECMD.dsk` (ordre DOS 3.3, celui d'ADTPro et de la plupart
des émulateurs), une disquette amorçable de 280 blocs, volume `/A2FILECMD` :

| Fichier | Contenu |
|---|---|
| `PRODOS`, `BASIC.SYSTEM` | ProDOS 8 2.4.3, la dernière version stable, et son interpréteur Applesoft : librement distribués pour la communauté Apple II, ils ne sont pas de l'auteur |
| `A2FILE.SYSTEM` | le lanceur, seul programme `.SYSTEM` : la disquette démarre directement dans A2FC. Compilé avec `NO_CHDIR`, il se fie au préfixe du volume amorcé |
| `A2FILE/A2FILE.CODE`, `A2FILE/*.PLG`, `A2FILE/A2FILE.HELP`, `A2FILE/FORMAT.SYS` | le programme, ses treize surcouches (`IMAGE`, `TEXT`, `HEX`, `HELP`, `DELETE`, `MUSIC`, `RUN`, `ATTR`, `IMGFS`, `DOS33`, et les grandes `EDIT`, `MENU`, `DISKIMG` : des BIN chargés en `$1B00` à la demande), le texte de l'aide et le formateur ; `A2FILE.CFG` sera écrit à côté |
| `DEMO/` | de quoi essayer, entièrement calculé par `tools/mkdemo.py` : deux mires (`DHGR.RLE`, `HGR.RLE`), une fanfare trois voix (`WELCOME.MB`), un texte (`SAMPLE`), un programme Applesoft (`HELLO`) et un `README` |

Il reste 46 blocs libres. Au démarrage, le panneau gauche montre la racine
de la disquette et le panneau droit son dossier `DEMO`. `mkvolume.py` écrit
le volume de 280 blocs, `po2dsk.py` en tire l'ordre DOS 3.3. Le banc amorce
cette image en slot 6 dans POM2 : A2FC s'ouvre sur `/A2FILECMD`, Q rend la
main à Bitsy Bye sur ce volume. Une version 2.5
alpha 8 de ProDOS existe ; elle n'est pas retenue, faute d'être publiée.

## Construction et mémoire

`make` construit les trois binaires, `make disk` la disquette. Le code
tourne à `$4000`. Les deux tables de 140 entrées occupent la page graphique
MAIN `$2000-$3FFF`, libre tant qu'aucune image n'est affichée : une image
la recouvre, et les deux panneaux sont relus au retour, marques conservées.
La RAM basse `$1000-$1AFF` reçoit toute la BSS de `a2fc.c` (panneaux,
chemins, copie, débuts de page du texte, la souris), mise à zéro par `main`,
et depuis `a2fc.cfg` la BSS principale de cc65 avec elle. Au-dessus,
`$1B00-$1FFF` est **la fenêtre de surcouche** : 1 280 octets où A2FC charge,
au moment d'ouvrir un fichier, le module qui sait le lire, et qu'il oublie
en revenant aux panneaux. **Treize surcouches**, sous `A2FILE/` : `IMAGE.PLG`
(le décodeur d'images), `TEXT.PLG` et `HEX.PLG` (les visionneuses),
`HELP.PLG` (l'aide), `DELETE.PLG` (la commande D et `delete_tree`, que le
déplacement d'un dossier charge aussi), `MUSIC.PLG` (le chargement d'un
`.MB`), `RUN.PLG` (X, F, et Entrée sur un SYS ou un BAS), `ATTR.PLG` (R, K,
A, L), `IMGFS.PLG` (l'extraction d'une image ProDOS ouverte comme un
dossier) et `DOS33.PLG` (l'extraction d'une disquette DOS 3.3, voir « Une
image disque comme dossier ») ; `MUSIC.PLG` porte aussi M et S ; et **trois grandes
surcouches** qui prennent aussi la page graphique `$2000-$3FFF` :
`EDIT.PLG` (l'éditeur, son texte au-dessus de son code), `MENU.PLG` (le menu
`!`) et `DISKIMG.PLG` (les images disque). Elles sont
**liées avec le programme** — elles appellent `fopen`, `memcpy`, `view_getc`
comme n'importe quelle fonction, et le noyau appelle leur point d'entrée à
son adresse dans la fenêtre — mais `a2fc.cfg` les écrit dans des fichiers à
part (deux segments par surcouche, `NOM` pour le code et `NOMRO` pour les
chaînes, dans le même fichier `%O.NOM`, code d'abord pour que les mots à zéro
que cc65 pose en tête d'une `.proc` sous `-Cl` n'atterrissent pas sur le
point d'entrée) que `make disk` range sous `A2FILE/` avec l'auxtype `$1B00`.
Passer un module en surcouche a rendu **près de 3,5 Ko** à la fenêtre
principale, qui finit désormais à `$ADC2` au lieu de `$BADF`.

Chaque surcouche s'ouvre sur l'en-tête `struct Overlay` (`a2fc_plugin.h`,
`overlay.s`, premier objet du lien) : la **signature** — l'adresse de `main`
dans le lien qui l'a produite, ou `PLUGIN_MAGIC` pour une surcouche d'un
tiers —, un octet de **drapeaux** (`OVERLAY_BIG` : grande surcouche), le
**point d'entrée** que le menu `!` appelle sur la sélection, et une
**description** d'une ligne. Une surcouche d'une autre construction est
refusée comme une absente, la ligne de message le dit. **`A2FILE.CODE` et
ses `.PLG` vont donc par ensemble.** Une surcouche d'un tiers, elle, ne
touche au programme que par la **table de services** (`struct A2fcApi`) que
le noyau lui passe : `fopen`, `message`, `confirm`, `prompt`, `dir_open`/
`dir_next`, `read_panel`, `mli`… — l'ABI stable, dont les champs ne changent
pas de place et à qui l'on n'ajoute qu'à la fin (`api->version` le dit).
`overlay()` lit chaque surcouche avec un simple `fread`, et n'en relit aucune
tant qu'elle est en place : feuilleter un dossier d'images ne relit rien.
Le lanceur ne met plus en scène en `$1000` que les 3 Ko
de l'image de la carte langage (`STAGE_BYTES` dans `loader.c`). La zone
`LOWRAM` est bornée à `$0B00` pour que le lieur refuse une BSS qui monterait
dans la fenêtre, et `check_layout.py` vérifie que chaque surcouche tient
entre la RAM basse et son plafond — la page graphique, ou ce qu'une grande
surcouche y garde pour elle — et que chaque fichier a la longueur du lien. La réserve des parcours récursifs emprunte la table d'entrées du
panneau inactif.

**La souris** (`mouse.s`) cherche la carte AppleMouse II par sa signature
(`$Cn05=$38`, `$Cn07=$18`, `$Cn0B=$01`, `$Cn0C=$20`, `$CnFB=$D6`) de `$C7` à
`$C1` en sautant le slot 3, où le firmware 80 colonnes du //e répond ;
`INITMOUSE`, puis `CLAMPMOUSE` à 0..79 et 0..23 — la position arrive
directement en cases de l'écran, aucun calcul — et `SETMOUSE` mode 1 : la
carte compte toute seule, `READMOUSE` à chaque tour de `wait_key` suffit,
aucune interruption n'est réservée. Le pointeur est un caractère MouseText
(`$42`) posé sur la cellule, l'octet caché étant rendu avant tout redessin ;
la colonne paire vit en banque AUX, atteinte par `PAGE2` sous `80STORE`. Le
banc met une AppleMouse II (HLE AppleWin) en slot 4 pour toute la session et
vérifie le pointeur, les bornes du firmware, le clic, le second clic, le
changement de panneau et la barre de touches.
Les visionneuses, les saisies et le fichier de préférences vivent dans la
carte langage, `$D400-$DFFF` en banque 2 (une vingtaine d'octets libres : `check_layout.py` veille), copiés par `crt0.s` comme pour le
jeu ; avant de lancer un programme, A2FC remet la ROM en lecture.

**Le plafond de la fenêtre principale.** Ce qui survit à l'initialisation —
CODE, RODATA, DATA, INIT — doit finir sous le plancher de la pile C,
`__HIMEM__ - __STACKSIZE__` ; seul ONCE a le droit de le dépasser, il est mort
avant `main`. ld65 ne le vérifie pas : la zone BSS se dimensionne par
`__HIMEM__ - __STACKSIZE__ - __ONCE_RUN__` et, dès que cette différence passe
en négatif, il la lit en entier non signé, ne signale rien et pose la BSS au
milieu de la pile. Le lien réussit, le programme se corrompt à l'usage. Deux
mesures ferment ce piège : A2FC est lié par `a2fc.cfg`, où la BSS descend en
RAM basse (il ne lie ni `malloc` ni `free` — les tampons ProDOS viennent de
`$0800` — donc aucun tas ne la suit), et
`check_layout.py` contrôle le plancher à chaque lien. La pile C fait 256
octets : le banc a mesuré son creux maximal à **94 octets** sous `$BF00`, la
copie récursive d'un arbre comprise, `-Cl` mettant les locales en statique.
Les 512 octets d'avant, plus les 88 de la BSS, sont rendus au code — de quoi
loger le lanceur Applesoft, là où il ne restait qu'une vingtaine d'octets.
Les programmes lancés par
X et F le sont par un talon recopié en page `$0300` (`chain.s`), qui lit le
fichier entier à son adresse et y saute : aucune limite de taille, et
FORMAT.SYS revient à A2FC par le même talon ; `chain_command` y ajoute le nom
que `BASIC.SYSTEM` attend en `$2006`, seize octets de plus dans le talon, et
une assertion d'assemblage garde l'ensemble sous `$03D0`, où commencent les
vecteurs. A2FC n'utilise plus ni
`opendir` ni `malloc` : les dossiers sont lus comme des fichiers, bloc par
bloc, dans le tampon de copie, ce qui est aussi plus rapide. Pour loger
l'éditeur et le visionneur, il a aussi rendu `hgr_loader.s` (le décodeur C
le remplace, par tranches `memset`/`memcpy` jusqu'à la frontière des
banques), `qsort` (un tri par insertion) et `exec()` (un lanceur de
quelques lignes) ; les messages répétés sont partagés et l'aide vit sur le
disque. Les deux fichiers ouverts pendant une copie utilisent les tampons
ProDOS `$0800` et `$0C00` ; A2FC n'utilise pas MAPBSS. Le programme est
compilé avec `-Cl` (variables locales statiques) ; les trois
parcours récursifs (compte, copie, suppression d'un arbre) repassent leurs
variables sur la pile par `#pragma static-locals`, sans quoi le niveau
interne écrase la longueur de chemin du niveau externe. La sortie suit le QUIT ProDOS du démarrage cc65.

Les preuves viennent de [bancs POM2 sans fenêtre](../bench/README.md), qui
partent tous de `dist/A2FILECMD.po` **tel qu'il sera téléchargé**.
`bench/run.py` joue une session complète — amorçage, navigation, pages,
marquage, copie, déplacement, renommage, verrou refusant la suppression,
changement de type et d'auxtype, création de dossier, suppression,
visionneuses texte et hexadécimale, aide, les deux mires comparées **octet à
octet dans les deux banques**, `/RAM` refait après une DHGR et intact après
une HGR, la fanfare qui se termine seule, l'éditeur, le formateur qui liste
les lecteurs et relance le gestionnaire, les images disque écrites et relues
(`.PO` et `.DSK`) et une disquette copiée lecteur à lecteur, une image
ouverte comme un dossier et un fichier extrait et comparé, un catalogue
DOS 3.3 lu et un fichier extrait, enfin un programme Applesoft lancé par
`BASIC.SYSTEM` puis le retour sur les panneaux par `-A2FILE.SYSTEM` :
**69 contrôles**.
`bench/memory.py` mesure le creux de la
pile C en faisant travailler le programme (86 octets sur les 256 réservés),
et `bench/smoke.py` se contente de vérifier que la disquette publiée démarre.
Hors émulateur, `make test` vérifie le contrat de disposition mémoire,
l'aller-retour de l'écrivain de volume ProDOS et le décodage des fichiers de
démonstration. Le banc travaille toujours sur une copie de l'image.

Bugs corrigés par cette chasse (et une relecture indépendante du code) avant
la 1.0 : la carte des marques faisait un octet de trop court (quatre entrées
fantômes dans une fenêtre pleine), le panneau tronquait les chemins longs par
la fin, une fenêtre après la première comptait 140 entrées et en répétait une,
un dossier vidé en mode fenêtré restait bloqué, le formateur calculait la
carte des blocs sur 16 bits (nulle pour 65 535 blocs), prenait la taille dans
l'en-tête de l'ancien volume, acceptait un lecteur sans disque, et revenait à
Bitsy Bye depuis la disquette (A2FILE.SYSTEM y est à la racine) ; un BIN chargé
en `$0800` écrasait le tampon du talon ; un A2FILE.HELP ou un A2FILE.CFG abîmé
pouvait faire écrire n'importe où ; la copie détruisait la cible avant d'avoir
ouvert la source, et pouvait remplacer un dossier vide par un fichier. Le
plus grave, trouvé par la relecture finale et reproduit par `roundtrips.py` :
le talon de lancement ne rendait pas à ProDOS l'entrée d'interruption prise
au démarrage pour la Mockingboard (ProDOS n'en a que quatre, et le vecteur
pointait dans de la mémoire recouverte) ; au troisième aller-retour F/ESC,
A2FC plantait dans le moniteur. `chain.s` appelle désormais `donelib`
(les destructeurs cc65) avant de sauter, et le lanceur fait de
même. Une troisième relecture, centrée sur l'éditeur, les images et la
musique, a encore corrigé : l'éditeur n'avait pas de curseur visible
(`cursor(1)` de conio), un fichier créé par E décalait les marques restaurées
sur d'autres entrées (elles sont effacées dans ce cas), une sauvegarde sur un
volume plein vidait le fichier avant d'échouer (la place est vérifiée avant
le `fopen "wb"` qui tronque), Entrée au milieu d'une ligne laissait
l'ancienne fin à l'écran, les erreurs d'ouverture de l'éditeur disparaissaient
sous le redessin, le lanceur lisait A2FILE.CODE sans borne sous `$BF00`, le
destructeur de la musique passait après la libération de l'interruption
(priorité 11 dans `music.s`), le visionneur d'images gardait un index périmé
si le dossier changeait sous lui, et un .MB sans END faisait lire l'AUX
au-delà du flux. `explore2.py` couvre l'éditeur (raccourcir, sans CR final,
LF seuls, fichier verrouillé), les marques en fenêtre pleine et en seconde
fenêtre, le déplacement vers /RAM et la suppression d'un arbre de 150
fichiers.

La chasse du 2026-09-07 au soir, après les surcouches et la souris, a
trouvé et reproduit dans POM2 quatre bugs de plus : E sur un fichier de
plus de 8 Ko le lisait dans la page graphique avant de le refuser, et
laissait les deux tables d'entrées écrasées par son début sans les relire
(la ligne suivante du panneau affichait du bruit) — la taille est
désormais refusée avant tout `fread` ; un BAS lancé sans `BASIC.SYSTEM`
sur le volume (`Run failed`) laissait son nom dans le talon de `chain.s`,
et le prochain SYS lancé par X recevait ce « -NOM » en `$2006`, au milieu
de son code (écran vide, machine plantée) — le nom est effacé dès l'échec ;
un chargement DHGR qui échouait à mi-chemin (fichier tronqué) avait déjà
écrit en banque auxiliaire mais ne refaisait pas `/RAM` — il est refait
dès qu'un chargement DHGR a commencé ; et la musique, voir plus haut,
écrasait `/RAM` en silence.
