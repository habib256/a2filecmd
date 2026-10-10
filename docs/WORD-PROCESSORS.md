# MultiScribe et Apple Writer

Les lecteurs `MULTISCR` et `APPLEWR` utilisent la surcouche, sa BSS, le
buffer MAIN `copy_buf` et l’écran texte. Ils n’écrivent ni fichier ni bloc,
ne décompressent rien en AUX et ne reconstruisent pas `/RAM`. Les sources
sont ouvertes uniquement en `rb`. Une passe complète et une fermeture
réussie précèdent l’affichage ; la seconde passe rouvre la source. Les
échecs de lecture/fermeture sont distingués de la fin normale et des
fichiers malformés. La taille périmée du panneau n’est pas une borne.

## MultiScribe

Échantillons publics Asimov : `multiscribedocs.dsk`, `multiscribe2.dsk`,
`Multiscribe disk 2.dsk`, `MultiScribe Data Disk.dsk`,
`MULTISCRIBE_V2.0_S2.dsk`. Les documents anciens ont le type TXT ($04),
les autres WPF ($0B). Le corpus contient aussi un `FONT.EXAMPLE` BeagleWrite
avec l’en-tête de la seconde variante : compatibilité à qualifier séparément.

| Élément | Variante TXT | Variante WPF |
| --- | --- | --- |
| Signature | `80 19 ?? ?? 01 00 B1 E2 02` | `80 19 ?? ?? 01 00 19 01 86 19 0A 01 14 14` |
| Début du texte | offset 37 | offset 295 |
| Fin de la règle initiale | offset 36 = $02 | offset 294 = $02 |

Les deux octets variables ne sont pas interprétés comme une taille.
Une séquence `$01 police taille style $01` change la typographie ; les
quatre octets suivants sont requis, avec fermeture $01. Une règle dans
le texte commence par $02, possède 27 octets de paramètres et se ferme
par $02. $03 est montré comme un séparateur de ligne, $0D comme un retour,
et $09 comme une tabulation à huit colonnes. Tous les paramètres de style
sont consommés, pas imprimés comme des lettres. Un contrôle inconnu ou une
séquence incomplète provoque un refus avant affichage.

Le rendu est du texte ASCII avec coupure à 79 colonnes, sans police
proportionnelle ni styles graphiques. Le sens détaillé des règles et de
$03 reste à confirmer contre l’original ; leur structure est vérifiée.
La signature n’établit pas à elle seule l’intégrité du document : une fin
survenue au milieu de texte imprimable ne porte pas de marqueur permettant
de prouver une troncature. Les autres versions et encodages sont à étudier.

Référence de recherche : [wpf2txt de prodosfs](https://github.com/nexvium/prodosfs/blob/master/util/wpf2txt).
Le décodeur C est indépendant et ne reprend pas ses suppressions permissives
de contrôles. Les offsets ont été contrôlés sur les octets des documents.

## Apple Writer

Référence : [manuel Apple Writer IIe original](https://www.vintageapple.org/apple_ii/pdf/Minute_Manual_For_Apple_Writer_lle_1983.pdf).
Les exemples réels viennent des disquettes `applewriterii_prodos.dsk`,
`applewriterii.dsk`, `APPLE_WRITER_DOS33.dsk` et `Apple Writer Utilities.DSK`.
Le texte peut avoir le bit haut mis. CR/LF/CRLF sont normalisés ; $0C
est affiché comme un retour. Les contrôles non pris en charge sont refusés.

| Commande seule sur une ligne | Aperçu |
| --- | --- |
| `.LMn`, `.RMn` | marges gauche/droite, dans les 79 colonnes disponibles |
| `.PMn`, `.PM+n`, `.PM-n` | retrait de première ligne relatif à la marge gauche |
| `.LJ`, `.CJ`, `.RJ` | alignement gauche, centré, droit |
| `.FJ` | retour à l’alignement gauche, justification complète non simulée |
| `.FF` | séparateur, pagination physique d’imprimante non simulée |

Les mots sont repliés entre les marges. Un mot dépassant la largeur se
coupe pour rester dans l’écran ; espaces multiples et tabulations sont
normalisés en séparateurs. Les commandes sont insensibles à la casse.
Une commande inconnue, une marge hors écran ou une syntaxe non reconnue
reste visible : pas de suppression silencieuse. Les includes, demandes
interactives, publipostage et programmes WPL ne sont jamais exécutés.
Les en-têtes, pieds, interlignes et paramètres d’impression ne sont pas
reproduits. L’aperçu n’est pas une émulation de l’imprimante.

Le choix automatique exige une commande initiale candidate ou la signature
MultiScribe ; un texte Apple Writer ordinaire reste lisible dans TEXT et peut
être ouvert explicitement dans APPLEWR par `!`.

Sur DOS 3.3, APPLEWR utilise le flux `dos_source.h` avec contrôle de l’identité
de catalogue, des listes T/S, de leurs bornes et des collisions de secteurs.
Le premier NUL termine le texte, puis la passe poursuit la lecture physique
pour détecter ses erreurs. Il ne crée aucun fichier extrait. La carte de
secteurs est limitée à 257 secteurs de données ; un document plus grand est
refusé. L’édition ProDOS lit en flux jusqu’à EOF réel.

## Qualification

- `python3 tools/test_worddocs.py` : vrai C, rendu, deux variantes, troncatures,
  contrôles et commandes malformés, erreurs d’ouverture/lecture/fermeture sur
  les deux passes, tailles de panneau périmées, annulation et octets sources.
  Compilation/exécution sous sim65 6502 et 65C02.
- `python3 bench/worddocs.py` : documents réels MultiScribe, Apple Writer,
  ouverture automatique, pagination et DOS direct ; AUX $1000–$BFFF, plancher
  de pile et octets sources conservés. **10/10 sur chaque CPU POM2**, dont le
  IIe non enhanced 6502. Images jetables seulement.
- Les builds natifs complets passent leurs contrôles de disposition sur les
  deux architectures. APPLEWR conserve 801/616 octets sous $4000 (65C02/6502),
  MULTISCR 6967/6937 ; aucune limite n’a été désactivée.

Les échantillons ne sont pas redistribués. `A2FC_WORDPRO_CORPUS` désigne
le répertoire qui contient `extracted/` ; sa provenance et ses empreintes
sont dans le manifeste du recensement. Qualification matérielle physique
et comparaison typographique complète aux logiciels d’origine restent à faire.
