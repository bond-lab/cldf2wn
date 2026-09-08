# cldf2wn

Turn CLDF wordlists into wordnets.

Comparative wordlists and wordnets have never talked to each other, despite
describing the same thing. A [CLDF](https://cldf.clld.org) wordlist records which
form a language uses for a concept; a wordnet records which words share a concept
and links that concept across languages. The missing piece is a route from
[Concepticon](https://concepticon.clld.org) concept sets to the
[Collaborative Interlingual Index](https://github.com/globalwordnet/cili).

That route turns out to already exist, unnoticed, inside Concepticon itself.

```
Concepticon_ID  ->  Borin-2015-1532  ->  PWN 3.0 synset  ->  ILI
```

`Borin-2015-1532` is a Concepticon conceptlist: the Intercontinental Dictionary
Series concept list with a hand-made mapping to Princeton WordNet added by Lars
Borin. It gives `PWN_SYNSET` for 1,373 concept sets, and CILI turns those offsets
into ILIs. Nothing about it is specific to any language, so one tool converts any
CLDF wordlist into a WN-LMF wordnet per doculect, loadable by
[`wn`](https://wn.readthedocs.io) and publishable through
[Cygnet](https://github.com/omwn/cygnet).

## What comes out

Twelve datasets, converted and DTD-validated:

| dataset | lexicons | entries | synsets | linked |
|---|--:|--:|--:|--:|
| [IDS](https://ids.clld.org) | 319 | 398,267 | 343,818 | **89%** |
| `lexibank/yangyi` | 76 | 44,395 | 46,658 | 62% |
| `lexibank/suntb` | 51 | 43,718 | 45,951 | 59% |
| `lexibank/lamanisoic` | 41 | 10,504 | 11,011 | 67% |
| `lexibank/chenhmongmien` | 25 | 18,630 | 19,490 | 56% |
| `lexibank/castrozhuang` | 20 | 9,899 | 9,786 | 67% |
| `lexibank/starostinhmongmien` | 20 | 1,810 | 1,810 | 81% |
| `lexibank/castrosui` | 16 | 8,199 | 8,224 | 61% |
| `lexibank/hsiuhmongmien` | 12 | 886 | 904 | 83% |
| `lexibank/wanghmongmien` | 12 | 790 | 738 | 61% |
| `lexibank/starostintujia` | 5 | 506 | 511 | 82% |
| `lexibank/leecaijia` | 1 | 232 | 234 | 76% |

**598 wordnets.** Lexibank has around 192 datasets, so this is a small fraction of
what the same command would produce.

IDS reaches 89% because Borin's mapping *is* the IDS concept list. Any dataset built
on the IDS or Swadesh traditions inherits most of that coverage; the rest land in the
55–85% range, since comparative wordlists concentrate on basic vocabulary, which is
exactly what English WordNet covers best. Across all 4,165 Concepticon concept sets
the link rate is only 32%, so the per-dataset figures are much better than the
mapping's raw coverage would suggest.

## Install and use

```sh
git clone https://github.com/fcbond/cldf2wn
cd cldf2wn
uv run --with-editable . -- cldf2wn --help
```

Convert a dataset:

```sh
git clone https://github.com/lexibank/castrosui
uv run --with-editable . -- cldf2wn -v convert castrosui -o sui.xml \
    --license https://creativecommons.org/licenses/by/4.0/
```

```
16 lexicons, 8199 entries, 8224 synsets, 5047 linked (61%)

lexicon                            lang             entries synsets  linked
castrosui-antangwesternsandong     qaa-x-sand1270       512     516     317
castrosui-banliangyangan           qaa-x-anya1244       502     511     314
...
```

Then use it like any wordnet:

```python
import wn
wn.add("sui.xml")

shuigen = wn.Wordnet(lexicon="castrosui-shuigencentralsandong:0.1")
pandong = wn.Wordnet(lexicon="castrosui-pandong:0.1")

firewood = shuigen.synsets(ili="i116556")[0]
print([w.lemma() for w in firewood.words()])                            # ['ⁿdjət⁷']
print([w.lemma() for w in pandong.synsets(ili="i116556")[0].words()])   # ['ⁿdjat⁷']
print(firewood.definitions())                        # ['firewood', '木柴（柴火）']
```

That last line is the point. A wordlist can tell you Shuigen Sui says `ⁿdjət⁷` for
concept 1234. A wordnet lets you ask what any of fifty languages calls the same
concept, and reach it from English or Chinese.

## The mapping

`data/concepticon-ili.tsv` is committed, so nothing needs to be downloaded to
convert a dataset. It has one row per Concepticon concept set:

```
CONCEPTICON_ID  GLOSS   SEMANTIC_FIELD        ONTOLOGICAL_CATEGORY  ILI       POS
2               DUST    The physical world    Person/Thing          i115039   n
```

To rebuild it — after a Concepticon or CILI release, say:

```sh
git clone https://github.com/concepticon/concepticon-data
git clone https://github.com/globalwordnet/cili
uv run --with-editable . -- cldf2wn -v build-map \
    --concepticon concepticon-data --cili cili
```

At the time of writing that yields 4,165 concept sets, 1,325 with an ILI. Forty-eight
PWN offsets in the Borin list no longer resolve against CILI and are reported.

## Modelling decisions

- **One lexicon per doculect.** A CLDF dataset with 76 Yi varieties becomes 76
  lexicons in one WN-LMF file, each independently loadable.
- **Synsets are Concepticon concept sets.** Every form a doculect records for a
  concept becomes a synonym in that synset — which is what makes the output a
  wordnet rather than a reformatted wordlist. Concepts with no ILI still become
  synsets with `ili=""`, so nothing is dropped.
- **Parts of speech** come from the linked Princeton synset. For unlinked concepts
  they are guessed from Concepticon's `ONTOLOGICAL_CATEGORY`: `Action/Process`
  gives `v`, `Property` gives `a`, everything else `n`.
- **Entries are (written form, part of speech).** A form used for both a noun and a
  verb concept becomes two entries, as WN-LMF requires.
- **Language tags** use ISO 639-3 where the dataset has one. Many do not —
  `castrosui` has none for any of its sixteen doculects — so the fallback is
  `qaa-x-<glottocode>`, using the ISO local-use range with the glottocode kept in a
  private-use subtag rather than inventing a code.
- **Definitions** are the Concepticon gloss, in English. Datasets carrying extra
  gloss columns (`Chinese_Gloss` and friends) get those as additional definitions in
  the right language.
- **Provenance** is kept: the Concepticon id in `dc:identifier`, the semantic field
  in `dc:subject`, the glottocode in the lexicon's `dc:source`.

## Honest limitations

These are thin wordnets, and it is worth being clear about that.

- **No relations.** Wordlists have no hypernymy, meronymy or antonymy, so neither do
  these. What you get is a synset inventory linked to the ILI — everything else has
  to come through the interlingual index.
- **Forms are usually phonetic.** Lexibank stores IPA, so these are wordnets of
  transcriptions, not orthographies. For many of these languages no standard
  orthography exists, which is part of why they were transcribed that way.
- **Concept-level, not sense-level.** A wordlist records one form per concept, so
  polysemy is invisible. Two concepts sharing a form become two entries, not one
  entry with two senses.
- **Coverage follows the concept list.** A 110-item Swadesh dataset yields a
  110-synset wordnet. That is genuinely small, though comparable to the TUFS Basic
  Wordnets (300–950 synsets), which are published and in the Open Multilingual
  Wordnet.
- **Licences are the source's, not this tool's.** `--license` records the *source
  dataset's* licence. Most Lexibank datasets are CC-BY-4.0, but check each one; the
  converter writes `UNSPECIFIED` and warns if you do not pass it.

## Development

```sh
uv run --with-editable . --with pytest --with wn -- pytest tests/ -q
```

22 tests. Neither network nor a populated wn database is needed; the one integration
test writes into a temporary directory.

## Related

- Bond, Vossen, McCrae & Fellbaum (2016), [The Collaborative Interlingual Index](https://aclanthology.org/2016.gwc-1.9/)
- Borin & Forsberg (2014), [Swesaurus; or, The Frankenstein Approach to Wordnet Construction](https://aclanthology.org/W14-0129/)
- Morgado da Costa, Bond & Kratochvíl (2016), Linking and Disambiguating Swadesh Lists, GLOBALEX @ LREC
- Kratochvíl & Morgado da Costa (2022), [Abui Wordnet](https://aclanthology.org/2022.fieldmatters-1.7/)
- Bond, Nomoto, Morgado da Costa & Bond (2020), [TUFS Basic Wordnets](https://aclanthology.org/2020.lrec-1.389/)
- List, Rzymski et al., [Concepticon](https://concepticon.clld.org)

## Licence

MIT for the code. `data/concepticon-ili.tsv` is derived from Concepticon (CC-BY-4.0)
and CILI (CC-BY-4.0) and is redistributed under CC-BY-4.0. Converted output carries
the licence of whichever CLDF dataset it came from.
