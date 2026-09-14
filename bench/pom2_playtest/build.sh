#!/bin/sh
# Builds the headless POM2 test host the benches drive (--ai-control), from
# the source kept here, against the POM2 emulator library. POM2 itself is the
# only outside dependency: point POM2_ROOT at its checkout (default
# ~/src/pom2, with build/libpom2_core.a already made). The binary lands in
# a2filecmd's build/ so that bench/pom2.py finds it without any variable.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../.." && pwd)
pom2_root=${POM2_ROOT:-"$HOME/src/pom2"}
pom2_root=$(CDPATH= cd -- "$pom2_root" && pwd)
out=${1:-"$root/build/pom2_playtest"}
mkdir -p "$(dirname -- "$out")"
c++ -std=c++17 -O2 -DNDEBUG -I"$pom2_root/src" -I"$pom2_root/include" \
    -I"$pom2_root/build/generated" -I"$pom2_root/imgui" \
    -DPOM2_ROOT=\""$pom2_root"\" "${SOURCE:-$here/pom2_playtest.cpp}" \
    "$pom2_root/build/libpom2_core.a" \
    -framework CoreAudio -framework AudioToolbox -framework AudioUnit \
    -o "$out"
echo "$out"
