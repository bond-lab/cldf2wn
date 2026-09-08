#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["wn>=1.1"]
# ///
"""Look one concept up across every converted lexicon.

This is the answer to "how do I merge languages that appear in several
datasets?": you do not. Each doculect stays its own lexicon, and the ILI does the
joining at query time.

    uv run examples/crosswalk.py i116556 out/*.xml
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import wn


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    ili, files = argv[1], argv[2:]

    data_dir = Path(tempfile.mkdtemp()) / "wn_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    wn.config.data_directory = data_dir
    if not wn.config.database_path.is_relative_to(data_dir.parent):
        raise SystemExit("refusing to run: wn is not using the temporary directory")

    for path in files:
        wn.add(path, progress_handler=None)

    found = 0
    for lexicon in wn.lexicons():
        wordnet = wn.Wordnet(lexicon=f"{lexicon.id}:{lexicon.version}")
        for synset in wordnet.synsets(ili=ili):
            forms = [word.lemma() for word in synset.words()]
            if forms:
                found += 1
                print(f"  {lexicon.id[:44]:44} {', '.join(forms)}")
    print(f"\n{ili}: {found} lexicons")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
