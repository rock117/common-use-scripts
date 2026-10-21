"""从 SSH 服务器下载文件或目录（不递归）到本地。

远端路径是文件：只下该文件。
远端路径是目录：只下该目录下一层的文件，不进入子目录。

同名文件：
    --overwrite     覆盖本地同名文件
    不加该选项      本地已存在则改名为 原名.copy；若 .copy 也存在则继续追加 .copy

用法:
    python download_ssh.py --host 1.2.3.4 --user root --password secret --remote /root/upload --local C:\\data\\weights
    python download_ssh.py --host 1.2.3.4 --port 46060 --user root --password secret --remote /root/upload/best.pt --local C:\\data --overwrite
"""
from __future__ import annotations

import argparse
import stat
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


def is_remote_dir(mode: int) -> bool:
    return stat.S_ISDIR(mode)


def remote_files(sftp: paramiko.SFTPClient, path: str) -> list[tuple[str, str, int]]:
    """返回 (远端路径, 文件名, 字节数)。目录只列一层文件。"""
    st = sftp.stat(path)
    if not is_remote_dir(st.st_mode):
        name = path.rstrip("/").split("/")[-1]
        return [(path, name, st.st_size)]

    items: list[tuple[str, str, int]] = []
    for attr in sftp.listdir_attr(path):
        if is_remote_dir(attr.st_mode):
            continue
        items.append((f"{path}/{attr.filename}", attr.filename, attr.st_size or 0))
    return sorted(items, key=lambda x: x[1])


def ensure_local_dir(path: Path) -> None:
    if path.is_dir():
        return
    if path.exists():
        raise NotADirectoryError(path)
    print(f"[提示] 本地目录不存在: {path}，尝试创建...")
    path.mkdir(parents=True, exist_ok=True)
    print(f"[OK] 已创建: {path}")


def pick_local_path(dest_dir: Path, filename: str, overwrite: bool) -> tuple[Path, bool]:
    """返回 (本地路径, 是否因同名而改名)。"""
    dest = dest_dir / filename
    if overwrite or not dest.exists():
        return dest, False
    renamed = dest_dir / f"{filename}.copy"
    while renamed.exists():
        renamed = dest_dir / f"{renamed.name}.copy"
    return renamed, True


def download_one(
    sftp: paramiko.SFTPClient,
    remote: str,
    local: Path,
    size: int,
    index: int,
    n_files: int,
) -> None:
    print(
        f"[{index}/{n_files}] 下载 {remote} ({size / 1e6:.2f} MB) -> {local}",
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
        whole_bytes = total or size
        pct = 100.0 * transferred / whole_bytes if whole_bytes else 100.0
        print(
            f"\r  [{index}/{n_files}] {pct:5.1f}%  {transferred / 1e6:.1f}/{whole_bytes / 1e6:.1f} MB  {mbps:.2f} MB/s",
            end="",
            flush=True,
        )

    sftp.get(remote, str(local), callback=cb if size else None)
    elapsed = max(time.time() - t0, 0.001)
    got = local.stat().st_size if local.is_file() else size
    avg = got / elapsed / 1e6
    print(
        f"\n  [{index}/{n_files}] 完成 {elapsed:.1f}s  平均 {avg:.2f} MB/s",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="从 SSH 服务器下载文件/目录到本地（不递归）")
    parser.add_argument("--host", required=True, help="服务器 IP 或域名")
    parser.add_argument("--port", type=int, default=22, help="SSH 端口，默认 22")
    parser.add_argument("--user", required=True, help="用户名")
    parser.add_argument("--password", required=True, help="密码")
    parser.add_argument("--remote", required=True, help="远端文件或目录")
    parser.add_argument("--local", required=True, help="本地保存目录")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="本地同名文件则覆盖；不加则改名为 原名.copy",
    )
    args = parser.parse_args()

    remote = args.remote.replace("\\", "/").rstrip("/")
    if not remote:
        print("[错误] 远端路径不能为空")
        return 1

    local_dir = Path(args.local)
    print(f"远端: {args.user}@{args.host}:{args.port}{remote}")
    print(f"本地: {local_dir}")
    print(f"同名: {'覆盖' if args.overwrite else '不覆盖，加 .copy 后缀'}")

    client = connect(args.host, args.port, args.user, args.password)
    try:
        sftp = client.open_sftp()
        try:
            if not remote_exists(sftp, remote):
                print(f"[错误] 远端路径不存在: {remote}")
                return 1
            try:
                files = remote_files(sftp, remote)
            except OSError as e:
                print(f"[错误] 无法读取远端路径: {remote} ({e})")
                return 1
            if not files:
                print(f"[错误] 没有可下载的文件: {remote}")
                return 1

            kind = "文件" if len(files) == 1 and not is_remote_dir(sftp.stat(remote).st_mode) else "目录"
            print(f"远端类型: {kind}，{len(files)} 个文件")

            try:
                ensure_local_dir(local_dir)
            except NotADirectoryError:
                print(f"[错误] 本地路径已存在且不是目录: {local_dir}")
                return 1

            n_files = len(files)
            for i, (src, name, size) in enumerate(files, start=1):
                dest, renamed = pick_local_path(local_dir, name, args.overwrite)
                if renamed:
                    print(f"[提示] 本地已有同名文件，改为: {dest}")
                download_one(sftp, src, dest, size, i, n_files)
        finally:
            sftp.close()
    finally:
        client.close()

    print(f"全部完成，共 {n_files} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
