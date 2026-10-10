# Print Shop : bordures et polices BIN / ProDOS $F5

Implémentation et qualification du 10 octobre 2026. `PSBORDER` et `PSFONT`
lisent les fichiers originaux directement sur ProDOS et DOS 3.3, en lecture
seule. `PRINTSHOP` conserve le lecteur de clip art 88×52.

## Bordures

Les BIN ont 144 octets, ou 148 avec un **préfixe de quatre octets**
d'options. Le type auxiliaire est $4800, $5800, $6800 ou $7800. Après le
préfixe éventuel, trois motifs occupent chacun 48 octets : deux banques
de 24 colonnes contenant sept pixels par octet.

Pour le motif `k`, la colonne `x` et la ligne `y` :

```text
offset = prefix + k*48 + x + (y < 7 ? 24 : 0)
masque = 1 << (y % 7)
```

Un bit à 1 donne un pixel marqué. Les trois motifs stockés font 24×14.
L'éditeur Companion n'affiche et n'édite que les 23 premières colonnes ;
le lecteur montre aussi la dernière colonne stockée. L'ancien intitulé
« 12×12 » de la feuille de route était incorrect pour ces fichiers.

L'aperçu présente les trois motifs séparément et les quatre octets d'options
en hexadécimal. Il ne reproduit pas l'assemblage du cadre, les répétitions
ou les inversions définies par ces options.

## Polices

Les BIN chargés à $6000 commencent directement par les tables ; ceux à
$5FF4 ont un préfixe de 12 octets avant les mêmes tables à $6000.
Quatre tables de 59 octets décrivent largeur, hauteur, adresse basse et
adresse haute des caractères ASCII $20–$5A. Le bit haut de largeur est un
indicateur de l'éditeur ; la largeur est `octet & $7F`. Espace n'a pas de
bitmap ; `@` réserve un emplacement graphique externe.

Les adresses sont absolues dans le fichier chargé. Chaque ligne occupe
`(largeur+7)/8` octets, puis commence la suivante. **Le pixel gauche utilise
le bit 7**, suivi du bit 6, etc. Ce sens est confirmé par `FOEDIT` original
et le convertisseur CiderPress II ; la description LSB de ses notes ne
correspond pas à ces fichiers.

Le lecteur accepte jusqu'à 48×64 pixels et 16 384 octets de fichier. Il
valide les bornes de chaque glyphe affichable avant tout aperçu. Les adresses
ne doivent pas viser les tables ni dépasser la longueur réellement lue.
L'éditeur original utilise un canevas de 48×38 ; au moins une police du
corpus comporte des glyphes de 39 lignes. L'aperçu A2FC permet le défilement,
sans réduire verticalement ces glyphes. Gauche/Droite ou Espace change le
caractère, Haut/Bas défile, Échap revient au panneau.

## Reconnaissance et préservation

Retour reconnaît les candidats `BORD.*` avec taille/adresse concordantes
et `FONT.*` avec adresse $6000/$5FF4 ; `!` permet la sélection explicite
pour un autre nom. Le nom et les métadonnées ne constituent qu'une sonde :
le lecteur vérifie ensuite les octets et ignore la taille périmée du panneau.

Les sources sont ouvertes `rb` ou par le flux DOS borné partagé. Aucun fichier
ni secteur n'est écrit. Les buffers et le code restent en MAIN ; seul
l'écran texte est affiché. AUX contenant `/RAM` n'est pas emprunté. Une
erreur d'ouverture, lecture, recherche ou fermeture refuse l'affichage.
La première lecture et sa fermeture précèdent tout aperçu ; chaque glyphe
est relu et fermé avant son affichage. Aucun programme original n'est exécuté
par les lecteurs.

## Qualification et limites

- Vrai C hôte et sim65 sur les deux CPU : six tests, 77 bordures et 36
  polices réelles, deux préfixes, bits, défilement jusqu'à 64 lignes, bornes
  de tous les glyphes, tailles périmées et erreurs d'I/O injectées.
