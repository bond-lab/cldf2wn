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

#: IDS labels its `Transcriptions` column with a ";"-separated list: the first label
#: describes what is in `Form`, the rest describe `AlternativeValues` in order. These
#: labels name a writing system, so a value carrying one belongs in `writtenForm`.
ORTHOGRAPHIC_LABELS = {"standardorth", "standorth", "standard", "orth",
                       "cyrilltrans", "latintrans", "standardorthtone"}

#: These label a transcription, which belongs in `<Pronunciation>` instead.
PHONETIC_LABELS = {"phonemic", "phonetic", "ipa"}


@dataclass
class Attestation:
    """One attested form, with any transcription recorded alongside it."""

    written: str
    #: (notation, transcription, phonemic) triples for `<Pronunciation>`
    pronunciations: list[tuple[str, str, bool]] = field(default_factory=list)

    def merge(self, other: Attestation) -> None:
        """Fold another attestation of the same written form into this one."""
        for pronunciation in other.pronunciations:
            if pronunciation not in self.pronunciations:
                self.pronunciations.append(pronunciation)


@dataclass
class Doculect:
    """One language in a CLDF dataset, and the forms recorded for it."""

    id: str
    name: str
    glottocode: str
    iso: str
    #: Concepticon id -> attestations
    forms: dict[str, list[Attestation]] = field(default_factory=lambda: defaultdict(list))

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


def _split(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


def attestation_of(row: dict[str, str], ipa_dataset: bool) -> Attestation | None:
    """Turn one forms.csv row into an attestation.

    Where the dataset labels its transcriptions -- IDS does -- an orthographic value
    becomes the written form and a phonemic or phonetic one becomes a pronunciation.
    Lexibank datasets carry no labels but are uniformly IPA, so the form doubles as
    its own pronunciation: there is no orthography to prefer, and marking it as IPA
    is more honest than presenting a transcription as a spelling.
    """
    values = [(row.get("Form") or row.get("Value") or "").strip()]
    values += _split(row.get("AlternativeValues"))
    labels = _split(row.get("Transcriptions"))

    written = ""
    pronunciations: list[tuple[str, str, bool]] = []
    for index, value in enumerate(values):
        if not value or value in MISSING_FORMS:
            continue
        label = labels[index] if index < len(labels) else ""
        key = label.lower()
        if key in PHONETIC_LABELS:
            notation = "ipa" if key == "ipa" else label
            entry = (notation, value, key == "phonemic")
            if entry not in pronunciations:
                pronunciations.append(entry)
        elif not written:
            written = value

    if not written:
        # only transcriptions were recorded, or the dataset labels nothing
        for value in values:
            if value and value not in MISSING_FORMS:
                written = value
                break
    if not written:
        return None
    if ipa_dataset and not pronunciations:
        pronunciations.append(("ipa", written, False))
    return Attestation(written=written, pronunciations=pronunciations)


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

    rows = _read_csv(cldf / "forms.csv")
    # Lexibank datasets segment into BIPA and carry no transcription labels; that
    # combination identifies a wordlist whose forms are IPA throughout.
    ipa_dataset = bool(rows) and "Segments" in rows[0] and "Transcriptions" not in rows[0]
    if ipa_dataset:
        logger.info("%s: forms look like IPA, recording them as pronunciations too",
                    cldf.parent.name)

    kept = skipped = 0
    for row in rows:
        doculect = doculects.get(row.get("Language_ID", ""))
        concept_id = concept_of.get(row.get("Parameter_ID", ""))
        if doculect is None or concept_id is None:
            skipped += 1
            continue
        attestation = attestation_of(row, ipa_dataset)
        if attestation is None:
            skipped += 1
            continue
        existing = next(
            (a for a in doculect.forms[concept_id] if a.written == attestation.written), None
        )
        if existing is None:
            doculect.forms[concept_id].append(attestation)
            kept += 1
        else:
            existing.merge(attestation)
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
