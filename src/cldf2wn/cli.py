"""Command line interface for cldf2wn."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .convert import read_dataset
from .ili import build_mapping, load_mapping, write_mapping
from .lmf import Metadata, write_dataset

logger = logging.getLogger("cldf2wn")

DEFAULT_MAPPING = Path(__file__).resolve().parents[2] / "data" / "concepticon-ili.tsv"


def _build_map(args: argparse.Namespace) -> int:
    concepts = build_mapping(args.concepticon, args.cili)
    write_mapping(args.output, concepts)
    linked = sum(1 for c in concepts if c.linked)
    print(f"{args.output}: {len(concepts)} concept sets, {linked} linked to an ILI "
          f"({100 * linked / len(concepts):.0f}%)")
    return 0


def _convert(args: argparse.Namespace) -> int:
    if not args.mapping.exists():
        logger.error("no mapping at %s; run `cldf2wn build-map` first", args.mapping)
        return 1
    concepts = load_mapping(args.mapping)

    cldf = args.cldf if (args.cldf / "forms.csv").exists() else args.cldf / "cldf"
    prefix = args.prefix or cldf.parent.name

    doculects, extra_glosses = read_dataset(cldf, concepts)
    if not doculects:
        logger.error("%s: no usable doculects", cldf)
        return 1
    if args.min_forms:
        doculects = [d for d in doculects if len(d.forms) >= args.min_forms]
        if not doculects:
            logger.error("no doculect has at least %d concepts", args.min_forms)
            return 1

    meta = Metadata(
        version=args.version,
        email=args.email,
        license=args.license,
        url=args.url,
        citation=args.citation,
        creator=args.creator,
        description=args.description or f"Converted from the {prefix} CLDF wordlist.",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stats = write_dataset(args.output, doculects, concepts, extra_glosses, prefix, meta)

    total_synsets = sum(s.synsets for s in stats)
    total_linked = sum(s.linked for s in stats)
    print(f"\n{args.output}")
    print(f"  {len(stats)} lexicons, {sum(s.entries for s in stats)} entries, "
          f"{total_synsets} synsets, {total_linked} linked "
          f"({100 * total_linked / total_synsets:.0f}%)" if total_synsets else "  empty")
    if args.verbose:
        print()
        print(f"  {'lexicon':34} {'lang':16} {'entries':>7} {'synsets':>7} {'linked':>7}")
        for stat in stats:
            print(f"  {stat.lexicon_id[:34]:34} {stat.language_tag[:16]:16} "
                  f"{stat.entries:7} {stat.synsets:7} {stat.linked:7}")
    if not args.license:
        logger.warning("no --license given; the output says UNSPECIFIED and cannot "
                       "be redistributed until the source dataset's licence is set")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cldf2wn", description="Convert CLDF wordlists into WN-LMF wordnets."
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="per-lexicon detail")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-map", help="build the Concepticon to ILI mapping")
    build.add_argument("--concepticon", type=Path, required=True,
                       help="clone of concepticon/concepticon-data")
    build.add_argument("--cili", type=Path, required=True,
                       help="clone of globalwordnet/cili")
    build.add_argument("-o", "--output", type=Path, default=DEFAULT_MAPPING)
    build.set_defaults(func=_build_map)

    convert = subparsers.add_parser("convert", help="convert one CLDF wordlist")
    convert.add_argument("cldf", type=Path,
                         help="CLDF dataset directory (or its cldf/ subdirectory)")
    convert.add_argument("-o", "--output", type=Path, required=True)
    convert.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    convert.add_argument("--prefix", help="lexicon id prefix (default: dataset directory name)")
    convert.add_argument("--min-forms", type=int, default=0,
                         help="skip doculects with fewer than this many concepts")
    convert.add_argument("--version", default="0.1")
    convert.add_argument("--email", default="")
    convert.add_argument("--license", default="",
                         help="licence URL of the SOURCE dataset, e.g. "
                              "https://creativecommons.org/licenses/by/4.0/")
    convert.add_argument("--url", default="")
    convert.add_argument("--citation", default="")
    convert.add_argument("--creator", default="")
    convert.add_argument("--description", default="")
    convert.set_defaults(func=_convert)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