- POM2 natif : **10/10 sur 65C02 et 10/10 sur 6502 NMOS**, Retour automatique
  sur ProDOS/DOS, navigation, refus de pointeur invalide, sources, AUX et
  limite de pile conservées. Les deux builds complets et limites de mémoire
  passent ; mesures dans [MEMORY-BUDGETS.md](MEMORY-BUDGETS.md).
- Original Print Shop Companion sur copies jetables : **77 bordures**, les
  3×23×14 pixels éditables chacune, identiques à l'écran original ; glyphe
  **A des 36 polices** identique. Ce contrôle ne qualifie ni tous leurs
  autres caractères ni la colonne 24 des bordures contre l'écran original.
  [Résultat mesuré](corpus/2026-10-10-printshop.json).

## Variantes ProDOS $F5

`PSBORDER` lit désormais $F5 aux $2000, exactement 264 octets. Après un
préfixe de 12 octets, les trois motifs 24×14 occupent chacun 42 octets,
ligne par ligne, bit fort à gauche :

```text
offset = 12 + k*42 + y*3 + x/8
masque = 128 >> (x & 7)
```

Les 126 derniers octets et les options du préfixe ne sont pas interprétés
par cet aperçu. Assemblage du cadre et masques restent à qualifier.

`PSFONT` lit $F5 aux $1000 : préfixe de 12 octets, puis quatre tables de
95 entrées (largeur, hauteur, pointeur bas, pointeur haut). Les pointeurs
sont relatifs au début des bitmaps, à l’offset 392. Le mot à l’offset 6
annonce leur longueur ; le lecteur exige qu’elle corresponde au fichier
complet lu et fermé. Tous les glyphes internes sont bornés avant affichage.
L’espace n’a pas de bitmap ; `@` réserve un graphique externe et est sauté.
Les entrées vides des polices originales restent visibles avec une taille nulle.

Les 77 bordures jumelles BIN/F5 ont exactement les mêmes 3×24×14 pixels.
Les 36 polices ont le même rendu pour les 57 glyphes internes communs,
avec tous leurs défilements verticaux disponibles. Cette comparaison du
vrai C avec les BIN complète la qualification originale ci-dessus ; elle
n’est pas une comparaison directe à l’écran du logiciel Print Shop ProDOS.
Le vrai C charge 616 651 pixels pour les 2 052 glyphes communs, tous
identiques ; [mesure détaillée](corpus/2026-10-10-printshop-f5.json).
Les 95 entrées sont parcourues dans les tests ; les fichiers malformés,
les tailles périmées et les erreurs de lecture/fermeture restent refusés.

Return propose ces lecteurs avec les noms BORD./FONT. (UFONT est aussi
accepté pour les polices). `!` permet de les choisir sans ce nom. La sélection
est une candidature ; le lecteur vérifie ensuite toute la structure.

## Reproduire et sources

```sh
python3 tools/test_printshop_extras.py
A2FC_BUILD=build A2FC_PRESET=iie python3 bench/printshop_extras.py
A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh python3 bench/printshop_extras.py
python3 bench/printshop_original.py
```

Les bancs natifs et original exigent les données publiques sous
`A2FC_PRINTSHOP_CORPUS`, par défaut `/tmp/a2fc-printshop-corpus`.
Les tests hôte sautent les cas corpus réel si ces données manquent.
Le dépôt ne redistribue ni disquette ni source de Print Shop.

Sources primaires : [disquettes et sources originales Companion/Print Shop](https://mirrors.apple2.org.za/ftp.apple.asimov.net/images/productivity/graphics/printshop/),
`BOEDIT` (SETBORD/GETMASK) et `FOEDIT` (LOADCHAR/MFDOLINE),
[notes techniques CiderPress II](https://ciderpress2.com/formatdoc/PrintShop-notes.html)
et [convertisseur de polices](https://github.com/fadden/CiderPress2/blob/main/FileConv/Gfx/PrintShopFont.cs).
