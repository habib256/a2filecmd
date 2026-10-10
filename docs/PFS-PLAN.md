# PFS:Plan : valeurs enregistrées et formules

`PFSPLAN` ouvre les feuilles ProDOS **$16 / aux $0004**, profil `Plan  $03B00`,
automatiquement avec Return ou explicitement via `!` → Files → PFSPLAN.
Il affiche les libellés de lignes, les libellés principaux de colonnes et
chaque valeur enregistrée. `Space`, Down ou Return avance ; ESC revient.
Les cellules vides restent visibles (`[blank]`), les résultats de formules
portent `[formula]`. Les formules de lignes et colonnes sont listées après
les valeurs, sans les exécuter ni recalculer les résultats.

## Structure qualifiée

Les six feuilles réelles sont CASH, PRODCOST, SALES, COSTS, BLANK et NEWCOSTS.
Elles contiennent respectivement 16×5, 9×5, 10×4, 8×7, 8×7 et 16×7 cellules.
BLANK et NEWCOSTS sont des modèles avec libellés/formules et cellules vides ;
ils ne sont pas des fichiers sans données structurées.

| Zone | Structure du profil |
| --- | --- |
| En-tête | 1024 octets ; nombres de lignes/colonnes LE aux offsets 0/2, signature de 10 octets à 24 |
| Lignes | Bloc de 512 octets ; quatre octets de disposition, longueur sur un octet et libellé ASCII |
| Colonnes | Bloc de 512 octets ; six octets de disposition, longueur LE comprenant ses deux octets, libellé principal et métadonnées de groupe |
| Cellules | Ordre ligne puis colonne ; six octets par cellule, bloc arrondi au multiple de 512 supérieur |
| Formules | Bloc de 512 octets pour les lignes puis un pour les colonnes ; longueur incluant son octet, 1 = aucune formule |
| Formules propres aux cellules | Bloc de 512 octets nul dans ce profil ; un contenu non nul provoque un refus |
| Paramètres | Dernier bloc de 512 octets, opaque mais intégralement lu |

Une valeur contient cinq octets BCD (dix chiffres), puis un octet d’état.
La position décimale est comptée depuis le début des dix chiffres et
indiquée par les quatre bits bas ; `$10` indique une valeur négative et `$40` un résultat enregistré
de formule. `$20` avec mantisse nulle représente zéro. Une mantisse
`A0 00 00 00 00` avec état 0 ou $40 représente une cellule vide.
Le lecteur produit une chaîne décimale directement, sans calcul flottant,
sans séparateurs de milliers ni arrondi d’impression.

Limites : **32 lignes, 16 colonnes**, libellés et formules contenus chacun
dans leur bloc de 512 octets, texte ASCII, position décimale 0 à 10.
Les autres états numériques, encodages et versions sont refusés.
Les métadonnées de disposition sont opaques ; trois structures de titres
constatées sont bornées et vérifiées, mais les titres de groupes partagés
ne sont pas reproduits. Les colonnes sont donc aussi numérotées C1, C2…
Les styles, formats monétaires et paramètres d’impression restent à traiter.

## Validation et préservation

Une passe complète valide les dimensions, les bornes et fins de tous les
libellés et formules, les nombres BCD, le remplissage nul des zones
structurées, la longueur physique exacte et EOF réel. Une fermeture réussie
précède le premier affichage ; une seconde passe rouvre la source.
Les erreurs d’ouverture, de lecture et de fermeture sont des erreurs d’I/O,
pas des EOF normaux. La taille du panneau ne borne jamais la lecture.

Le lecteur ouvre la source en `rb` et ne dispose d’aucune opération d’écriture.
Seuls les buffers MAIN et l’écran texte normal sont employés : aucun fichier,
volume, banque AUX de données ou `/RAM` n’est modifié ou reconstruit.
L’annulation ferme la source. Ce lecteur ne répare pas les fichiers et ne
vérifie pas le sens mathématique des formules.

## Qualification

Résultat : **7 tests C réussis**, **17/17 contrôles natifs par CPU**
(6502 et 65C02), **42/42 valeurs comparées au logiciel original**.
[Empreintes, périmètre et résultats](corpus/2026-10-10-pfsplan.json).

`tools/test_pfsplan.py` exécute le vrai C sur hôte et sim65 6502/65C02 : six
feuilles réelles, décimales, négatifs, zéros, cellules vides et résultats,
troncatures, dimensions/longueurs/contrôles malformés, I/O sur les deux
passes, tailles périmées, types File/Write/Plan, annulation et octets sources.
`bench/pfsplan.py` vérifie Return et `!`, la pagination, les refus sans sortie
partielle, AUX $1000–$BFFF, la garde de pile et le volume entier synchronisé,
sur des images jetables dans les deux architectures.

`bench/pfsplan_original.py` compare **42 valeurs** visibles de COSTS (lignes
2 à 8, colonnes 1 à 6) et leurs libellés au logiciel original. Il utilise le
clavier normal et conserve les six feuilles octet par octet après
synchronisation. Cette comparaison ne couvre pas les autres pages,
l’ensemble des feuilles, les formules ni la typographie complète.

```sh
python3 tools/test_pfsplan.py
A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh python3 bench/pfsplan.py
A2FC_BUILD=build A2FC_PRESET=iie python3 bench/pfsplan.py
python3 bench/pfsplan_original.py
```

Source primaire : [disques PFS publics](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/integrated/pfs/),
`PFS Plan.po`. [Inventaire séparé](corpus/2026-10-10-pfs-inventory.json).
Les documents et le logiciel original ne sont pas redistribués.
