#!/usr/bin/env python3
"""Decode Unicode escapes (\\uXXXX) in a file to readable text.

Usage:
  python decode_unicode.py <file>
  python decode_unicode.py log.txt
  python decode_unicode.py log.txt -o decoded.txt
  type log.txt | python decode_unicode.py -
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Match \uXXXX (and optional \\uXXXX when doubly escaped in logs)
UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def decode_unicode_escapes(text: str) -> str:
    """Replace \\uXXXX with the corresponding character.

    Also tries JSON parse when the whole content (or a clear JSON substring)
    is valid JSON, which correctly handles \\n, \\\" etc.
    """
    stripped = text.strip()
    if stripped:
        # Whole file is a JSON string / object / array
        try:
            parsed = json.loads(stripped)
            return json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass

        # Common log shape: prefix + JSON body=...
        for marker in ("body=", " body=", "payload=", " data="):
            idx = text.find(marker)
            if idx < 0:
                continue
            candidate = text[idx + len(marker) :].strip()
            # Trim trailing non-JSON noise on the same line if any
            try:
                parsed = json.loads(candidate)
                head = text[: idx + len(marker)]
                return head + json.dumps(parsed, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                # Try from first { or [
                for start_ch in ("{", "["):
                    j = candidate.find(start_ch)
                    if j < 0:
                        continue
                    try:
                        parsed = json.loads(candidate[j:])
                        head = text[: idx + len(marker)] + candidate[:j]
                        return head + json.dumps(parsed, ensure_ascii=False, indent=2)
                    except json.JSONDecodeError:
                        continue

    # Fallback: only expand \uXXXX (leave other escapes alone)
    def repl(m: re.Match[str]) -> str:
        return chr(int(m.group(1), 16))

    return UNICODE_ESCAPE_RE.sub(repl, text)


def read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    data = Path(path).read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def main() -> int:
    configure_stdio()
    parser = argparse.ArgumentParser(
        description="Decode \\uXXXX Unicode escapes in a file to Chinese/UTF-8 text."
    )
    parser.add_argument(
        "file",
        help="Input file path, or '-' to read stdin",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write result to this file (default: stdout)",
    )
    args = parser.parse_args()

    if args.file != "-" and not Path(args.file).is_file():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 2

    raw = read_input(args.file)
    decoded = decode_unicode_escapes(raw)

    if args.output:
        args.output.write_text(decoded, encoding="utf-8")
        print(f"Wrote: {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(decoded)
        if not decoded.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
