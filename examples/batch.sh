#!/bin/sh
# Convert a set of CLDF wordlists in one go.
#
#   sh examples/batch.sh <directory-of-clones> <output-directory>
#
# Every dataset listed below is CC-BY-4.0; check the licence of anything you add.
set -eu
SRC=${1:?usage: batch.sh SRC OUT}
OUT=${2:?usage: batch.sh SRC OUT}
CC="https://creativecommons.org/licenses/by/4.0/"
mkdir -p "$OUT"

for d in castrosui chenhmongmien suntb yangyi leecaijia hsiuhmongmien \
         starostinhmongmien wanghmongmien starostintujia lamanisoic castrozhuang
do
    [ -d "$SRC/$d" ] || { echo "skip $d (not cloned)"; continue; }
    uv run --with-editable . -- cldf2wn convert "$SRC/$d" -o "$OUT/$d.xml" --license "$CC"
done
