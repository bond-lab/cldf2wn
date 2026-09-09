"""Write WN-LMF 1.4 documents."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from .convert import Attestation, Doculect, LexiconStats
from .ili import Concept

logger = logging.getLogger(__name__)

DOCTYPE = (
    '<!DOCTYPE LexicalResource SYSTEM '
    '"http://globalwordnet.github.io/schemas/WN-LMF-1.4.dtd">'
)
DC_NAMESPACE = "https://globalwordnet.github.io/schemas/dc/"

#: Attributes the DTD marks #REQUIRED, which must be written even when empty.
REQUIRED_LEXICON_ATTRIBUTES = ("id", "label", "language", "email", "license", "version")


@dataclass(frozen=True)
class Metadata:
    """Lexicon-level metadata shared by every doculect in a dataset."""

    version: str
    email: str
    license: str
    url: str = ""
    citation: str = ""
    creator: str = ""
    description: str = ""


def _attributes(pairs: list[tuple[str, str]]) -> str:
    """Render optional attributes, dropping the empty ones."""
    return "".join(f" {name}={quoteattr(value)}" for name, value in pairs if value)


def _entries_of(
    doculect: Doculect, concepts: dict[str, Concept]
) -> dict[tuple[str, str], tuple[list[str], Attestation]]:
    """Group a doculect's forms into (written form, part of speech) entries.

    The value pairs the Concepticon ids that form expresses -- which become the
    entry's senses -- with a merged attestation carrying its pronunciations. A form
    used for both a noun and a verb concept yields two entries, as WN-LMF requires
    one part of speech per lexical entry.
    """
    entries: dict[tuple[str, str], tuple[list[str], Attestation]] = {}
    for concept_id, attestations in doculect.forms.items():
        pos = concepts[concept_id].pos
        for attestation in attestations:
            key = (attestation.written, pos)
            if key not in entries:
                entries[key] = ([], Attestation(attestation.written))
            concept_ids, merged = entries[key]
            concept_ids.append(concept_id)
            merged.merge(attestation)
    return entries


def write_dataset(
    path: Path,
    doculects: list[Doculect],
    concepts: dict[str, Concept],
    extra_glosses: dict[str, dict[str, str]],
    prefix: str,
    meta: Metadata,
) -> list[LexiconStats]:
    """Write one WN-LMF file holding a Lexicon per doculect.

    Args:
        path: file to write
        doculects: doculects with forms, from `read_dataset`
        concepts: the Concepticon mapping
        extra_glosses: per-concept glosses in other languages
        prefix: lexicon id prefix, normally the dataset name
        meta: shared lexicon metadata

    Returns:
        One `LexiconStats` per doculect written.
    """
    lines: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>', DOCTYPE]
    lines.append(f'<LexicalResource xmlns:dc="{DC_NAMESPACE}">')
    stats: list[LexiconStats] = []

    for doculect in sorted(doculects, key=lambda d: d.id):
        lexicon_id = f"{prefix}-{doculect.slug}"
        entries = _entries_of(doculect, concepts)
        used = sorted(doculect.forms, key=int)
        synset_id = {c: f"{lexicon_id}-s{index:05d}" for index, c in enumerate(used, 1)}

        values = {
            "id": lexicon_id,
            "label": f"{doculect.name} ({prefix})",
            "language": doculect.language_tag,
            "email": meta.email,
            "license": meta.license or "UNSPECIFIED",
            "version": meta.version,
        }
        lines.append(
            "  <Lexicon"
            + "".join(f" {k}={quoteattr(values[k])}" for k in REQUIRED_LEXICON_ATTRIBUTES)
            + _attributes(
                [
                    ("url", meta.url),
                    ("citation", meta.citation),
                    ("dc:creator", meta.creator),
                    ("dc:description", meta.description),
                    ("dc:source", doculect.glottocode),
                ]
            )
            + ">"
        )

        senses = 0
        for index, ((form, pos), (concept_ids, attestation)) in enumerate(
            sorted(entries.items()), 1
        ):
            entry_id = f"{lexicon_id}-e{index:05d}"
            lines.append(f'    <LexicalEntry id="{entry_id}">')
            lemma = f"      <Lemma writtenForm={quoteattr(form)} partOfSpeech=\"{pos}\""
            if not attestation.pronunciations:
                lines.append(lemma + "/>")
            else:
                lines.append(lemma + ">")
                for notation, value, phonemic in attestation.pronunciations:
                    lines.append(
                        f"        <Pronunciation notation={quoteattr(notation)} "
                        f'phonemic="{str(phonemic).lower()}">{escape(value)}'
                        "</Pronunciation>"
                    )
                lines.append("      </Lemma>")
            for position, concept_id in enumerate(sorted(concept_ids, key=int), 1):
                lines.append(
                    f'      <Sense id="{entry_id}-{position}" '
                    f'synset="{synset_id[concept_id]}"/>'
                )
                senses += 1
            lines.append("    </LexicalEntry>")

        linked = 0
        for concept_id in used:
            concept = concepts[concept_id]
            linked += bool(concept.ili)
            lines.append(
                "    <Synset"
                + f' id="{synset_id[concept_id]}" ili={quoteattr(concept.ili)}'
                + f' partOfSpeech="{concept.pos}"'
                + _attributes(
                    [
                        ("dc:identifier", f"Concepticon:{concept.id}"),
                        ("dc:subject", concept.semantic_field),
                    ]
                )
                + ">"
            )
            lines.append(
                f'      <Definition language="en">{escape(concept.gloss.lower())}</Definition>'
            )
            for language, gloss in sorted(extra_glosses.get(concept_id, {}).items()):
                lines.append(
                    f'      <Definition language="{language}">{escape(gloss)}</Definition>'
                )
            lines.append("    </Synset>")

        lines.append("  </Lexicon>")
        stats.append(
            LexiconStats(
                lexicon_id=lexicon_id,
                name=doculect.name,
                language_tag=doculect.language_tag,
                entries=len(entries),
                senses=senses,
                synsets=len(used),
                linked=linked,
            )
        )

    lines.append("</LexicalResource>")
    path.write_text("\n".join(lines) + "\n", encoding="utf8")
    logger.info("wrote %s: %d lexicons", path, len(stats))
    return stats
