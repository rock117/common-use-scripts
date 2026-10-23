"""用训练好的模型对视频推理，输出带检测框的标注视频。

用法:
    python detect_video.py --weights best.pt --video-dir video --out-dir output
    python detect_video.py --weights best.pt --videos rod1.mp4 rod2.mp4 --out-dir output
    python detect_video.py --weights best.pt --videos a.mp4 --conf 0.5 --labels person car
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
from ultralytics import YOLO

VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm"}


def resolve_class_ids(model: YOLO, labels: list[str] | None) -> list[int] | None:
    """把标签名解析为 class id；未指定则返回 None（表示全部类别）。"""
    if not labels:
        return None

    name_to_id = {name: i for i, name in model.names.items()}
    ids: list[int] = []
    missing: list[str] = []
    for label in labels:
        if label in name_to_id:
            ids.append(name_to_id[label])
        else:
            missing.append(label)

    if missing:
        available = ", ".join(f"{i}:{n}" for i, n in sorted(model.names.items()))
        print(f"[错误] 未知标签: {', '.join(missing)}")
        print(f"可用标签: {available}")
        raise SystemExit(1)

    return ids


def process(
    model: YOLO,
    video_path: Path,
    out_dir: Path,
    conf: float,
    class_ids: list[int] | None,
) -> None:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"[错误] 无法打开 {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_path = out_dir / f"{video_path.stem}_annotated.mp4"
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    predict_kw: dict = {"conf": conf, "verbose": False}
    if class_ids is not None:
        predict_kw["classes"] = class_ids

    n = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        results = model.predict(frame, **predict_kw)
        writer.write(results[0].plot())
        n += 1
        if n % 100 == 0:
            print(f"  {video_path.name}: 已处理 {n} 帧")

    cap.release()
    writer.release()
    print(f"完成: {out_path}（共 {n} 帧）")


def resolve_videos(video_dir: Path | None, videos: list[Path] | None) -> list[Path]:
    """解析待处理视频列表：--videos 优先；否则扫描 --video-dir。"""
    if videos:
        paths: list[Path] = []
        for p in videos:
            if p.is_file():
                paths.append(p)
            elif video_dir and (video_dir / p).is_file():
                paths.append(video_dir / p)
            else:
                print(f"[跳过] 找不到视频: {p}")
        return paths

    if video_dir is None or not video_dir.is_dir():
        return []

    return sorted(
        p for p in video_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="用 YOLO 对视频推理并输出标注视频")
    parser.add_argument(
        "--weights",
        type=Path,
        required=True,
        help="模型权重路径，如 best.pt",
    )
    parser.add_argument(
        "--video-dir",
        type=Path,
        default=None,
        help="视频所在目录；未指定 --videos 时扫描该目录下全部视频",
    )
    parser.add_argument(
        "--videos",
        type=Path,
        nargs="+",
        default=None,
        help="指定视频文件（可用绝对/相对路径，或相对 --video-dir 的文件名）",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("output"),
        help="标注视频输出目录，默认 output",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.4,
        help="置信度阈值，默认 0.4",
    )
    parser.add_argument(
        "--labels",
        nargs="+",
        default=None,
        help="只标注这些类别名；不指定则标注全部",
    )
    args = parser.parse_args()

    if not args.weights.exists():
        print(f"[错误] 权重不存在: {args.weights}")
        return

    if args.videos is None and args.video_dir is None:
        print("[错误] 请指定 --video-dir 或 --videos")
        return

    if args.video_dir is not None and not args.video_dir.is_dir():
        print(f"[错误] 视频目录不存在: {args.video_dir}")
        return

    video_paths = resolve_videos(args.video_dir, args.videos)
    if not video_paths:
        print("[错误] 没有可处理的视频")
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(args.weights))
    class_ids = resolve_class_ids(model, args.labels)

    print(f"权重: {args.weights}")
    print(f"输出: {args.out_dir}")
    print(f"置信度: {args.conf}")
    if class_ids is None:
        print(f"标签: 全部 ({', '.join(model.names.values())})")
    else:
        print(f"标签: {', '.join(args.labels)} -> ids {class_ids}")
    print(f"视频数: {len(video_paths)}")

    for path in video_paths:
        process(model, path, args.out_dir, args.conf, class_ids)


if __name__ == "__main__":
    main()
