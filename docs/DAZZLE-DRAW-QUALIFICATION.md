# Dazzle Draw : qualification du 10 octobre 2026

`bench/dazzledraw.py` compare trois images réelles à l'original
`DD.PICLOADER`, exécuté sans modification sous Applesoft dans POM2.
Aucune correction du lecteur d'images d'A2FC n'a été nécessaire.

Corpus local : `132_DAZZLE_DRAW_SLIDE_SHOW.dsk`, volume `/DD.FLIPSIDE`.
Les fichiers ne sont pas redistribués avec le dépôt. Le banc convertit
l'ordre DOS en blocs ProDOS pour les lire, puis place des copies dans
des volumes jetables. Il conserve les types BIN `$06`, aux `$2000`,
longueur 16 384 ; le chargeur conserve son type BAS `$FC`, aux `$0801`.

| Fichier | SHA256 |
| --- | --- |
| Disquette du corpus | `38881dfffad0a26e49b2fcbb8a97681491507ec52dedeed0cd01dbec7f0cf8ea` |
| DD.PICLOADER | `591553f848d29a80641e9645eae48d603bdcc5be8ae842fbcf7ac4757ff7f533` |
| MONARCH | `6e0bc4269e7d0c84397b7c6622e3a7b671725980d7dbad701fab30a8d4630f51` |
| ROOM | `88515b51f8403e7834e5315d81e0398317b5db853a21b82b966ab8a08f4d6d68` |
| SCREEN.SHOE | `354ac8c81c3aad81db0816ddfe7448c2a4a4990e6190b97281125610d981dee1` |

Le chargeur d'origine charge la première moitié en AUX `$2000-$3FFF`,
puis la seconde en MAIN `$2000-$3FFF`. Le banc vérifie d'abord ces deux
banques complètes contre chaque fichier, puis compare les banques d'A2FC
au résultat de l'original. Il compare également les sorties `/screen.ppm`
de POM2 : tous les octets du rendu correspondent.

Résultats : **14/14 en IIe enhanced / 65C02**, **14/14 en IIe non enhanced /
6502**. Pour chaque image, Retour et I donnent les mêmes banques et le
même rendu que l'original. Les deux autres contrôles vérifient qu'un
`/RAM` non vide demande confirmation avant modification et que N conserve
intacts ses octets AUX `$1000-$BFFF`, sans ouvrir le lecteur. Après
synchronisation et arrêt, les deux volumes jetables restent identiques à
leur état initial ; la disquette source aussi.

Les builds natifs des deux architectures passent leurs contrôles de
disposition. Le résident, IMAGE et OPEN du stage utilisé ont été comparés
aux binaires recompilés : identiques.

```sh
make ARCH=enh disk
make ARCH=6502 disk
A2FC_IMG=A2FILECMD-full python3 bench/dazzledraw.py --out /tmp/dazzledraw-enh.json
A2FC_IMG=A2FILECMD-full A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh \
  python3 bench/dazzledraw.py --out /tmp/dazzledraw-6502.json
```

Le corpus par défaut est dans `~/.cache/a2fc/dazzle/` ; `--corpus` accepte
un autre emplacement. Les deux scénarios sont enregistrés dans
`bench/all.py` avec le corpus comme prérequis explicite.

Cette validation concerne les images plein écran de 16 384 octets et le
rendu émulé. Les sections `.SEC`, les autres variantes et la recette sur
machine physique restent hors de cette vérification.
