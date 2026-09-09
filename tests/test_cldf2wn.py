"""Tests for cldf2wn.

No network and no populated wn database are needed. The one integration test
writes into a temporary wn data directory.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from cldf2wn.convert import Attestation, Doculect, attestation_of, read_dataset
from cldf2wn.ili import Concept, build_mapping, load_mapping, synset_key, write_mapping
from cldf2wn.lmf import Metadata, write_dataset

# --- fixtures ---------------------------------------------------------------

CONCEPTS = {
    "1": Concept("1", "SUN", "The physical world", "Person/Thing", "i100", "n"),
    "2": Concept("2", "TO GO", "Motion", "Action/Process", "i200", "v"),
    "3": Concept("3", "FIREWOOD", "The house", "Person/Thing", "", "n"),
}


def _write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def cldf(tmp_path: Path) -> Path:
    """A minimal but realistic CLDF wordlist directory."""
    directory = tmp_path / "demo" / "cldf"
    directory.mkdir(parents=True)
    _write_csv(
        directory / "languages.csv",
        [
            {"ID": "Alpha", "Name": "Alpha", "Glottocode": "alph1234", "ISO639P3code": "aaa"},
            {"ID": "Beta", "Name": "Beta", "Glottocode": "beta1234", "ISO639P3code": ""},
            {"ID": "Empty", "Name": "Empty", "Glottocode": "", "ISO639P3code": ""},
        ],
        ["ID", "Name", "Glottocode", "ISO639P3code"],
    )
    _write_csv(
        directory / "parameters.csv",
        [
            {"ID": "p1", "Name": "sun", "Concepticon_ID": "1", "Chinese_Gloss": "太阳"},
            {"ID": "p2", "Name": "go", "Concepticon_ID": "2", "Chinese_Gloss": ""},
            {"ID": "p3", "Name": "firewood", "Concepticon_ID": "3", "Chinese_Gloss": "柴"},
            {"ID": "p4", "Name": "unmapped", "Concepticon_ID": "", "Chinese_Gloss": ""},
            {"ID": "p5", "Name": "unknown", "Concepticon_ID": "9999", "Chinese_Gloss": ""},
        ],
        ["ID", "Name", "Concepticon_ID", "Chinese_Gloss"],
    )
    _write_csv(
        directory / "forms.csv",
        [
            {"ID": "1", "Language_ID": "Alpha", "Parameter_ID": "p1", "Form": "sol", "Value": "sol"},
            # a second form for the same concept: a synonym
            {"ID": "2", "Language_ID": "Alpha", "Parameter_ID": "p1", "Form": "soli", "Value": "soli"},
            # the same form again: must not be duplicated
            {"ID": "3", "Language_ID": "Alpha", "Parameter_ID": "p1", "Form": "sol", "Value": "sol"},
            # the same form for a verb concept: a separate entry
            {"ID": "4", "Language_ID": "Alpha", "Parameter_ID": "p2", "Form": "sol", "Value": "sol"},
            {"ID": "5", "Language_ID": "Alpha", "Parameter_ID": "p3", "Form": "lenn", "Value": "lenn"},
            {"ID": "6", "Language_ID": "Beta", "Parameter_ID": "p1", "Form": "sun", "Value": "sun"},
            # missing forms must be dropped
            {"ID": "7", "Language_ID": "Beta", "Parameter_ID": "p2", "Form": "?", "Value": "?"},
            {"ID": "8", "Language_ID": "Beta", "Parameter_ID": "p3", "Form": "", "Value": ""},
            # concepts with no Concepticon id, or one we do not know
            {"ID": "9", "Language_ID": "Alpha", "Parameter_ID": "p4", "Form": "xxx", "Value": "xxx"},
            {"ID": "10", "Language_ID": "Alpha", "Parameter_ID": "p5", "Form": "yyy", "Value": "yyy"},
            # a language with no usable forms at all
            {"ID": "11", "Language_ID": "Empty", "Parameter_ID": "p1", "Form": "-", "Value": "-"},
        ],
        ["ID", "Language_ID", "Parameter_ID", "Form", "Value"],
    )
    return directory


# --- ili.py -----------------------------------------------------------------


def test_synset_key_reorders_pos() -> None:
    assert synset_key("n04401088") == "04401088-n"


def test_synset_key_of_empty_is_empty() -> None:
    assert synset_key("") == ""


def test_mapping_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "m.tsv"
    write_mapping(path, list(CONCEPTS.values()))
    loaded = load_mapping(path)
    assert loaded == CONCEPTS


def test_build_mapping_joins_the_three_sources(tmp_path: Path) -> None:
    concepticon = tmp_path / "concepticon"
    (concepticon / "concepticondata" / "conceptlists").mkdir(parents=True)
    (concepticon / "concepticondata" / "concepticon.tsv").write_text(
        "ID\tGLOSS\tSEMANTICFIELD\tONTOLOGICAL_CATEGORY\n"
        "1\tSUN\tThe physical world\tPerson/Thing\n"
        "2\tBRAVE\tEmotions and values\tProperty\n",
        encoding="utf8",
    )
    (concepticon / "concepticondata" / "conceptlists" / "Borin-2015-1532.tsv").write_text(
        "CONCEPTICON_ID\tPWN_SYNSET\n1\tn09450163\n2\tn99999999\n", encoding="utf8"
    )
    cili = tmp_path / "cili"
    cili.mkdir()
    (cili / "ili-map-pwn30.tab").write_text(
        "# a comment\ni500\t09450163-n\n", encoding="utf8"
    )

    concepts = build_mapping(concepticon, cili)
    by_id = {c.id: c for c in concepts}
    assert by_id["1"].ili == "i500"
    assert by_id["1"].pos == "n"
    # an offset absent from CILI must not invent a link
    assert by_id["2"].ili == ""
    # and an unlinked concept still gets a part of speech from its category
    assert by_id["2"].pos == "a"


# --- convert.py -------------------------------------------------------------


def test_language_tag_prefers_iso() -> None:
    assert Doculect("x", "X", "alph1234", "aaa").language_tag == "aaa"


def test_language_tag_falls_back_to_private_use_glottocode() -> None:
    assert Doculect("x", "X", "alph1234", "").language_tag == "qaa-x-alph1234"


def test_language_tag_of_last_resort() -> None:
    assert Doculect("x", "X", "", "").language_tag == "qaa"


def test_slug_strips_punctuation() -> None:
    assert Doculect("A b-c.1", "X", "", "").slug == "abc1"


def test_read_dataset_drops_languages_with_no_forms(cldf: Path) -> None:
    doculects, _ = read_dataset(cldf, CONCEPTS)
    assert sorted(d.id for d in doculects) == ["Alpha", "Beta"]


def test_read_dataset_deduplicates_forms(cldf: Path) -> None:
    doculects, _ = read_dataset(cldf, CONCEPTS)
    alpha = next(d for d in doculects if d.id == "Alpha")
    assert [a.written for a in alpha.forms["1"]] == ["sol", "soli"]


def test_read_dataset_ignores_missing_and_unmapped(cldf: Path) -> None:
    doculects, _ = read_dataset(cldf, CONCEPTS)
    beta = next(d for d in doculects if d.id == "Beta")
    assert set(beta.forms) == {"1"}
    alpha = next(d for d in doculects if d.id == "Alpha")
    assert "9999" not in alpha.forms


def test_read_dataset_collects_extra_glosses(cldf: Path) -> None:
    _, extra = read_dataset(cldf, CONCEPTS)
    assert extra["1"] == {"zh": "太阳"}
    assert "2" not in extra  # empty gloss must not be carried


def test_read_dataset_requires_the_cldf_tables(tmp_path: Path) -> None:
    empty = tmp_path / "nothing"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        read_dataset(empty, CONCEPTS)


# --- transcriptions and pronunciation ---------------------------------------


def test_labelled_orthography_becomes_the_written_form() -> None:
    """IDS Hungarian: Form is standard orthography, the alternative is phonemic."""
    row = {"Form": "világ", "AlternativeValues": "wilaag",
           "Transcriptions": "Standard;Phonemic"}
    attestation = attestation_of(row, ipa_dataset=False)
    assert attestation.written == "világ"
    assert attestation.pronunciations == [("Phonemic", "wilaag", True)]


def test_orthography_is_preferred_even_when_it_comes_second() -> None:
    """IDS Estonian labels the phonemic value first and the orthography second."""
    row = {"Form": "maailm", "AlternativeValues": "maailma",
           "Transcriptions": "Phonemic;StandOrth"}
    attestation = attestation_of(row, ipa_dataset=False)
    assert attestation.written == "maailma"
    assert attestation.pronunciations == [("Phonemic", "maailm", True)]


def test_cyrillic_transliteration_counts_as_orthography() -> None:
    row = {"Form": "дуниял", "AlternativeValues": "duniyal",
           "Transcriptions": "CyrillTrans;Phonemic"}
    attestation = attestation_of(row, ipa_dataset=False)
    assert attestation.written == "дуниял"
    assert attestation.pronunciations == [("Phonemic", "duniyal", True)]


def test_phonetic_label_is_not_marked_phonemic() -> None:
    row = {"Form": "lak.33", "Transcriptions": "phonetic"}
    attestation = attestation_of(row, ipa_dataset=False)
    assert attestation.pronunciations == [("phonetic", "lak.33", False)]
    # nothing orthographic was recorded, so the transcription has to serve as the form
    assert attestation.written == "lak.33"


def test_ipa_label_is_normalised_to_lowercase_notation() -> None:
    row = {"Form": "top", "Transcriptions": "IPA"}
    assert attestation_of(row, ipa_dataset=False).pronunciations == [("ipa", "top", False)]


def test_lexibank_forms_double_as_their_own_pronunciation() -> None:
    row = {"Form": "ⁿdjət⁷", "Value": "ⁿdjət⁷"}
    attestation = attestation_of(row, ipa_dataset=True)
    assert attestation.written == "ⁿdjət⁷"
    assert attestation.pronunciations == [("ipa", "ⁿdjət⁷", False)]


def test_unlabelled_non_ipa_dataset_gets_no_pronunciation() -> None:
    assert attestation_of({"Form": "sol"}, ipa_dataset=False).pronunciations == []


def test_missing_form_yields_no_attestation() -> None:
    assert attestation_of({"Form": "?", "Value": ""}, ipa_dataset=True) is None


def test_pronunciation_is_written_to_the_lemma(cldf: Path, tmp_path: Path) -> None:
    doculect = Doculect("L", "L", "", "aaa")
    doculect.forms["1"] = [Attestation("world", [("ipa", "wɜːld", False)])]
    out = tmp_path / "out.xml"
    write_dataset(out, [doculect], CONCEPTS, {}, "demo", Metadata("0.1", "", ""))
    text = out.read_text(encoding="utf8")
    assert '<Pronunciation notation="ipa" phonemic="false">wɜːld</Pronunciation>' in text
    assert "</Lemma>" in text


# --- lmf.py -----------------------------------------------------------------


def _write(cldf: Path, tmp_path: Path, **kwargs: str) -> tuple[Path, list]:
    doculects, extra = read_dataset(cldf, CONCEPTS)
    out = tmp_path / "out.xml"
    meta = Metadata(version="0.1", email=kwargs.get("email", ""),
                    license=kwargs.get("license", ""))
    stats = write_dataset(out, doculects, CONCEPTS, extra, "demo", meta)
    return out, stats


def test_one_lexicon_per_doculect(cldf: Path, tmp_path: Path) -> None:
    _, stats = _write(cldf, tmp_path)
    assert [s.lexicon_id for s in stats] == ["demo-alpha", "demo-beta"]


def test_a_form_used_for_two_parts_of_speech_makes_two_entries(
    cldf: Path, tmp_path: Path
) -> None:
    out, stats = _write(cldf, tmp_path)
    alpha = next(s for s in stats if s.lexicon_id == "demo-alpha")
    # forms: sol(n), soli(n), sol(v), lenn(n) -> 4 entries over 3 synsets
    assert (alpha.entries, alpha.synsets) == (4, 3)
    assert 'partOfSpeech="v"' in out.read_text(encoding="utf8")


def test_linked_count_matches_the_mapping(cldf: Path, tmp_path: Path) -> None:
    _, stats = _write(cldf, tmp_path)
    alpha = next(s for s in stats if s.lexicon_id == "demo-alpha")
    assert alpha.linked == 2  # SUN and TO GO are linked, FIREWOOD is not
    assert round(alpha.linked_percent) == 67


def test_required_attributes_survive_when_empty(cldf: Path, tmp_path: Path) -> None:
    out, _ = _write(cldf, tmp_path)
    text = out.read_text(encoding="utf8")
    assert 'email=""' in text
    assert 'license="UNSPECIFIED"' in text
    assert 'ili=""' in text  # the unlinked FIREWOOD synset


def test_glosses_become_definitions(cldf: Path, tmp_path: Path) -> None:
    out, _ = _write(cldf, tmp_path)
    text = out.read_text(encoding="utf8")
    assert '<Definition language="en">sun</Definition>' in text
    assert '<Definition language="zh">太阳</Definition>' in text


def test_concepticon_id_is_recorded_for_provenance(cldf: Path, tmp_path: Path) -> None:
    out, _ = _write(cldf, tmp_path)
    assert 'dc:identifier="Concepticon:1"' in out.read_text(encoding="utf8")


def test_ids_are_unique_across_the_document(cldf: Path, tmp_path: Path) -> None:
    import xml.etree.ElementTree as ET

    out, _ = _write(cldf, tmp_path)
    ids = [e.get("id") for e in ET.parse(out).getroot().iter() if e.get("id")]
    assert len(ids) == len(set(ids))


def test_markup_in_forms_is_escaped(tmp_path: Path) -> None:
    doculect = Doculect("L", "L & Co", "", "aaa")
    doculect.forms["1"] = [Attestation("a<b"), Attestation("c&d")]
    out = tmp_path / "out.xml"
    write_dataset(out, [doculect], CONCEPTS, {}, "demo", Metadata("0.1", "", ""))
    text = out.read_text(encoding="utf8")
    assert "&amp;" in text and "a<b" not in text


@pytest.mark.integration
def test_output_loads_into_wn(cldf: Path, tmp_path: Path) -> None:
    import wn

    out, _ = _write(cldf, tmp_path, email="a@example.org",
                    license="https://creativecommons.org/licenses/by/4.0/")
    data_dir = tmp_path / "wn_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    wn.config.data_directory = data_dir
    assert wn.config.database_path.is_relative_to(tmp_path)  # isolation
    wn.add(str(out), progress_handler=None)

    alpha = wn.Wordnet(lexicon="demo-alpha:0.1")
    assert len(alpha.synsets()) == 3
    sun = alpha.synsets(ili="i100")
    assert sorted(w.lemma() for w in sun[0].words()) == ["sol", "soli"]
    # the same concept reached from another lexicon by ILI
    beta = wn.Wordnet(lexicon="demo-beta:0.1")
    assert [w.lemma() for w in beta.synsets(ili="i100")[0].words()] == ["sun"]
