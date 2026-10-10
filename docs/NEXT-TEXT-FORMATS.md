# Magic Window et LISA v3

État et qualification du 10 octobre 2026. `MAGWIN` et `LISAV3` donnent
un aperçu texte paginé. Les sources restent ouvertes en lecture seule ;
aucune écriture de fichier, de secteur ou d'AUX. Les seuls espaces écrits
sont les buffers MAIN de la surcouche, le buffer partagé et l'écran texte.
Le disque `/RAM` est conservé sans besoin de confirmation.

## Magic Window

BIN DOS originaux ou copies ProDOS, de 256 à 49 152 octets. L'en-tête
de 256 octets commence par $8D ; son troisième octet est au moins $20.
Le corps contient du texte à bit haut, des retours chariot et des commandes
d'imprimante. A2FC retire le bit haut et représente les contrôles comme
`^A`, `^N`, `^[`, etc. NUL reste visible comme `^@`, il ne termine pas le
document. Les commandes ne sont jamais envoyées à une imprimante ni exécutées.

Retour reconnaît les candidats BIN dont le nom finit par `.MW` et dont
l'en-tête concorde. `!` permet un autre nom. Le lecteur reprend les bornes
de la longueur réellement lue, indépendamment de la taille du panneau.
Le flux DOS utilise la longueur du BIN et les contrôles de chaînes existants.

Limites : en-tête/pied de page omis ; commandes et styles visibles mais pas
appliqués ; lignes longues repliées à 79 colonnes. Six documents du disque
Magic Window //e ont été lus. Cela ne qualifie pas toutes les éditions du
logiciel. `ULTRATERM NOTES.MW` comporte une zone de contrôles et de texte
apparemment altéré : le lecteur conserve ces octets dans l'aperçu, sans
inventer le passage manquant. Deux autres disquettes téléchargées n'ont
pas été extraites par le lecteur de corpus, qui refuse leur chaîne DOS
non séquentielle ; elles ne sont pas comptées comme documents validés.

## LISA v3 standard

ProDOS INT ($FA), auxiliaire $1000–$3FFF. Deux mots de l'en-tête donnent
les longueurs du code et des symboles. La table doit contenir au maximum
512 entrées de huit octets : six octets compactent huit caractères de
six bits, les deux derniers portent une valeur inutilisée par l'aperçu.
A2FC garde seulement les 3 072 octets compactés et décode les noms à la demande.

Le code combine des instructions courtes et des enregistrements dont la
longueur inclut son propre octet (au maximum 127). Les symboles utilisent
des indices sur neuf bits. Le lecteur affiche mnémoniques standard,
étiquettes normales/locales, macros, chaînes, nombres décimaux/hexadécimaux/
binaires, expressions, modes d'adressage et commentaires. Les tabulations
de listing sont 9, 18 et 40 colonnes. Les chaînes doublent leur délimiteur.

Longueurs, limites d'enregistrement, indices, paramètres numériques,
chaînes et jetons inconnus sont contrôlés avant affichage. La longueur
physique ProDOS doit correspondre aux longueurs déclarées. Si un marqueur
zéro termine le code avant sa limite, seul un remplissage zéro est accepté
jusqu'à cette limite. Les fichiers avec octets supplémentaires sont refusés.

`ANIX.EQUATES` est un dialecte documenté avec une table différente malgré
le même type/auxiliaire : il est refusé explicitement sous ce nom. Son
renommage peut empêcher cette protection ; aucune identification générale
de tous les dialectes ANIX n'est revendiquée. Les sources v4/v5 aux $4000–
$5FFF ont un autre en-tête : LISAV3 les refuse, LISAV4 les lit désormais.
Ne pas confondre le code
listé avec un fichier exécutable.

Deux sources standard réelles sont qualifiées : `LISA3.9` (décodeur original)
et `LISA.MNEMONICS`, issues du corpus de test CiderPress II. La comparaison
complète du listing avec l'éditeur LISA original reste à faire ; les tests
ne constituent pas une preuve d'équivalence sur tous les dialectes.

## Erreurs et qualification

Une première passe lit et valide toute la structure, puis ferme la source
avec succès avant d'effacer l'écran pour l'aperçu. Une seconde passe la
rouvre et affiche le texte. Les échecs d'ouverture, lecture et fermeture
sont distincts d'EOF et signalés, y compris pendant cette seconde passe.
Une annulation du défilement ferme la source sans la modifier.

- Sept tests du vrai C sur l'hôte : contrôles Magic Window, en-têtes,
  limites, troncatures, indices dans les deux banques de symboles, nombres,
  chaînes, macros, commentaires, erreurs d'I/O, tailles périmées et annulation.
- Le même code exécuté par sim65 sur 6502 et 65C02 : documents réels,
  référence au symbole 511 et valeurs 16 bits, sortie identique à l'hôte.
- Banc natif sur images jetables : **10/10 sur chaque CPU**, ouverture automatique des deux formats,
  512 symboles avec passage à la deuxième banque, refus de référence invalide,
  Magic Window DOS, AUX, limite de pile et octets sources conservés.
- Builds complets des deux architectures : tous les contrôles de disposition
  actifs ; [budgets mesurés](MEMORY-BUDGETS.md). IDFORMATS 6502 garde 13 octets,
  donc une prochaine extension devra récupérer de la place ou scinder le code.

Le contrôle dans Magic Window original porte sur les dix libellés du fichier
`PRINTER TEST.MW`, également présents dans le résultat du vrai C. Ce n'est
pas une comparaison pixel à pixel des styles imprimés.
[Résultat mesuré et empreintes](corpus/2026-10-10-nexttext.json).

## Reproduire et sources

```sh
python3 tools/test_nexttext.py
A2FC_BUILD=build A2FC_PRESET=iie python3 bench/nexttext.py
A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh python3 bench/nexttext.py
python3 bench/magic_original.py
```

Le corpus Magic Window est sous `A2FC_NEXT_CORPUS` (par défaut
`/tmp/a2fc-next-corpus`), le corpus ProDOS CiderPress sous
`~/.cache/a2fc/cp2/test-files.po`. Les cas réels hôte peuvent être sautés si
les données manquent ; les bancs natifs exigent leurs fixtures et ne sont
pas alors déclarés réussis. Aucun document ou programme original ajouté au dépôt.

Références primaires : [format Magic Window](https://ciderpress2.com/formatdoc/MagicWindow-notes.html),
[format LISA](https://ciderpress2.com/formatdoc/LisaAsm-notes.html),
[décodeur de référence](https://github.com/fadden/CiderPress2/blob/main/FileConv/Code/LisaAsm.cs),
[corpus de test](https://github.com/fadden/CiderPress2/tree/main/TestData/fileconv)
et [disquettes originales](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/word_processing/magic_window/).
Tables et règles adaptées de CiderPress II, Apache-2.0 ; attribution dans
`data/licenses/NOTICE.TXT`, adaptations A2FC de lecture bornée et de pagination.

LISA v4/v5 a désormais son lecteur séparé `LISAV4` : [format, qualification et limites](LISA4-FORMAT.md).
