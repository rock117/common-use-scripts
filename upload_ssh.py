"""把本地文件或目录（不递归）上传到 SSH 服务器。

本地路径是文件：只传该文件。
本地路径是目录：只传该目录下一层的文件，不进入子目录。

同名文件：
    --overwrite     覆盖远端同名文件
    不加该选项      远端已存在则改名为 原名.copy；若 .copy 也存在则继续追加 .copy

用法:
    python upload_ssh.py --host 1.2.3.4 --user root --password secret --local C:\\data\\weights --remote /root/upload
    python upload_ssh.py --host 1.2.3.4 --port 46060 --user root --password secret --local C:\\data\\best.pt --remote /root/upload --overwrite
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import paramiko


def connect(host: str, port: int, user: str, password: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        port=port,
        username=user,
        password=password,
        timeout=60,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


def remote_exists(sftp: paramiko.SFTPClient, path: str) -> bool:
    try:
        sftp.stat(path)
        return True
    except OSError:
        return False


def ensure_remote_dir(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    remote_dir = remote_dir.replace("\\", "/").rstrip("/")
    if not remote_dir or remote_dir == "/":
        return
    cur = ""
    for part in remote_dir.split("/"):
        if not part:
            cur = "/"
            continue
        cur = f"{cur.rstrip('/')}/{part}"
        if remote_exists(sftp, cur):
            continue
        print(f"[提示] 远端目录不存在: {cur}，尝试创建...")
        sftp.mkdir(cur)
        print(f"[OK] 已创建: {cur}")


def pick_remote_path(
    sftp: paramiko.SFTPClient,
    remote_dir: str,
    filename: str,
    overwrite: bool,
) -> tuple[str, bool]:
    """返回 (远端路径, 是否因同名而改名)。"""
    dest = f"{remote_dir}/{filename}"
    if overwrite or not remote_exists(sftp, dest):
        return dest, False
    renamed = dest + ".copy"
    while remote_exists(sftp, renamed):
        renamed += ".copy"
    return renamed, True


def local_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.is_file())
    raise FileNotFoundError(path)


def upload_one(
    sftp: paramiko.SFTPClient,
    local: Path,
    remote: str,
    index: int,
    total: int,
) -> None:
    size = local.stat().st_size
    print(
        f"[{index}/{total}] 上传 {local.name} ({size / 1e6:.2f} MB) -> {remote}",
        flush=True,
    )
    t0 = time.time()
    last = {"t": 0.0}

    def cb(transferred: int, total: int) -> None:
        now = time.time()
        if transferred != total and now - last["t"] < 0.5:
            return
        last["t"] = now
        elapsed = max(now - t0, 0.001)
        mbps = transferred / elapsed / 1e6
        pct = 100.0 * transferred / total if total else 100.0
        done = transferred / 1e6
        whole = (total or size) / 1e6
        print(
            f"\r  [{index}/{total}] {pct:5.1f}%  {done:.1f}/{whole:.1f} MB  {mbps:.2f} MB/s",
            end="",
            flush=True,
        )

    sftp.put(str(local), remote, callback=cb if size else None)
    elapsed = max(time.time() - t0, 0.001)
    avg = size / elapsed / 1e6
    print(
        f"\n  [{index}/{total}] 完成 {elapsed:.1f}s  平均 {avg:.2f} MB/s",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="上传本地文件/目录到 SSH 服务器（不递归）")
    parser.add_argument("--host", required=True, help="服务器 IP 或域名")
    parser.add_argument("--port", type=int, default=22, help="SSH 端口，默认 22")
    parser.add_argument("--user", required=True, help="用户名")
    parser.add_argument("--password", required=True, help="密码")
    parser.add_argument("--local", required=True, help="本地文件或目录")
    parser.add_argument("--remote", required=True, help="远端目录")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="远端同名文件则覆盖；不加则改名为 原名.copy",
    )
    args = parser.parse_args()

    local = Path(args.local)
    if not local.exists():
        print(f"[错误] 本地路径不存在: {local}")
        return 1

    try:
        files = local_files(local)
    except FileNotFoundError:
        print(f"[错误] 本地路径不存在: {local}")
        return 1

    if not files:
        print(f"[错误] 没有可上传的文件: {local}")
        return 1

    remote_dir = args.remote.replace("\\", "/").rstrip("/")
    if not remote_dir:
        print("[错误] 远端目录不能为空")
        return 1

    print(f"本地: {local}  ({'文件' if local.is_file() else '目录'}，{len(files)} 个文件)")
    print(f"远端: {args.user}@{args.host}:{args.port}{remote_dir}")
    print(f"同名: {'覆盖' if args.overwrite else '不覆盖，加 .copy 后缀'}")

    client = connect(args.host, args.port, args.user, args.password)
    try:
        sftp = client.open_sftp()
        try:
            ensure_remote_dir(sftp, remote_dir)
            total = len(files)
            for i, path in enumerate(files, start=1):
                dest, renamed = pick_remote_path(sftp, remote_dir, path.name, args.overwrite)
                if renamed:
                    print(f"[提示] 远端已有同名文件，改为: {dest}")
                upload_one(sftp, path, dest, i, total)
        finally:
            sftp.close()
    finally:
        client.close()

    print(f"全部完成，共 {len(files)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
