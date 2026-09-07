# Le manuel d'A2 Retro Cmd

Un gestionnaire de fichiers ProDOS à deux panneaux, dans l'esprit de Total
Commander, pour l'Apple IIe 128 Ko ; à l'écran il se nomme **A2 RETRO CMD
1.0** (le numéro vit dans `A2RC_VERSION` du Makefile, repris par le lanceur,
la ligne de statut et l'aide). C'est un logiciel libre sous licence GNU GPL
v3, d'Arnaud Verhille ; le lanceur et l'aide le rappellent. Deux façons de le
lancer : amorcer la disquette `/A2RETROCMD`, ou choisir `A2RETRO.SYSTEM`
depuis un sélecteur comme Bitsy Bye.

Le lanceur affiche un écran d'attente pendant le chargement : le titre, la
mention « ProDOS 8 only », la date et l'heure si une horloge est présente
(bit 0 de MACHID, `$BF98`) ou « No clock » sinon, puis **PLEASE WAIT**. Suivent
les deux panneaux en texte 80 colonnes : à gauche le volume amorcé, à droite
son dossier `DEMO` la première fois ; ensuite les deux dossiers, le tri et le
panneau actif de la session précédente, lus dans `A2RETRO/A2RETRO.CFG`.

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
| **Entrée** | ouvrir : un dossier s'ouvre ; une image s'affiche plein écran, en HGR ou en DHGR selon son contenu (une touche pour revenir, la ligne de message dit le format reconnu) ; un TXT se lit page par page ; un SYS ou un BAS se lance après confirmation ; tout autre fichier s'affiche en hexadécimal |
| **Échap** | remonter au dossier parent, la sélection revient sur le dossier quitté ; depuis la racine d'un volume, la liste des volumes |
| **/** | la liste des volumes en ligne |
| **C** | copier les entrées marquées, sinon l'entrée sélectionnée, dans le dossier de l'autre panneau ; un dossier est copié entier, sous-dossiers compris, un sous-dossier déjà présent est complété ; même nom, même type et auxtype. Quand le fichier existe, A2RC demande : **O** écraser, **S** passer, **A** tout écraser, **N** ne rien écraser. Une barre de progression montre le fichier en cours, son rang sur le total et les octets copiés ; le message final compte les fichiers copiés et passés |
| **V** | déplacer : copie, puis suppression de l'original, dossiers compris |
| **R** | renommer (nom ProDOS : une lettre, puis lettres, chiffres ou points, 15 au plus) |
| **D** | supprimer les entrées marquées, sinon l'entrée sélectionnée, après une confirmation ; un dossier est supprimé avec tout son contenu |
| **K** | créer un dossier dans le panneau actif |
| **S** | changer le tri : nom, taille décroissante, type ; les deux panneaux suivent |
| **M** | marquer les fichiers absents de l'autre panneau ou de taille différente : suivi de C, c'est une synchronisation |
| **A** | changer le type et l'auxtype d'un fichier, en hexadécimal |
| **L** | verrouiller ou déverrouiller ; un fichier verrouillé porte un L après son nom et refuse la suppression et le renommage |
| **?** | l'aide, un écran qui résume toutes les touches, sous le titre « A2 Retro Cmd » |
| **T** | lire le fichier sélectionné comme du texte |
| **H** | afficher le fichier sélectionné en hexadécimal |
| **X** | lancer le fichier sélectionné après confirmation ; A2RC ne reprend pas la main. Un SYS est lu en `$2000`, un BIN à son auxtype, entre `$0800` et `$BAFF` (le talon garde son tampon ProDOS en `$BB00`). Un BAS (Applesoft) passe par `BASIC.SYSTEM`, voir ci-dessous |
| **E** | éditer le fichier sélectionné comme du texte ; sur un dossier ou `..`, créer un fichier texte neuf dans le dossier courant |
| **I** | afficher le fichier sélectionné comme une image, quel que soit son nom : HGR ou DHGR, brut ou compressé RLE |
| **P** | mettre en pause ou reprendre la musique Mockingboard ; Entrée sur un fichier `.MB` la lance |
| **F** | ouvrir le formateur, `A2RETRO/FORMAT.SYS`, qui revient à A2RC en sortant |
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

À l'ouverture, A2RC lit les huit premiers octets et la taille :

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

**Une image DHGR détruit le contenu de `/RAM`, alors A2RC le refait à
neuf.** Le disque virtuel de ProDOS vit en RAM auxiliaire, et la moitié
auxiliaire d'une page DHGR (`$2000-$3FFF` en banque AUX) lui appartient : 18
blocs, mesurés au banc, et c'est justement là que commencent les données d'un
fichier écrit sur `/RAM`. C'est la contrainte de la machine, pas un défaut de
A2RC — le double haute résolution et `/RAM` se partagent les mêmes octets —
mais elle laissait un volume à moitié faux, dont la prochaine écriture rendait
n'importe quoi.

En quittant une image DHGR, A2RC demande donc à `/RAM` de se reformater : il
reconnaît son pilote à son adresse `$FF00` dans `DEVADR` (`$BF10`), comme le
formateur, et lui envoie la commande FORMAT, carte langage commutée en banque
1 comme ce pilote l'exige (`ram_format`, dans `a2rc_mli.s` — une quarantaine
d'instructions ; le pilote reconstruit lui-même le répertoire de volume, il
n'y a aucune structure à écrire, et l'appel rend à A2RC la banque 2 de la
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

## Lancer un programme Applesoft

Un fichier BAS ne se lance pas seul : c'est `BASIC.SYSTEM` qui l'exécute.
**X** (ou **Entrée**) sur un BAS charge donc `BASIC.SYSTEM` depuis la racine
du volume et lui passe le nom du programme dans le tampon que tous ses
lanceurs utilisent — Bitsy Bye compris : les huit premiers octets d'un
programme SYSTEM sont un saut puis un nom précédé de sa longueur, en `$2006`,
et `BASIC.SYSTEM` en fait la commande `-NOM` à son démarrage. `chain_command`
(chain.s) dépose ce nom dans le talon de la page `$0300`, qui l'écrit en
`chain_addr+6` juste avant de sauter.

Le préfixe ProDOS part sur le dossier du programme : `-NOM` s'y résout, un BAS
rangé dans un sous-dossier se lance donc aussi. Sans `BASIC.SYSTEM` à la
racine du volume, le lancement s'arrête sur `Run failed` et A2RC garde la
main. Comme pour un SYS, A2RC ne reprend pas la main ensuite : on revient
par Applesoft.

## Formater un disque

`F` (ou `A2RETRO/FORMAT.SYS` depuis Bitsy Bye) lance le formateur, un
programme à part qui revient à A2RC en sortant. Il liste les lecteurs que
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
se fige le temps de la lecture, puis reprend ; A2RC n'y peut rien. P la met
en pause et la reprend, un autre `.MB` la remplace, Q et X la coupent ; une
fois le morceau fini, P le dit. La carte est cherchée dans les slots 1 à 7 à la
première demande ; sans carte, A2RC le dit.

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

## Ce que A2RC ne fait pas

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
| `A2RETRO.SYSTEM` | Le lanceur, à la racine : seul fichier `.SYSTEM` du volume, donc celui que ProDOS démarre (`src/loader.c`) |
| `A2RETRO/A2RETRO.CODE` | Le gestionnaire lui-même (`src/a2rc.c`, plus `src/a2rc_mli.s` pour GET_FILE_INFO, SET_FILE_INFO et le reformatage du /RAM) |
| `A2RETRO/A2RETRO.CFG` | Écrit par A2RC en quittant : les deux dossiers, le tri et le panneau actif, trois lignes de texte |
| `A2RETRO/FORMAT.SYS` | Le formateur (`format.c`, `format_diskii.s`, `format_mli.s`). Pas de suffixe .SYSTEM : ProDOS amorce le premier fichier .SYSTEM du catalogue, et F passe avant S |
| `A2RETRO/A2RETRO.HELP` | Le texte de la page d'aide (`data/A2RETRO.HELP.TXT`), une ligne par élément : `x,y,TOUCHE,libellé`, `x,y,#TITRE` pour une section, `x,y,~texte` pour du texte en clair. Il passe par la page graphique, rien de l'aide ne reste en mémoire |

Les noms tiennent dans les quinze caractères de ProDOS.

## La disquette 5,25 pouces

`make disk` produit `dist/A2RETROCMD.po` (ordre ProDOS)
et `dist/A2RETROCMD.dsk` (ordre DOS 3.3, celui d'ADTPro et de la plupart
des émulateurs), une disquette amorçable de 280 blocs, volume `/A2RETROCMD` :

| Fichier | Contenu |
|---|---|
| `PRODOS`, `BASIC.SYSTEM` | ProDOS 8 2.4.3, la dernière version stable, et son interpréteur Applesoft : librement distribués pour la communauté Apple II, ils ne sont pas de l'auteur |
| `A2RETRO.SYSTEM` | le lanceur, seul programme `.SYSTEM` : la disquette démarre directement dans A2RC. Compilé avec `NO_CHDIR`, il se fie au préfixe du volume amorcé |
| `A2RETRO/A2RETRO.CODE`, `A2RETRO/A2RETRO.HELP`, `A2RETRO/FORMAT.SYS` | le programme, son aide et le formateur ; `A2RETRO.CFG` sera écrit à côté |
| `DEMO/` | de quoi essayer, entièrement calculé par `tools/mkdemo.py` : deux mires (`DHGR.RLE`, `HGR.RLE`), une fanfare trois voix (`WELCOME.MB`), un texte (`SAMPLE`), un programme Applesoft (`HELLO`) et un `README` |

Il reste 60 blocs libres. Au démarrage, le panneau gauche montre la racine
de la disquette et le panneau droit la liste des volumes, faute de dossier
`DHGR`. `build_prodos_volume` taille ses volumes au contenu ;
`make_floppy.py` porte ensuite le compte de blocs à 280, libère les blocs
ajoutés dans la table d'allocation et écrit les deux ordres de secteurs. Le
banc a démarré cette image comme disque dur dans POM2 : A2RC s'ouvre sur
`/A2RETROCMD`, Q rend la main à Bitsy Bye sur ce volume. Une version 2.5
alpha 8 de ProDOS existe ; elle n'est pas retenue, faute d'être publiée.

## Construction et mémoire

`make` construit les trois binaires, `make disk` la disquette. Le code
tourne à `$4000`. Les deux tables de 140 entrées occupent la page graphique
MAIN `$2000-$3FFF`, libre tant qu'aucune image n'est affichée : une image
la recouvre, et les deux panneaux sont relus au retour, marques conservées.
La RAM basse `$1000-$1FFF` reçoit toute la BSS de `a2rc.c` (panneaux,
chemins, copie, débuts de page du texte), mise à zéro par `main`, et depuis
`a2rc.cfg` la BSS principale de cc65 avec elle. Son dernier kilo-octet,
`$1C00-$1FFF`, est **du code** : segment `LOWEXE`, le décodeur RLE et ce qui
l'entoure. Le lanceur met en scène en `$1000` un préfixe de 4 Ko au lieu de 3
(`STAGE_BYTES` dans `loader.c`) ; `crt0` n'en emporte que les trois premiers
vers la carte langage, le quatrième reste sur place. Personne d'autre n'y
touche : la zone `LOWRAM` est bornée à `$0C00` pour que le lieur refuse une
BSS qui monterait jusque-là, et `check_lc_layout.py` le vérifie aussi. C'était
la dernière réserve de place de la machine — la fenêtre principale bute sur la
pile C, la carte langage est pleine. **`A2RETRO.SYSTEM` et `A2RETRO.CODE` vont
désormais par paire** : un ancien lanceur ne lit que 3 Ko et laisserait le
décodeur d'images absent. La réserve
des parcours récursifs emprunte la table d'entrées du panneau inactif.
Les visionneuses, les saisies et le fichier de préférences vivent dans la
carte langage, `$D400-$DFFF` en banque 2 (une vingtaine d'octets libres : `check_lc_layout.py` veille), copiés par `crt0.s` comme pour le
jeu ; avant de lancer un programme, A2RC remet la ROM en lecture.

**Le plafond de la fenêtre principale.** Ce qui survit à l'initialisation —
CODE, RODATA, DATA, INIT — doit finir sous le plancher de la pile C,
`__HIMEM__ - __STACKSIZE__` ; seul ONCE a le droit de le dépasser, il est mort
avant `main`. ld65 ne le vérifie pas : la zone BSS se dimensionne par
`__HIMEM__ - __STACKSIZE__ - __ONCE_RUN__` et, dès que cette différence passe
en négatif, il la lit en entier non signé, ne signale rien et pose la BSS au
milieu de la pile. Le lien réussit, le programme se corrompt à l'usage. Deux
mesures ferment ce piège : A2RC est lié par `a2rc.cfg`, où la BSS descend en
RAM basse (il ne lie ni `malloc` ni `free` — les tampons ProDOS viennent de
`$0800` — donc aucun tas ne la suit), et
`check_lc_layout.py` contrôle le plancher à chaque lien. La pile C fait 256
octets : le banc a mesuré son creux maximal à **94 octets** sous `$BF00`, la
copie récursive d'un arbre comprise, `-Cl` mettant les locales en statique.
Les 512 octets d'avant, plus les 88 de la BSS, sont rendus au code — de quoi
loger le lanceur Applesoft, là où il ne restait qu'une vingtaine d'octets.
Les programmes lancés par
X et F le sont par un talon recopié en page `$0300` (`chain.s`), qui lit le
fichier entier à son adresse et y saute : aucune limite de taille, et
FORMAT.SYS revient à A2RC par le même talon ; `chain_command` y ajoute le nom
que `BASIC.SYSTEM` attend en `$2006`, seize octets de plus dans le talon, et
une assertion d'assemblage garde l'ensemble sous `$03D0`, où commencent les
vecteurs. A2RC n'utilise plus ni
`opendir` ni `malloc` : les dossiers sont lus comme des fichiers, bloc par
bloc, dans le tampon de copie, ce qui est aussi plus rapide. Pour loger
l'éditeur et le visionneur, il a aussi rendu `hgr_loader.s` (le décodeur C
le remplace, par tranches `memset`/`memcpy` jusqu'à la frontière des
banques), `qsort` (un tri par insertion) et `exec()` (un lanceur de
quelques lignes) ; les messages répétés sont partagés et l'aide vit sur le
disque. Les deux fichiers ouverts pendant une copie utilisent les tampons
ProDOS `$0800` et `$0C00` ; A2RC n'utilise pas MAPBSS. Le programme est
compilé avec `-Cl` (variables locales statiques) ; les trois
parcours récursifs (compte, copie, suppression d'un arbre) repassent leurs
variables sur la pile par `#pragma static-locals`, sans quoi le niveau
interne écrase la longueur de chemin du niveau externe. La sortie suit le QUIT ProDOS du démarrage cc65.

Les preuves viennent de [bancs POM2 sans fenêtre](../bench/README.md), qui
partent tous de `dist/A2RETROCMD.po` **tel qu'il sera téléchargé**.
`bench/run.py` joue une session complète — amorçage, navigation, pages,
marquage, copie, déplacement, renommage, verrou refusant la suppression,
changement de type et d'auxtype, création de dossier, suppression,
visionneuses texte et hexadécimale, aide, les deux mires comparées **octet à
octet dans les deux banques**, `/RAM` refait après une DHGR et intact après
une HGR, la fanfare qui se termine seule, l'éditeur, le formateur qui liste
les lecteurs et relance le gestionnaire, enfin un programme Applesoft lancé
par `BASIC.SYSTEM` : **39 contrôles**. `bench/memory.py` mesure le creux de la
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
Bitsy Bye depuis la disquette (A2RETRO.SYSTEM y est à la racine) ; un BIN chargé
en `$0800` écrasait le tampon du talon ; un A2RETRO.HELP ou un A2RETRO.CFG abîmé
pouvait faire écrire n'importe où ; la copie détruisait la cible avant d'avoir
ouvert la source, et pouvait remplacer un dossier vide par un fichier. Le
plus grave, trouvé par la relecture finale et reproduit par `roundtrips.py` :
le talon de lancement ne rendait pas à ProDOS l'entrée d'interruption prise
au démarrage pour la Mockingboard (ProDOS n'en a que quatre, et le vecteur
pointait dans de la mémoire recouverte) ; au troisième aller-retour F/ESC,
A2RC plantait dans le moniteur. `chain.s` appelle désormais `donelib`
(les destructeurs cc65) avant de sauter, et le lanceur fait de
même. Une troisième relecture, centrée sur l'éditeur, les images et la
musique, a encore corrigé : l'éditeur n'avait pas de curseur visible
(`cursor(1)` de conio), un fichier créé par E décalait les marques restaurées
sur d'autres entrées (elles sont effacées dans ce cas), une sauvegarde sur un
volume plein vidait le fichier avant d'échouer (la place est vérifiée avant
le `fopen "wb"` qui tronque), Entrée au milieu d'une ligne laissait
l'ancienne fin à l'écran, les erreurs d'ouverture de l'éditeur disparaissaient
sous le redessin, le lanceur lisait A2RETRO.CODE sans borne sous `$BF00`, le
destructeur de la musique passait après la libération de l'interruption
(priorité 11 dans `music.s`), le visionneur d'images gardait un index périmé
si le dossier changeait sous lui, et un .MB sans END faisait lire l'AUX
au-delà du flux. `explore2.py` couvre l'éditeur (raccourcir, sans CR final,
LF seuls, fichier verrouillé), les marques en fenêtre pleine et en seconde
fenêtre, le déplacement vers /RAM et la suppression d'un arbre de 150
fichiers.
