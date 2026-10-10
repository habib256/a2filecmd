# PFS:File : formulaire et fiches actives

`PFSFILE` lit les bases ProDOS de type `$16`, auxiliaire `$0001`,
portant le discriminateur `A2CD00`. Return choisit le lecteur ; le suffixe
`.PFS` n’est pas requis. Un choix explicite existe dans `!` → Files.
Space/Down/Return avancent dans le texte, ESC revient aux panneaux.

Chaque fiche affiche son numéro dans la liste, son identifiant interne,
puis les noms des champs et leurs valeurs. Le formulaire donne les noms :
une valeur est associée au nom situé à sa gauche sur la même ligne.
Sans nom correspondant, sa position `[x,y]` reste affichée. Les adresses
multilignes sont restituées, avec une indentation simple. Ce lecteur ne
reproduit pas la mise en page imprimée et ne calcule aucun rapport.

## Structure qualifiée

Les règles résultent de l’examen des deux bases publiques et d’une
comparaison limitée au logiciel original. Elles ne décrivent pas toutes
les versions de PFS:File.

| Position dans l’en-tête | Interprétation utilisée, mots little endian |
| --- | --- |
| 0 / 2 | Cellule du formulaire, deux valeurs identiques |
| 4 | Version constatée : 1 |
| 6 | Nombre de fiches actives |
| 8 / 10 | Première / dernière cellule de fiche |
| 16–21 | `A2CD00` |

Une cellule occupe **128 octets physiques** : 126 octets de contenu et
un pointeur 16 bits vers la continuation. Le formulaire et les fiches
commencent au-delà des 64 premières cellules ; index et zones libres
restent opaques. Une même cellule ne peut appartenir à deux chaînes.

Le contenu assemblé commence par un en-tête de 12 octets : état constaté
`0, 0, 1`, identifiant et liens précédent/suivant. Le formulaire utilise
l’identifiant `$BD98` et n’a pas de liens de fiches. Seule la liste active
est affichée : modèles de recherche, fiches supprimées et résidus ne sont
pas présentés comme des enregistrements actifs.

Chaque champ porte une longueur paire incluant quatre octets d’en-tête
(longueur, x, y), puis une valeur terminée par NUL. `$04` peut remplir le
dernier octet avant ce NUL. `$01` et son octet de disposition introduisent
la ligne suivante ; cet octet de disposition est omis dans la prévisualisation.
Les autres contrôles bas restent visibles (`^B`…). Les octets à bit haut,
DEL, NUL intérieurs et structures inconnues sont refusés dans ce profil.
Un champ de longueur zéro termine le contenu ; le remplissage restant
doit être nul.

## Validation et préservation

Tous les octets physiques sont lus, indépendamment de la taille du panneau.
Le formulaire et toute la liste active sont ensuite validés : continuations,
blocs partagés, cycles, liens retour, nombre de fiches, dernière fiche,
longueurs des champs, coordonnées et terminaisons. La source est fermée
avec succès avant tout affichage, puis rouverte pour la lecture paginée.
Les erreurs d’ouverture, de lecture, de recherche et de fermeture sont
signalées comme erreurs d’I/O, jamais comme EOF normal.

Seuls la mémoire principale et l’écran texte normal sont employés.
Aucun fichier, volume ou stockage auxiliaire `/RAM` n’est écrit ou reconstruit.
L’annulation ferme la source. Les limites actuelles sont explicites :
**256 KiB par fichier**, **8 cellules / 1008 octets de contenu par formulaire
ou fiche**, **32 noms de champs**, x inférieur à 80 et y inférieur à 128.
Un dépassement provoque un refus, sans sortie partielle lors de la validation.
Les index et listes de blocs libres ne sont pas vérifiés comme par un outil
de réparation : ce lecteur valide les chaînes nécessaires à la consultation.

## Documents et qualification

Le [corpus PFS séparé](corpus/2026-10-10-pfs-inventory.json) contient deux
bases distinctes :

| Document | Taille | Fiches actives | Noms de champs |
| --- | ---: | ---: | ---: |
| STAFF.PFS | 16384 | 8 | 11 |
| COSTFILE.PFS | 24576 | 41 | 7 |

Les huit tests exécutent le vrai C sur hôte et sim65 6502/65C02, avec les
deux bases réelles. Ils couvrent les champs multiblocs, les bases vides,
les limites, les liens cassés/partagés/cycliques, les troncatures et erreurs
d’I/O, les types File/Write/Plan, les tailles périmées et l’annulation.
Chaque source est comparée octet par octet après l’appel.

`bench/pfsfile.py` utilise un volume jetable dans A2FC : Return, `!`, valeurs
nommées, adresses multilignes, pagination, refus, AUX, garde de pile et
volume entier après synchronisation. Les deux architectures sont construites
avec leurs contrôles de disposition actifs.

Résultat : **14/14 contrôles sur 6502 et 14/14 sur 65C02**, sources,
mémoire auxiliaire et garde de pile conservées. Les empreintes des deux
bases et des binaires qualifiés figurent dans le
[compte rendu reproductible](corpus/2026-10-10-pfsfile.json).

`bench/pfsfile_original.py` compare neuf libellés/valeurs de la première
fiche COSTFILE à PFS:File original. L’API clavier POM2 n’expose pas la touche
Apple : le banc redirige temporairement l’unique lecture du bouton Apple
en mémoire principale, pour un Return, puis restaure l’instruction. Les
routines de lecture/rendu et les octets des bases restent originaux. Cela
ne certifie ni les 49 fiches à l’écran original ni leur typographie complète.
La comparaison passe **9/9**, avec les deux bases originales conservées
octet par octet après synchronisation du volume.

```sh
python3 tools/test_pfsfile.py
A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh python3 bench/pfsfile.py
A2FC_BUILD=build A2FC_PRESET=iie python3 bench/pfsfile.py
python3 bench/pfsfile_original.py
```

Les rapports PFS:Report, les bases anciennes sur disques propres au logiciel,
les autres signatures, styles et feuilles PFS:Plan restent à traiter.
Sources primaires : [disques PFS publics](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/integrated/pfs/),
notamment PFS_REPORT_hr.dsk (STAFF), PFS Plan.po (COSTFILE) et
PFS_FILE_PRODOS_hr.dsk (logiciel original). Aucun document original n’est
redistribué dans le dépôt.
