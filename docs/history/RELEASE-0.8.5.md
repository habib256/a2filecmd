# Qualification de la 0.8.5

Publiée le 13 septembre 2026 depuis le commit `7d6c025`, tag `v0.8.5`.
Première release où **A2FC Mini porte le numéro de l’édition ProDOS** : la
ligne `A2FC_VERSION` du Makefile produit `build-mini/version.inc` pour le
splash, et `mkmini33.py`, les bancs Mini et le nom de la disquette lisent la
même ligne. Cette passe prolonge [BUG-HUNT-0.8.0.md](BUG-HUNT-0.8.0.md).

## Périmètre

Tout le travail en attente depuis la 0.8.0 est entré dans cette révision
(voir la section 0.8.5 du [CHANGELOG](../../CHANGELOG.md)) : lecteur DUET,
DOSGET dans FILES/XL, IDENT/FIXTYPES, durcissement UNSHRINK, chasse aux bugs
du système de fichiers Mini, feuilletage lo-res, page des catégories du
menu `!`. Aucun plafond mémoire n’est relevé ; aucun nouvel accès AUX.

## Validation locale

- `make test` : **650 tests hôtes** dans 70 suites, tous réussis, dont les 66
  tests sim65 de la Mini.
- Constructions 65C02 et 6502, contrôles de disposition actifs.
  Réserves au lien (65C02/6502) : MAIN 23/518, carte langage 14/6, LOWRAM
  245/270, écart avant pile 51/735, OPEN 11/43, DELETE 4/3, IMGFS 5/13,
  UNSHRINK 9/29. La Mini finit à `$94F2`, 270 octets sous DOS.
- `tools/check_images.py` : 7/7 images vérifiées ;
  `release_notes.py --check-tag v0.8.5` accepte le numéro.
- POM2, `bench/smoke.py` : la disquette BOOT 6502 démarre sur les panneaux
  et affiche `A2 FILE CMD 0.8.5` sur IIe non enhanced et IIe enhanced.
- POM2, cœur NMOS II+, disquette `A2FC-MINI-DOS33-0.8.5.dsk` :
  `bench/mini33.py` (amorçage, ergonomie, aucune écriture),
  `bench/mini33_ops.py` (tags, HGR, création, suppression, copie marquée) et
  `bench/mini33_write.py` (annulation, protection, disque échangé refusé,
  copie binaire vérifiée, collision, BLOAD/SAVE DOS, garde de pile) passent ;
  les images jetables sont conservées octet pour octet.
- Manuel PDF régénéré (17 pages, 10 signets).

## Ce qui n’a pas été refait

Les 219 contrôles POM2 de la passe 0.8.0 (pile, catalogues malformés,
préservation et consentement AUX, navigation multimédia, grands
répertoires, PT3, configuration et déplacements groupés) ne sont pas
réexécutés ici ; les bancs GitHub `bench` restent conditionnés à un exécuteur
POM2 auto-hébergé. Pas de qualification sur matériel réel de cette
révision, ni pour la Mini sur un II+ physique.

## Publication

La CI de `main` puis celle du tag ont construit les sept images ProDOS, le
manuel et les empreintes. La disquette Mini ne peut pas être construite sur
l’exécuteur (aucun DOS 3.3 amorçable dans le dépôt) : elle est construite
localement avec `make mini-disk MINI_MASTER=<DOS 3.3 amorçable>`, comparée
au binaire de la CI, puis jointe à la release avec `SHA256SUMS-0.8.5.txt`
complété de sa ligne.

## Décision

Pas de défaut d’exécution confirmé dans ce périmètre. La priorité suivante
est de retrouver la marge résidente 65C02 (23 octets) avant tout
enrichissement : voir [TODO.md](../../TODO.md).
