"""从视频目录抽帧，并把其中已有图片复制到输出目录，供人工标注。

支持两种抽帧方式（二选一）：
    --interval 1.5   每隔多少秒抽 1 帧（默认）
    --every 30       每隔多少帧抽 1 帧

用法:
    python extract_frames.py
    python extract_frames.py --video-dir path\\to\\video --out-dir path\\to\\frames
    python extract_frames.py --interval 2.0
    python extract_frames.py --every 30 --clear
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import cv2

# —— 默认路径（可用命令行覆盖）——
DEFAULT_VIDEO_DIR = Path(
    r"C:\rock\code\ai-test\yolo-detect-electroscope\dataset-by-date\2026-10-21\video"
)
DEFAULT_OUT_DIR = Path(
    r"C:\rock\code\ai-test\yolo-detect-electroscope\dataset-by-date\2026-10-21\frames"
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"}


def list_videos(video_dir: Path) -> list[Path]:
    """列出目录下视频（优先 ASCII 文件名，避免 OpenCV 中文路径问题）。"""
    videos = sorted(
        p for p in video_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )
    ascii_videos = [p for p in videos if p.name.isascii()]
    return ascii_videos if ascii_videos else videos


def list_images(video_dir: Path) -> list[Path]:
    images = sorted(
        p for p in video_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )
    ascii_images = [p for p in images if p.name.isascii()]
    return ascii_images if ascii_images else images


def copy_images(video_dir: Path, out_dir: Path) -> int:
    """把视频目录里的静态图片直接复制到输出目录。"""
    images = list_images(video_dir)
    if not images:
        print("视频目录下没有静态图片需要复制")
        return 0

    copied = 0
    for src in images:
        shutil.copy2(src, out_dir / src.name)
        copied += 1
    print(f"复制图片: {copied} 张")
    return copied


def extract(
    video_path: Path,
    out_dir: Path,
    *,
    interval_sec: float | None = None,
    every: int | None = None,
) -> int:
    """按秒间隔或帧间隔抽帧（二选一）。"""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"[错误] 无法打开视频: {video_path}")
        return 0

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if every is not None:
        step = max(1, every)
        mode_desc = f"每 {step} 帧"
    else:
        assert interval_sec is not None
        step = max(1, round(fps * interval_sec))
        mode_desc = f"每 {interval_sec}s (~{step} 帧)"

    stem = video_path.stem
    saved = 0
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % step == 0:
            out_file = out_dir / f"{stem}_{frame_idx:06d}.jpg"
            cv2.imwrite(str(out_file), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            saved += 1
        frame_idx += 1
    cap.release()
    print(
        f"{video_path.name}: fps={fps:.1f}, 总帧数={total}, "
        f"{mode_desc}, 抽取 {saved} 张"
    )
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="从视频抽帧（按时间或按帧间隔）")
    parser.add_argument(
        "--video-dir",
        type=Path,
        default=DEFAULT_VIDEO_DIR,
        help=f"视频/图片所在目录，默认 {DEFAULT_VIDEO_DIR}",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"抽帧输出目录，默认 {DEFAULT_OUT_DIR}",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="每隔多少秒抽 1 帧（与 --every 二选一；都不写则默认 1.5 秒）",
    )
    parser.add_argument(
        "--every",
        type=int,
        default=None,
        help="每隔多少帧抽 1 帧（与 --interval 二选一）",
    )
    parser.add_argument("--clear", action="store_true", help="抽帧前清空输出目录")
    args = parser.parse_args()

    if args.interval is not None and args.every is not None:
        print("[错误] --interval 与 --every 只能二选一")
        return
    if args.every is not None and args.every < 1:
        print("[错误] --every 至少为 1")
        return
    if args.interval is not None and args.interval <= 0:
        print("[错误] --interval 必须大于 0")
        return

    video_dir = args.video_dir
    out_dir = args.out_dir
    use_every = args.every is not None
    interval = None if use_every else (args.interval if args.interval is not None else 1.5)
    every = args.every if use_every else None

    if not video_dir.is_dir():
        print(f"[错误] 视频目录不存在: {video_dir}")
        return

    if args.clear and out_dir.exists():
        for old in out_dir.iterdir():
            if old.is_file():
                old.unlink()
        print(f"已清空 {out_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"视频目录: {video_dir}")
    print(f"输出目录: {out_dir}")
    if use_every:
        print(f"模式: 每隔 {every} 帧抽 1 张")
    else:
        print(f"模式: 每隔 {interval} 秒抽 1 张")

    n_images = copy_images(video_dir, out_dir)

    videos = list_videos(video_dir)
    if not videos and n_images == 0:
        print(f"[错误] {video_dir} 下没有找到视频或图片")
        return

    total_saved = 0
    if videos:
        print(f"找到 {len(videos)} 个视频")
        for path in videos:
            total_saved += extract(
                path,
                out_dir,
                interval_sec=interval,
                every=every,
            )

    print(
        f"合计: 复制图片 {n_images} + 视频抽帧 {total_saved} "
        f"= {n_images + total_saved} 张，保存在 {out_dir}"
    )


if __name__ == "__main__":
    main()
