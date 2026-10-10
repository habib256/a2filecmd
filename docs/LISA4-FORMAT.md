# LISA 8/16 v4/v5 : aperçu des sources

`LISAV4` lit les sources ProDOS INT (type $FA) aux $4000–$5FFF.
Return propose ce lecteur quand l’en-tête est plausible ; `!` → Development
→ LISAV4 permet de le choisir manuellement. Il fonctionne sur les éditions
6502 et 65C02 d’A2FC : il affiche le texte du source, sans exécuter le code
6502/65C02/65816 qu’il contient.

## Structure et rendu

L’en-tête de 16 octets contient version, fin de table des symboles, nombre
de symboles, tabulations des opcodes/opérandes/commentaires et CPU cible.
Version, CPU et octets réservés ne pilotent pas l’exécution du lecteur.
Chaque symbole contient sa longueur (incluant longueur et NUL), ses
caractères et un NUL final. Les références sont des index sur 16 bits ;
la casse suit l’encodage LISA. Le lecteur exige que la table se termine
exactement à la position annoncée avec le nombre annoncé de symboles.

Le corps contient des lignes compactes ou à longueur explicite. Le lecteur
restitue mnémoniques standard v4/v5, macros `_nom`, labels locaux `^n`,
commentaires et lignes d’erreur `!`. Il gère nombres décimaux, hexadécimaux
et binaires sur 8/16/24/32 bits, chaînes, opérateurs, références coercées
`:A`/`:L` et les 16 modes d’adressage. Les décimaux sur 32 bits sont affichés
sans signe : `$FFFFFFFF` donne `4294967295`.

Les tabulations du fichier sont respectées ; les longues lignes se replient
sur l’écran texte. Space/Down avance d’une page, ESC revient. Un EOF physique
à la fin d’une ligne complète est accepté, comme le marqueur zéro suivi
éventuellement de remplissage zéro. Un octet non nul après ce marqueur,
une ligne incomplète ou une référence hors table sont refusés.

## Préservation et limites

Lecture seule : buffers MAIN, table des symboles et écran texte. Aucun
fichier temporaire, écriture disque ou reconstruction du disque `/RAM`.
Une passe valide tout le fichier et sa fermeture **avant** tout affichage.
La seconde passe rouvre la source ; les erreurs d’ouverture, lecture et
fermeture restent des erreurs, pas une fin normale. Une taille périmée
venant du panneau n’est pas utilisée pour borner la lecture.

La table encodée est limitée à **2816 octets**, le fichier à 65535 octets
et chaque ligne explicite à 126 octets de contenu. Le nombre de symboles
est borné par la longueur validée de leur table. Les jetons inconnus,
notamment le rare $FB non défini dans le décodeur de référence, sont refusés.
Les autres dialectes et grandes tables restent à qualifier. Le stockage
MAIN compact permet la lecture sur les deux CPU sans toucher aux données
auxiliaires ; aucun plafond mémoire n’a été relevé.

## Qualification

Les deux sources publiques du volume de tests CiderPress II sont lues :

| Source | Aux | Octets | Symboles | Table encodée |
| --- | --- | ---: | ---: | ---: |
| DETOKEN.A | $50E1 | 14752 | 134 | 1344 |
| MNEMONICS.A | $50E1 | 20569 | 315 | 2185 |

Les tests exécutent le vrai C sur l’hôte et sous sim65 sur les deux CPU,
avec ces deux sources, un index de symbole supérieur à 255, les 16 modes,
les mnémoniques comparés à la table primaire CiderPress et des résultats
littéraux attendus pour nombres/macros/chaînes. Ils couvrent troncatures,
tables incohérentes, limites de buffers, EOF, jetons invalides, annulation,
tailles périmées et erreurs d’ouverture/lecture/fermeture. Les octets sources
sont comparés après chaque appel.

Le banc POM2 utilise seulement un volume jetable. Il vérifie Return et `!`,
la première ligne décodée des deux fichiers réels, la seconde banque d’index
de symboles, les nombres 24/32 bits, le refus d’un mauvais symbole, la mémoire
auxiliaire, la garde de pile et le volume complet après synchronisation.
[Résultat mesuré](corpus/2026-10-10-lisa4.json) : 13/13 contrôles par CPU.
Cette qualification **n’est pas** une comparaison exhaustive à l’écran
original de LISA 8/16 ; elle ne certifie pas toutes les versions de l’éditeur.

```sh
python3 tools/test_lisa4.py
A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh python3 bench/lisa4.py
A2FC_BUILD=build A2FC_PRESET=iie python3 bench/lisa4.py
```

Sources primaires : [CiderPress II, LisaAsm.cs](https://github.com/fadden/CiderPress2/blob/main/FileConv/Code/LisaAsm.cs),
[notes LISA](https://github.com/fadden/CiderPress2/blob/main/FileConv/Code/LisaAsm-notes.md)
et les sources originales `DETOKEN.A` / `MNEMONICS.A` du
[volume de tests public](https://github.com/fadden/CiderPress2/tree/main/TestData/fileconv).
Les tables/règles adaptées sont créditées dans `data/licenses/NOTICE.TXT`.
Le dépôt ne redistribue pas les disquettes originales.
