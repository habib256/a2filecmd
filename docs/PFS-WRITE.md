# PFS:Write : lecture du texte ProDOS

`PFSWRITE` affiche les documents ProDOS de type `$16`, auxiliaire `$0002`.
Return choisit le lecteur lorsque le type, l’auxiliaire et la longueur
annoncée concordent avec le fichier réellement lu. `!` → Files → PFSWRITE
permet un choix explicite ; un fichier File, Plan ou un module exécutable
PFS est refusé. Le suffixe `.PFS` n’est pas nécessaire.

Le texte est paginé : Space, Down ou Return avancent ; ESC revient aux
panneaux. Les caractères imprimables à bit haut sont rendus en ASCII ;
les contrôles restent visibles en notation `^A`, `^I`, `^L`… Aucun rendu
imprimé, fusion avec une base File, soulignement ou justification n’est
promis. Ainsi la ligne stylée « Agent » d’ANNUAL apparaît `A^Ag^Ae^An^At^A`.

## Structure constatée sur les documents

Il s’agit d’une qualification par échantillons, pas d’une spécification
universelle de toutes les éditions PFS. Les huit contenus Write distincts
ont la structure suivante :

| Position | Interprétation utilisée |
| --- | --- |
| 0–1023 | Paramètres de page et d’impression, ignorés pour le texte |
| 6–7 | Nombre de CR du corps, entier 16 bits little endian |
| 8–9 | Longueur exacte du corps, entier 16 bits little endian |
| 1024–1025 | Début du corps : `$0C $0D` |
| Dernier octet du corps | `$0E`, marque de fin |

Le logiciel original affiche **66 lignes par page**, marges haute/basse
**6**, gauche/droite **10/70**, correspondant aux valeurs d’en-tête des
exemples. Ces paramètres ne sont pas une signature : des paramètres
modifiés ne doivent pas empêcher de lire le texte. Ils restent opaques
pour PFSWRITE, qui ne valide pas leurs valeurs d’impression.

Le lecteur vérifie le corps complet, son compteur de CR, son marqueur de
fin et l’EOF physique, puis ferme la source avant l’affichage. Un NUL,
DEL, `$FF`, une fin `$0E` prématurée, une troncature ou des données après
la fin provoquent un refus. Les autres contrôles sont montrés sans
interprétation. Le corps est borné à **64 511 octets** (65 535 avec l’en-tête).
La taille périmée du panneau ne sert jamais de borne d’entrée.

Les buffers vivent en mémoire principale et utilisent l’écran texte
normal. Aucun volume, fichier source ni banque de stockage auxiliaire
`/RAM` n’est écrit ou reconstruit. Les erreurs d’ouverture, lecture et
fermeture restent distinctes d’une fin de fichier normale.

## Corpus séparé et limites

[Inventaire reproductible](corpus/2026-10-10-pfs-inventory.json) : 28 sources
locales, 17 images uniques lues, une image dupliquée, dix images refusées
par les lecteurs DOS/ProDOS existants. Le convertisseur SHK est inventorié
mais n’est pas décompressé par ce recensement. Les autres refus ne prouvent
pas l’absence de documents : ils concernent des formats non pris en charge
ou une structure que le lecteur borné refuse.

| Auxiliaire du type `$16` | Occurrences après déduplication des images | Contenus distincts | Usage observé |
| --- | ---: | ---: | --- |
| `$0002` | 27 | 8 | Write : NAME, ANNUAL, FLYER, MEMO, LETTER, EXTRA, HOUSE, NILSSON |
| `$0001` | 3 | 2 | File : STAFF.PFS, COSTFILE.PFS, fiches lues par PFSFILE |
| `$0004` | 12 | 6 | Plan : six feuilles B00 lues par PFSPLAN |

Ce corpus supplémentaire n’entre pas dans le recensement général figé
à 1 907 sources. Les occurrences sont des candidats par métadonnées ;
seuls les huit documents Write sont exécutés dans les tests du lecteur.
Les anciennes éditions à disques propres au logiciel, les variantes File non qualifiées,
les rapports et les autres variantes restent ouverts. Les six feuilles Plan
B00 ont un lecteur : [PFSPLAN](PFS-PLAN.md).
La qualification ne compare pas exhaustivement le rendu à celui de
PFS:Write original ; l’écran Define Page a seulement confirmé les réglages.

Les régressions exécutent le vrai C sur hôte et sur les deux sim65 :
huit documents réels, tailles périmées, limites, troncatures, mauvais types,
contrôles, paramètres de page différents, erreurs d’ouverture/lecture/
fermeture, seconde passe et annulation. Chaque source est comparée octet
par octet après lecture. Le banc POM2 utilise un volume jetable et vérifie
Return, `!`, pagination, refus, AUX, garde de pile et volume synchronisé.
[Résultat mesuré](corpus/2026-10-10-pfswrite.json) : **18/18 par CPU**,
soit 36/36 contrôles natifs. Les sept tests hôte/sim65 passent.

```sh
python3 tools/test_pfswrite.py
python3 tools/pfs_census.py --output /tmp/pfs-inventory.json
A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh python3 bench/pfswrite.py
A2FC_BUILD=build A2FC_PRESET=iie python3 bench/pfswrite.py
```

Sources primaires : [disques PFS publiés dans Asimov](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/integrated/pfs/),
[disques Write et Dictionary](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/word_processing/)
et [manuel original PFS:Write](https://mirrors.apple2.org.za/ftp.apple.asimov.net/documentation/applications/pfs%20Write%20Manual.pdf).
Le dépôt conserve des métadonnées et des empreintes, aucun document original.

Le lecteur [PFSFILE](PFS-FILE.md) qualifie désormais les 49 fiches des deux bases File.
