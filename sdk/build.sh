#!/bin/sh
# build.sh -- compiler une surcouche d'un tiers pour A2 File Cmd en un
# A2FILE/NOM.PLG. Exemple : ./sdk/build.sh sdk/hello.c HELLO
#
# La surcouche n'est PAS liée avec le programme : on compile le C, puis on
# lie avec ld65 sur sdk/plugin.cfg et la bibliothèque apple2enh (pour la
# pile C, le zéro-page et les fonctions d'appui). crt0 n'est pas tiré : rien
# ne référence son point de démarrage. Le résultat est un BIN brut, à poser
# sous A2FILE/ (type ProDOS $06, adresse $1B00) à côté d'A2FILE.CODE.

set -e
src="${1:-sdk/hello.c}"
name="${2:-HELLO}"
here="$(cd "$(dirname "$0")" && pwd)"
out="${OUT:-$here/../build}"
target=apple2enh

# La bibliothèque cible : réglable par CC65_LIB, sinon déduite du chemin de
# cc65 (../share/cc65/lib à côté du binaire, l'agencement habituel).
lib="${CC65_LIB:-$(dirname "$(command -v cc65)")/../share/cc65/lib/$target.lib}"
[ -f "$lib" ] || { echo "apple2enh.lib introuvable ; posez CC65_LIB=/chemin/apple2enh.lib" >&2; exit 1; }

mkdir -p "$out"
base="$out/$name"                     # intermediaires nommes d'apres la surcouche
cc65 -t "$target" -O -Oirs -Cl --codesize 100 -o "$base.s" "$src"
ca65 -t "$target" -o "$base.o" "$base.s"
ld65 -C "$here/plugin.cfg" -o "$out/$name.PLG" "$base.o" "$lib"
echo "$out/$name.PLG : $(wc -c < "$out/$name.PLG") octets, a poser sous A2FILE/$name.PLG"
