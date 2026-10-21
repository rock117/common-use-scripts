#!/usr/bin/env python3
"""Search .docx files under a directory for a given text string.

Usage:
  python search_docx.py <directory> <text>
  python search_docx.py ./storage "关键字"
  python search_docx.py ./storage "hello" -i -c 10
"""

from __future__ import annotations

import argparse
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

W_P = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
W_T = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
W_BR = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}br"

# (zip path, human label). Body first so paragraph numbers match Word body order.
DOCX_TEXT_PARTS = (
    ("word/document.xml", "正文"),
    ("word/header1.xml", "页眉1"),
    ("word/header2.xml", "页眉2"),
    ("word/header3.xml", "页眉3"),
    ("word/footer1.xml", "页脚1"),
    ("word/footer2.xml", "页脚2"),
    ("word/footer3.xml", "页脚3"),
    ("word/footnotes.xml", "脚注"),
    ("word/endnotes.xml", "尾注"),
    ("word/comments.xml", "批注"),
)


@dataclass(frozen=True)
class Paragraph:
    """One Word paragraph (or soft-break line within it)."""

    part: str  # 正文 / 页眉1 / ...
    para_no: int  # 1-based within that part
    line_no: int  # 1-based within that paragraph (soft breaks)
    text: str


@dataclass(frozen=True)
class Match:
    part: str
    para_no: int
    line_no: int
    col: int  # 1-based offset of match within the line
    before: str
    matched: str
    after: str


def _paragraph_lines(para_el: ET.Element) -> list[str]:
    """Split a <w:p> into lines by <w:br>; concatenate <w:t> within each line."""
    lines: list[str] = []
    buf: list[str] = []
    for node in para_el.iter():
        if node.tag == W_T:
            buf.append(node.text or "")
        elif node.tag == W_BR:
            lines.append("".join(buf))
            buf = []
    lines.append("".join(buf))
    return lines


def extract_paragraphs(path: Path) -> list[Paragraph]:
    """Extract paragraphs from a .docx (stdlib only)."""
    paragraphs: list[Paragraph] = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            for part_name, part_label in DOCX_TEXT_PARTS:
                if part_name not in names:
                    continue
                root = ET.fromstring(zf.read(part_name))
                para_no = 0
                for para_el in root.iter(W_P):
                    para_no += 1
                    for line_no, text in enumerate(_paragraph_lines(para_el), 1):
                        paragraphs.append(
                            Paragraph(
                                part=part_label,
                                para_no=para_no,
                                line_no=line_no,
                                text=text,
                            )
                        )
    except zipfile.BadZipFile as exc:
        raise ValueError(f"not a valid docx/zip: {exc}") from exc
    return paragraphs


def iter_docx_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*.docx") if p.is_file() and not p.name.startswith("~$")
    )


def find_matches(
    paragraphs: list[Paragraph],
    needle: str,
    *,
    ignore_case: bool,
    context: int,
) -> list[Match]:
    if not needle:
        return []

    needle_cmp = needle.lower() if ignore_case else needle
    nlen = len(needle_cmp)
    matches: list[Match] = []

    for para in paragraphs:
        if not para.text:
            continue
        search_in = para.text.lower() if ignore_case else para.text
        start = 0
        while True:
            idx = search_in.find(needle_cmp, start)
            if idx < 0:
                break
            left = max(0, idx - context)
            right = min(len(para.text), idx + nlen + context)
            before = para.text[left:idx]
            matched = para.text[idx : idx + nlen]
            after = para.text[idx + nlen : right]
            if left > 0:
                before = "…" + before
            if right < len(para.text):
                after = after + "…"
            matches.append(
                Match(
                    part=para.part,
                    para_no=para.para_no,
                    line_no=para.line_no,
                    col=idx + 1,
                    before=before,
                    matched=matched,
                    after=after,
                )
            )
            start = idx + max(nlen, 1)

    return matches


def format_location(m: Match) -> str:
    """e.g. 正文 第3段  or  正文 第3段/第2行  or  页眉1 第1段."""
    loc = f"{m.part} 第{m.para_no}段"
    if m.line_no > 1:
        loc += f"/第{m.line_no}行"
    loc += f" · 第{m.col}字"
    return loc


def configure_stdio() -> None:
    """Prefer UTF-8 on Windows consoles so Chinese snippets render correctly."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def print_report(
    *,
    root: Path,
    needle: str,
    ignore_case: bool,
    context: int,
    results: list[tuple[Path, list[Match]]],
    scanned: int,
    errors: int,
) -> None:
    line = "─" * 64
    print(line)
    print(f"  关键词 : {needle}")
    print(f"  目录   : {root}")
    print(f"  上下文 : 前后各 {context} 字" + ("（忽略大小写）" if ignore_case else ""))
    print(line)

    if not results:
        print("  （无匹配）")
    else:
        for file_index, (rel, matches) in enumerate(results, 1):
            print(f"\n[{file_index}] {rel}  ·  {len(matches)} 处")
            width = len(str(len(matches)))
            for i, m in enumerate(matches, 1):
                print(f"    {i:>{width}}. [{format_location(m)}]")
                print(f"       {m.before}「{m.matched}」{m.after}")

    print()
    print(line)
    total_matches = sum(len(m) for _, m in results)
    summary = (
        f"  合计 : {total_matches} 处匹配 / {len(results)} 个文件"
        f" / 扫描 {scanned} 个"
    )
    if errors:
        summary += f" / 跳过 {errors} 个"
    print(summary)
    print(line)


def main() -> int:
    configure_stdio()

    parser = argparse.ArgumentParser(
        description="Search .docx files under a directory for text."
    )
    parser.add_argument("directory", type=Path, help="Root directory to search")
    parser.add_argument("text", help="Text to find")
    parser.add_argument(
        "-i",
        "--ignore-case",
        action="store_true",
        help="Case-insensitive match",
    )
    parser.add_argument(
        "-c",
        "--context",
        type=int,
        default=5,
        metavar="N",
        help="Show N characters before/after each match (default: 5)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Also print files that were skipped due to errors",
    )
    args = parser.parse_args()

    root: Path = args.directory
    if not root.is_dir():
        print(f"Error: not a directory: {root}", file=sys.stderr)
        return 2
    if args.context < 0:
        print("Error: --context must be >= 0", file=sys.stderr)
        return 2

    needle = args.text
    files = iter_docx_files(root)
    if not files:
        print(f"No .docx files under: {root}")
        return 0

    results: list[tuple[Path, list[Match]]] = []
    errors = 0
    for path in files:
        try:
            paragraphs = extract_paragraphs(path)
        except Exception as exc:  # noqa: BLE001 - report and continue
            errors += 1
            if args.verbose:
                print(f"[skip] {path}: {exc}", file=sys.stderr)
            continue

        matches = find_matches(
            paragraphs,
            needle,
            ignore_case=args.ignore_case,
            context=args.context,
        )
        if not matches:
            continue

        rel = path.relative_to(root) if path.is_relative_to(root) else path
        results.append((rel, matches))

    print_report(
        root=root.resolve(),
        needle=needle,
        ignore_case=args.ignore_case,
        context=args.context,
        results=results,
        scanned=len(files),
        errors=errors,
    )
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
