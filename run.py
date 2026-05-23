
import argparse
import json
import sys

from pipeline import RePrompt


def main():
    parser = argparse.ArgumentParser(description="RePrompt — intent-aware prompt improver")
    parser.add_argument("query", nargs="?", help="Raw user query (omit to read from stdin)")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip regex cleanup stage")
    parser.add_argument("--no-spellfix", action="store_true", help="Skip spell-fix stage")
    parser.add_argument("--device", default="auto", help='Device: "auto", "cpu", or "cuda"')
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    if args.query:
        queries = [args.query]
    else:
        queries = [line.strip() for line in sys.stdin if line.strip()]

    if not queries:
        parser.print_help()
        sys.exit(1)

    rp = RePrompt(device=args.device)

    for query in queries:
        result = rp.run(
            query,
            skip_cleanup=args.no_cleanup,
            skip_spellfix=args.no_spellfix,
        )
        indent = 2 if args.pretty else None
        print(json.dumps(result, indent=indent))


if __name__ == "__main__":
    main()
