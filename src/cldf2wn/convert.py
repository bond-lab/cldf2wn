"""Turn a CLDF wordlist into WN-LMF lexicons, one per doculect."""

from __future__ import annotations

import csv
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .ili import Concept

logger = logging.getLogger(__name__)

#: Values that mean "no form recorded" in practice across Lexibank datasets.
MISSING_FORMS = {"", "?", "-", "--", "n/a", "NA", "∅", "Ø"}

#: Extra gloss columns some datasets carry, mapped to a BCP-47 language code.
GLOSS_COLUMNS: dict[str, str] = {
    "Chinese_Gloss": "zh",
    "English_Gloss": "en",
    "French_Gloss": "fr",
    "German_Gloss": "de",
    "Portuguese_Gloss": "pt",
    "Russian_Gloss": "ru",
    "Spanish_Gloss": "es",
}


@dataclass
class Doculect:
    """One language in a CLDF dataset, and the forms recorded for it."""

    id: str
    name: str
    glottocode: str
    iso: str
    #: Concepticon id -> written forms attested for it
    forms: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    @property
    def language_tag(self) -> str:
        """A BCP-47 tag.

        ISO 639-3 where the dataset gives one. Otherwise `qaa-x-<glottocode>`:
        `qaa` is the ISO range reserved for local use, and the private-use subtag
        keeps the glottocode recoverable instead of inventing a code. Many Lexibank
        datasets have no ISO codes at all -- castrosui has none for any of its
        sixteen doculects -- so this path is the common one, not an edge case.
        """
        if self.iso:
            return self.iso
        if self.glottocode:
            return f"qaa-x-{self.glottocode}"
        return "qaa"

    @property
    def slug(self) -> str:
        """A lexicon-id-safe form of the CLDF language id."""
        return re.sub(r"[^A-Za-z0-9]+", "", self.id).lower() or "lang"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf8") as handle:
        return list(csv.DictReader(handle))


def _concepticon_column(row: dict[str, str]) -> str | None:
    """Datasets name it Concepticon_ID or, occasionally, something close."""
    for column in row:
        if "oncepticon" in column and "Gloss" not in column:
            return column
    return None


def read_dataset(
    cldf: Path, concepts: dict[str, Concept]
) -> tuple[list[Doculect], dict[str, dict[str, str]]]:
    """Read a CLDF wordlist directory.

    Args:
        cldf: a directory holding languages.csv, parameters.csv and forms.csv
        concepts: the Concepticon mapping, used only to ignore unknown ids

    Returns:
        The doculects with their forms, and any extra per-concept glosses found
        (keyed by Concepticon id, then by BCP-47 language code).

    Raises:
        FileNotFoundError: if a required CLDF table is absent.
    """
    for required in ("languages.csv", "parameters.csv", "forms.csv"):
        if not (cldf / required).exists():
            raise FileNotFoundError(f"{cldf} has no {required}")

    parameters = _read_csv(cldf / "parameters.csv")
    if not parameters:
        return [], {}
    column = _concepticon_column(parameters[0])
    if column is None:
        logger.warning("%s: parameters.csv has no Concepticon column", cldf)
        return [], {}

    concept_of: dict[str, str] = {}
    extra_glosses: dict[str, dict[str, str]] = defaultdict(dict)
    present = [c for c in GLOSS_COLUMNS if c in parameters[0]]
    for row in parameters:
        concept_id = row.get(column, "").strip()
        if not concept_id or concept_id not in concepts:
            continue
        concept_of[row["ID"]] = concept_id
        for source in present:
            value = (row.get(source) or "").strip()
            if value:
                extra_glosses[concept_id][GLOSS_COLUMNS[source]] = value
    if present:
        logger.info("%s: carrying extra glosses from %s", cldf.parent.name, ", ".join(present))

    doculects: dict[str, Doculect] = {}
    for row in _read_csv(cldf / "languages.csv"):
        doculects[row["ID"]] = Doculect(
            id=row["ID"],
            name=row.get("Name") or row["ID"],
            glottocode=(row.get("Glottocode") or "").strip(),
            iso=(row.get("ISO639P3code") or "").strip(),
        )

    kept = skipped = 0
    for row in _read_csv(cldf / "forms.csv"):
        doculect = doculects.get(row.get("Language_ID", ""))
        concept_id = concept_of.get(row.get("Parameter_ID", ""))
        if doculect is None or concept_id is None:
            skipped += 1
            continue
        written = (row.get("Form") or row.get("Value") or "").strip()
        if written in MISSING_FORMS:
            skipped += 1
            continue
        if written not in doculect.forms[concept_id]:
            doculect.forms[concept_id].append(written)
            kept += 1
    logger.info("%s: kept %d forms, skipped %d", cldf.parent.name, kept, skipped)

    return [d for d in doculects.values() if d.forms], dict(extra_glosses)


@dataclass
class LexiconStats:
    """What one converted doculect came out as."""

    lexicon_id: str
    name: str
    language_tag: str
    entries: int
    senses: int
    synsets: int
    linked: int

    @property
    def linked_percent(self) -> float:
        return 100 * self.linked / self.synsets if self.synsets else 0.0
