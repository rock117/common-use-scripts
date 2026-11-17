#!/usr/bin/env python3
"""统计目录内的文件数量与总大小。

用法:
  python dir_stats.py
  python dir_stats.py <directory>
  python dir_stats.py ./storage
  python dir_stats.py ./storage --depth 1
  python dir_stats.py ./storage --depth 2 --ext .jpg,.png
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Stats:
    files: int = 0
    size: int = 0
    dirs_scanned: int = 0
    skipped: int = 0


def human_size(num: int) -> str:
    """把字节数格式化为易读单位（1 KB = 1024 B）。"""
    if num < 1024:
        return f"{num} B"
    size = float(num)
    for unit in ("KB", "MB", "GB", "TB", "PB"):
        size /= 1024
        if size < 1024 or unit == "PB":
            return f"{size:.2f} {unit}"
    return f"{num} B"


def parse_exts(raw: str | None) -> set[str] | None:
    """解析 --ext：支持逗号/空格分隔，如 .jpg,.png / jpg png。

    返回 None 表示不过滤（统计所有文件）。
    """
    if not raw:
        return None
    exts: set[str] = set()
    for item in raw.replace(",", " ").split():
        ext = item.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        exts.add(ext)
    return exts or None


def scan(
    root: Path,
    *,
    depth: int | None,
    exts: set[str] | None,
    verbose: bool,
    stats: Stats,
) -> None:
    """遍历 root 统计文件。

    depth 语义与 find -maxdepth 一致：
      1 = 只统计 root 下的直接文件
      2 = 再包含一层子目录
      None = 不限深度，统计所有子孙目录
    """
    # (目录, 当前层级)，root 自身为第 1 层
    stack: list[tuple[Path, int]] = [(root, 1)]

    while stack:
        current, level = stack.pop()
        stats.dirs_scanned += 1
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except OSError as exc:
            stats.skipped += 1
            if verbose:
                print(f"[skip] {current}: {exc}", file=sys.stderr)
            continue

        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    # 超出深度限制的子目录不再进入
                    if depth is None or level < depth:
                        stack.append((Path(entry.path), level + 1))
                    continue

                # 只统计普通文件；符号链接、设备文件等跳过
                if not entry.is_file(follow_symlinks=False):
                    continue

                if exts is not None and Path(entry.name).suffix.lower() not in exts:
                    continue

                stats.files += 1
                stats.size += entry.stat(follow_symlinks=False).st_size
            except OSError as exc:
                stats.skipped += 1
                if verbose:
                    print(f"[skip] {entry.path}: {exc}", file=sys.stderr)


def configure_stdio() -> None:
    """Prefer UTF-8 on Windows consoles so Chinese output renders correctly."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def print_report(
    *,
    root: Path,
    depth: int | None,
    exts: set[str] | None,
    stats: Stats,
) -> None:
    line = "─" * 64
    print(line)
    print(f"  目录 : {root}")
    if depth is None:
        print("  深度 : 不限（所有子孙目录）")
    else:
        print(f"  深度 : {depth} 层（find -maxdepth {depth}）")
    if exts is not None:
        print(f"  类型 : {', '.join(sorted(exts))}")
    print(line)
    print(f"  文件 : {stats.files:,} 个")
    print(f"  大小 : {human_size(stats.size)}（{stats.size:,} 字节）")
    if stats.skipped:
        print(f"  跳过 : {stats.skipped} 项（无权限或读取失败）")
    print(line)


def main() -> int:
    configure_stdio()

    parser = argparse.ArgumentParser(
        description="统计目录内的文件数量与总大小。"
    )
    parser.add_argument(
        "directory",
        type=Path,
        nargs="?",
        default=Path("."),
        help="要统计的根目录（默认当前目录）",
    )
    parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=None,
        metavar="N",
        help="扫描深度：1=仅当前目录，2=含一层子目录；默认不限",
    )
    parser.add_argument(
        "-e",
        "--ext",
        metavar="EXTS",
        help="只统计指定扩展名，逗号或空格分隔，如 .jpg,.png",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="打印因权限或读取错误而跳过的路径",
    )
    args = parser.parse_args()

    root: Path = args.directory
    if not root.is_dir():
        print(f"Error: not a directory: {root}", file=sys.stderr)
        return 2
    if args.depth is not None and args.depth < 1:
        print("Error: --depth must be >= 1", file=sys.stderr)
        return 2

    stats = Stats()
    try:
        scan(
            root,
            depth=args.depth,
            exts=parse_exts(args.ext),
            verbose=args.verbose,
            stats=stats,
        )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130

    print_report(
        root=root.resolve(),
        depth=args.depth,
        exts=parse_exts(args.ext),
        stats=stats,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
