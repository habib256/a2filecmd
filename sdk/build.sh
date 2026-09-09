#!/bin/sh
# build.sh -- compile a third-party overlay for A2 File Cmd into an
# A2FILE/NAME.PLG. Example: ./sdk/build.sh sdk/hello.c HELLO
#
# The overlay is NOT linked with the program: the C is compiled, then
# linked with ld65 on sdk/plugin.cfg and the apple2enh library (for the C
# stack, the zero page and the support functions). crt0 is not pulled in:
# nothing references its start point. The result is a raw BIN, to be put
# under A2FILE/ (ProDOS type $06, address $1B00) next to A2FILE.CODE.

set -e
src="${1:-sdk/hello.c}"
name="${2:-HELLO}"
here="$(cd "$(dirname "$0")" && pwd)"
out="${OUT:-$here/../build}"
target=apple2enh

# The target library: settable through CC65_LIB, otherwise deduced from the
# path of cc65 (../share/cc65/lib next to the binary, the usual layout).
lib="${CC65_LIB:-$(dirname "$(command -v cc65)")/../share/cc65/lib/$target.lib}"
[ -f "$lib" ] || { echo "apple2enh.lib not found; set CC65_LIB=/path/to/apple2enh.lib" >&2; exit 1; }

mkdir -p "$out"
base="$out/$name"                     # intermediates named after the overlay
cc65 -t "$target" -O -Oirs -Cl --codesize 100 -o "$base.s" "$src"
ca65 -t "$target" -o "$base.o" "$base.s"
ld65 -C "$here/plugin.cfg" -o "$out/$name.PLG" "$base.o" "$lib"
echo "$out/$name.PLG : $(wc -c < "$out/$name.PLG") bytes, to be placed under A2FILE/$name.PLG"
