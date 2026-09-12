# Dernier bug hunt avant la 0.8.0

Cette passe porte sur le candidat local 0.8.0 et conserve les modifications
de travail existantes. Elle prolonge le [bug hunt précédent](BUG-HUNT-0.7.6.md)
et la vérification des [volumes PT3](../src/plugins/pt3lib/README.md).
Aucun commit, tag ou publication ne découle de cette qualification locale.

## Changements et périmètre

- `A2FC_VERSION` passe de 0.7.6 à 0.8.0. README, manuel et documentation des
  bancs utilisent les nouveaux noms ; le PDF est régénéré (14 pages,
  10 signets). La capture historique du manuel reste identifiée 0.7.6.
- Le contrôle des images vérifie désormais le numéro inclus dans le lanceur,
  en plus de leur concordance avec la construction. Une régression refuse
  une ancienne version et un numéro partageant seulement le même préfixe.
- Les octets de ProDOS et BASIC.SYSTEM livrés sont comparés aux fichiers
  sources. Les contrôles des 59 surcouches, des catégories et des images
  DSK/ProDOS restent actifs.
- La revue complémentaire des chemins configuration, déplacements groupés,
  navigation multimédia et chargement PT3 n'a pas identifié de nouveau défaut
  d'exécution confirmé. Les corrections antérieures restent présentes.

Les opérations de cette passe écrivent les produits de construction et les
images temporaires des tests. Elles ne modifient aucun disque personnel.
Les bancs destructifs utilisent des supports jetables ; le corpus GISTDATA
est uniquement lu. Aucun nouveau chemin d'écriture natif ou d'accès à AUX
n'est introduit.

## Validation locale

- `make test` : **396 tests hôtes réussis**, y compris la vérification PT3
  sur deux CPU avec et sans conversion (19 220 lectures synthétiques).
- Constructions 6502 et enhanced réussies, contrôles de disposition actifs.
- `tools/check_images.py` : **7/7 images 0.8.0 vérifiées**.
- `release_notes.py --check-tag v0.8.0` accepte le numéro du candidat.
- Comparaison de tous les fichiers des deux XL avec la qualification 0.7.6 :
  seule la substitution du texte de version change le contenu. Les trois
  fichiers concernés sont le lanceur, le résident et FORMAT.PLG ; chaque
  fichier conserve sa taille et ne diffère que de deux octets.

- Nouvelle campagne de mutations, graine **41725** : **7 140 cas réussis**
  sous ASan/UBSan, sans violation de bornes, blocage ni modification des
  sources. DGR 1 033 ; Extasie 1 011 ; PACKFOT et 816/Paint 1 022 chacun ;
  FONTVIEW 1 011 ; PRINTSHOP 1 022 ; LZ4FH 1 019.

**219 contrôles POM2 réussis**, réexécutés sur les binaires 0.8.0 :

| Banc | IIe non enhanced | IIe enhanced |
| --- | ---: | ---: |
| Pile et opérations récursives | 6/6 | 6/6 |
| Catalogues malformés | 5/5 | 5/5 |
| Préservation des données et consentement AUX | 14/14 | 14/14 |
| Navigation multimédia | 34/34 | 34/34 |
| Grands répertoires et retour au dossier quitté | 9/9 | 9/9 |
| PT3, pause/sortie et modules malformés | 16/16 | 17/17 |
| Configuration et déplacements groupés | 25/25 | 25/25 |
| Total | **109/109** | **110/110** |

Le contrôle PT3 supplémentaire dans le second parcours vérifie le refus sans
Mockingboard avec un préréglage //c. Les tests contrôlent les octets conservés,
les témoins de pile, les collisions, l'annulation, les préférences au redémarrage
et les données auxiliaires selon chaque scénario. Le moteur POM2 utilisé ferme
et vide les écritures HDV avant les comparaisons finales.

Les 73 contrôles de session complète de la passe précédente ne sont pas
comptés comme réexécutés ici. La comparaison exhaustive des fichiers XL
confirme que seuls les textes de version ont changé depuis cette qualification.

Les sept images, le manuel PDF, `RELEASE_NOTES.md` et
`SHA256SUMS-0.8.0.txt` sont préparés dans `dist/`. Les huit fichiers du manifeste
passent la vérification SHA-256. Les anciens produits 0.7.6 sont conservés
localement ; seuls les fichiers portant 0.8.0 figurent dans ce manifeste.

## Décision

**Aucun nouveau défaut d'exécution confirmé ni échec local restant dans ce
périmètre.** Le candidat 0.8.0 est prêt pour la CI sur une révision figée.
Ce résultat n'est pas une publication ni une validation matérielle nouvelle.

## Empreintes et limites

SHA-256 des résidents reconstruits :

- 6502 : `1694ef1d75c5aafa4af1d6e349390592052cdc6077e9a41d00c98321d0847f5c`.
- enhanced : `2420b1c12c29bdca770f70bea0618cd40fe68a9a8eeddc2d97ea1a57a8b70d56`.

La disposition reste inchangée : enhanced MAIN finit à `$BEDB` (5 octets
avant le plafond), LC à `$E000` (aucun octet libre), et le code vivant à
`$BE1F`, sous le plancher de pile `$BE40`. Sur 6502, MAIN finit à `$BCC2`
et LC à `$DFFC`. Aucun contrôle de limite n'a été désactivé.

La CI distante sur une révision figée reste nécessaire avant publication.
Les validations matérielles antérieures sur //c, IIe enhanced et IIe non
enhanced ne sont pas présentées comme de nouveaux essais de ce candidat.
Les tests ne prouvent pas l'absence de tout défaut et ne rendent pas les
écritures physiques ProDOS atomiques en cas de coupure.
