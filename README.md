# common-use-scripts

日常开发中常用的 Python 小工具集合。

## 目录

- [环境依赖](#环境依赖)
- [脚本一览](#脚本一览)
- [download_ssh.py](#download_sshpy) — SSH 下载
- [upload_ssh.py](#upload_sshpy) — SSH 上传
- [extract_frames.py](#extract_framespy) — 视频抽帧
- [search_docx.py](#search_docxpy) — Word 全文搜索
- [decode_unicode.py](#decode_unicodepy) — Unicode 转义解码
- [detect-yolo-class.py](#detect-yolo-classpy) — 查看 YOLO 类别

---

## 环境依赖

按需安装：

```bash
pip install paramiko opencv-python torch
```

| 依赖 | 用途 |
|------|------|
| `paramiko` | SSH 上传 / 下载 |
| `opencv-python` | 视频抽帧 |
| `torch` | 读取 YOLO 权重中的类别名 |

---

## 脚本一览

| 脚本 | 用途 |
|------|------|
| [`download_ssh.py`](#download_sshpy) | 从 SSH 服务器下载文件或目录（不递归） |
| [`upload_ssh.py`](#upload_sshpy) | 把本地文件或目录上传到 SSH 服务器（不递归） |
| [`extract_frames.py`](#extract_framespy) | 从视频按时间/帧间隔抽帧，供标注使用 |
| [`search_docx.py`](#search_docxpy) | 在目录下递归搜索 `.docx` 中的关键字 |
| [`decode_unicode.py`](#decode_unicodepy) | 把 `\uXXXX` 等 Unicode 转义解码为可读文本 |
| [`detect-yolo-class.py`](#detect-yolo-classpy) | 打印 YOLO 权重文件中的类别 id 与名称 |

---

## download_ssh.py

从 SSH 服务器下载文件或目录到本地。

- 远端是**文件**：只下载该文件
- 远端是**目录**：只下载该目录下一层文件，**不进入子目录**
- 本地已有同名文件时：默认改名为 `原名.copy`；加 `--overwrite` 则覆盖

```bash
python download_ssh.py --host 1.2.3.4 --user root --password secret --remote /root/upload --local C:\data\weights
python download_ssh.py --host 1.2.3.4 --port 46060 --user root --password secret --remote /root/upload/best.pt --local C:\data --overwrite
```

| 参数 | 说明 |
|------|------|
| `--host` | 服务器 IP 或域名 |
| `--port` | SSH 端口，默认 `22` |
| `--user` | 用户名 |
| `--password` | 密码 |
| `--remote` | 远端文件或目录 |
| `--local` | 本地保存目录 |
| `--overwrite` | 覆盖本地同名文件 |

---

## upload_ssh.py

把本地文件或目录上传到 SSH 服务器。

- 本地是**文件**：只上传该文件
- 本地是**目录**：只上传该目录下一层文件，**不进入子目录**
- 远端已有同名文件时：默认改名为 `原名.copy`；加 `--overwrite` 则覆盖

```bash
python upload_ssh.py --host 1.2.3.4 --user root --password secret --local C:\data\weights --remote /root/upload
python upload_ssh.py --host 1.2.3.4 --port 46060 --user root --password secret --local C:\data\best.pt --remote /root/upload --overwrite
```

| 参数 | 说明 |
|------|------|
| `--host` | 服务器 IP 或域名 |
| `--port` | SSH 端口，默认 `22` |
| `--user` | 用户名 |
| `--password` | 密码 |
| `--local` | 本地文件或目录 |
| `--remote` | 远端目录 |
| `--overwrite` | 覆盖远端同名文件 |

---

## extract_frames.py

从视频目录抽帧，并把目录中已有图片一并复制到输出目录，方便人工标注。

抽帧方式二选一：

- `--interval`：每隔多少秒抽 1 帧（都不写时默认 `1.5` 秒）
- `--every`：每隔多少帧抽 1 帧

```bash
python extract_frames.py
python extract_frames.py --video-dir path\to\video --out-dir path\to\frames
python extract_frames.py --interval 2.0
python extract_frames.py --every 30 --clear
```

| 参数 | 说明 |
|------|------|
| `--video-dir` | 视频/图片所在目录 |
| `--out-dir` | 抽帧输出目录 |
| `--interval` | 按秒间隔抽帧 |
| `--every` | 按帧间隔抽帧 |
| `--clear` | 抽帧前清空输出目录 |

---

## search_docx.py

在指定目录下递归查找 `.docx`，搜索正文、页眉页脚、脚注、批注等中的关键字，并输出带上下文的匹配位置。

```bash
python search_docx.py ./storage "关键字"
python search_docx.py ./storage "hello" -i -c 10
```

| 参数 | 说明 |
|------|------|
| `directory` | 要搜索的根目录 |
| `text` | 要查找的文本 |
| `-i` / `--ignore-case` | 忽略大小写 |
| `-c` / `--context N` | 匹配前后各显示 N 个字符，默认 `5` |
| `-v` / `--verbose` | 打印因错误跳过的文件 |

---

## decode_unicode.py

把文件或标准输入中的 `\uXXXX` Unicode 转义解码为可读 UTF-8 文本；若内容是合法 JSON，会优先按 JSON 解析并美化输出。

```bash
python decode_unicode.py log.txt
python decode_unicode.py log.txt -o decoded.txt
type log.txt | python decode_unicode.py -
```

| 参数 | 说明 |
|------|------|
| `file` | 输入文件路径；`-` 表示从 stdin 读取 |
| `-o` / `--output` | 写入指定文件（默认打印到 stdout） |

---

## detect-yolo-class.py

加载指定 YOLO `.pt` 权重，打印模型中的类别 id 与名称。

> 脚本内权重路径为硬编码，使用前请按实际路径修改。

```bash
python detect-yolo-class.py
```
