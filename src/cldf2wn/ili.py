"""Build and load the Concepticon to interlingual-index mapping.

Concepticon itself carries no wordnet links, but one of its conceptlists does.
`Borin-2015-1532` is the Intercontinental Dictionary Series concept list with a
hand-made mapping to Princeton WordNet senses added by Lars Borin, giving
`PWN_SYNSET` for 1,373 concept sets. Running those offsets through the
Collaborative Interlingual Index turns them into ILIs.

That chain is the whole trick:

    Concepticon_ID -> Borin-2015-1532 -> PWN 3.0 synset -> ILI

Building it needs local clones of two repositories:

    git clone https://github.com/concepticon/concepticon-data
    git clone https://github.com/globalwordnet/cili

The result is small enough to ship, so `data/concepticon-ili.tsv` is committed and
users do not need either clone.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

BORIN_LIST = "concepticondata/conceptlists/Borin-2015-1532.tsv"
CONCEPTICON_TSV = "concepticondata/concepticon.tsv"
CILI_MAP = "ili-map-pwn30.tab"

#: Concepticon's ontological category, used to guess a part of speech for concepts
#: that never reach an English synset. Concepticon's own inventory is small.
CATEGORY_POS: dict[str, str] = {
    "Person/Thing": "n",
    "Action/Process": "v",
    "Property": "a",
    "Number": "a",
    "Classifier": "n",
    "Class": "n",
    "Other": "n",
}


@dataclass(frozen=True)
class Concept:
    """One Concepticon concept set, with whatever wordnet link it has."""

    id: str
    gloss: str
    semantic_field: str
    ontological_category: str
    ili: str
    pos: str

    @property
    def linked(self) -> bool:
        return bool(self.ili)


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def synset_key(synset: str) -> str:
    """Turn a Borin synset like 'n04401088' into a CILI key like '04401088-n'."""
    return f"{synset[1:]}-{synset[0]}" if synset else ""


def build_mapping(concepticon: Path, cili: Path) -> list[Concept]:
    """Join Concepticon, the Borin conceptlist and CILI into one table.

    Args:
        concepticon: clone of concepticon/concepticon-data
        cili: clone of globalwordnet/cili

    Returns:
        Every Concepticon concept set, with `ili` filled in where one was found.

    Raises:
        FileNotFoundError: if either clone is missing the files we need.
    """
    ili_of: dict[str, str] = {}
    with (cili / CILI_MAP).open(encoding="utf8") as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2:
                ili_of[parts[1].strip()] = parts[0].strip()
    logger.info("loaded %d PWN 3.0 to ILI mappings", len(ili_of))

    pwn_of: dict[str, str] = {}
    unresolved = 0
    for row in _read_tsv(concepticon / BORIN_LIST):
        concept_id, synset = row.get("CONCEPTICON_ID"), row.get("PWN_SYNSET", "").strip()
        if not concept_id or not synset:
            continue
        ili = ili_of.get(synset_key(synset), "")
        if ili:
            pwn_of[concept_id] = f"{ili}\t{synset[0]}"
        else:
            unresolved += 1
    if unresolved:
        logger.warning("%d PWN offsets did not resolve against CILI", unresolved)

    concepts: list[Concept] = []
    for row in _read_tsv(concepticon / CONCEPTICON_TSV):
        packed = pwn_of.get(row["ID"], "")
        ili, _, pos = packed.partition("\t")
        concepts.append(
            Concept(
                id=row["ID"],
                gloss=row.get("GLOSS", ""),
                semantic_field=row.get("SEMANTICFIELD", ""),
                ontological_category=row.get("ONTOLOGICAL_CATEGORY", ""),
                ili=ili,
                pos=pos or CATEGORY_POS.get(row.get("ONTOLOGICAL_CATEGORY", ""), "n"),
            )
        )
    logger.info(
        "%d concept sets, %d linked to an ILI",
        len(concepts),
        sum(1 for c in concepts if c.linked),
    )
    return concepts


def write_mapping(path: Path, concepts: list[Concept]) -> None:
    """Write the mapping as a TSV that `load_mapping` can read back."""
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            ["CONCEPTICON_ID", "GLOSS", "SEMANTIC_FIELD", "ONTOLOGICAL_CATEGORY", "ILI", "POS"]
        )
        for concept in sorted(concepts, key=lambda c: int(c.id)):
            writer.writerow(
                [
                    concept.id,
                    concept.gloss,
                    concept.semantic_field,
                    concept.ontological_category,
                    concept.ili,
                    concept.pos,
                ]
            )


def load_mapping(path: Path) -> dict[str, Concept]:
    """Read a mapping written by `write_mapping`, keyed by Concepticon id."""
    concepts: dict[str, Concept] = {}
    for row in _read_tsv(path):
        concepts[row["CONCEPTICON_ID"]] = Concept(
            id=row["CONCEPTICON_ID"],
            gloss=row["GLOSS"],
            semantic_field=row["SEMANTIC_FIELD"],
            ontological_category=row["ONTOLOGICAL_CATEGORY"],
            ili=row["ILI"],
            pos=row["POS"] or "n",
        )
    return concepts
