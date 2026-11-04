"""从 SSH 服务器下载文件或目录（不递归）到本地。

远端路径是文件：只下该文件。
远端路径是目录：只下该目录下一层的文件，不进入子目录。

同名文件：
    --overwrite     覆盖本地同名文件
    不加该选项      本地已存在则改名为 原名.copy；若 .copy 也存在则继续追加 .copy

用法:
    python download_ssh.py --host 1.2.3.4 --user root --password secret --remote /root/upload --local C:\\data\\weights
    python download_ssh.py --host 1.2.3.4 --port 46060 --user root --password secret --remote /root/upload/best.pt --local C:\\data --overwrite
    # host/port/user/password 可省略，缺省读同目录 .env（SSH_HOST / SSH_PORT / SSH_USER / SSH_PASSWORD）
    python download_ssh.py --remote /root/upload --local C:\\data\\weights
"""
from __future__ import annotations

import argparse
import stat
import time
from pathlib import Path

import paramiko

ENV_PATH = Path(__file__).resolve().parent / ".env"


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    """读取 KEY=VALUE 格式的 .env（忽略空行与 # 注释）。"""
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            env[key] = value
    return env


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
    parser.add_argument("--host", default=None, help="服务器 IP 或域名；缺省读 .env 的 SSH_HOST")
    parser.add_argument("--port", type=int, default=None, help="SSH 端口；缺省读 .env 的 SSH_PORT，再默认 22")
    parser.add_argument("--user", default=None, help="用户名；缺省读 .env 的 SSH_USER")
    parser.add_argument("--password", default=None, help="密码；缺省读 .env 的 SSH_PASSWORD")
    parser.add_argument("--remote", required=True, help="远端文件或目录")
    parser.add_argument("--local", required=True, help="本地保存目录")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="本地同名文件则覆盖；不加则改名为 原名.copy",
    )
    args = parser.parse_args()

    env = load_env()
    host = args.host or env.get("SSH_HOST") or ""
    user = args.user or env.get("SSH_USER") or ""
    password = args.password or env.get("SSH_PASSWORD") or ""
    port_raw = args.port if args.port is not None else (env.get("SSH_PORT") or "22")
    try:
        port = int(port_raw)
    except ValueError:
        print(f"[错误] 无效端口: {port_raw}")
        return 1

    missing = [
        name
        for name, value in (
            ("--host / SSH_HOST", host),
            ("--user / SSH_USER", user),
            ("--password / SSH_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        print(f"[错误] 缺少连接参数: {', '.join(missing)}（可写在命令行或 {ENV_PATH}）")
        return 1

    remote = args.remote.replace("\\", "/").rstrip("/")
    if not remote:
        print("[错误] 远端路径不能为空")
        return 1

    local_dir = Path(args.local)
    print(f"远端: {user}@{host}:{port}{remote}")
    print(f"本地: {local_dir}")
    print(f"同名: {'覆盖' if args.overwrite else '不覆盖，加 .copy 后缀'}")

    client = connect(host, port, user, password)
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
