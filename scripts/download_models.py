#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载 FunASR 所需模型到本地 models/ 目录。

说明：
- 该脚本通过 ModelScope 公开 API 列目录、下载文件，并用官方提供的 SHA256 做完整性校验。
- 断点续传：对每个文件使用 .part 临时文件 + HTTP Range 续传（若服务端不支持会自动重下）。
- 进度显示：优先使用 tqdm（可选依赖）；未安装时退化为简单的文本进度。

不要把该脚本当作库导入；建议直接运行：
  uv run python scripts/download_models.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True)
class RemoteFile:
    # ModelScope repo 内的相对路径，例如: "model.pt" 或 "example/asr_example.wav"
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelSpec:
    # 用户配置中的短名（用于落盘目录名）
    name: str
    # ModelScope 的 model_id，例如: "damo/speech_fsmn_vad_zh-cn-16k-common-pytorch"
    modelscope_id: str
    # 人类可读类型
    kind: str


MODELS: list[ModelSpec] = [
    ModelSpec(
        name="paraformer-zh",
        modelscope_id="damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        kind="ASR",
    ),
    ModelSpec(
        name="fsmn-vad",
        modelscope_id="damo/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        kind="VAD",
    ),
    ModelSpec(
        name="ct-punc",
        modelscope_id="damo/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
        kind="PUNC",
    ),
    ModelSpec(
        name="cam++",
        modelscope_id="damo/speech_campplus_sv_zh-cn_16k-common",
        kind="SPK",
    ),
]


MODELSCOPE_API_BASE = "https://modelscope.cn/api/v1"


def _try_import_tqdm():
    try:
        from tqdm import tqdm  # type: ignore

        return tqdm
    except Exception:
        return None


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _human_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.2f}{u}" if u != "B" else f"{int(size)}B"
        size /= 1024
    return f"{size:.2f}TB"


def _project_root() -> Path:
    # scripts/download_models.py -> project_root
    return Path(__file__).resolve().parents[1]


def _model_dir(models_dir: Path, model_name: str) -> Path:
    return models_dir / model_name


def _marker_path(model_dir: Path) -> Path:
    return model_dir / ".download_complete.json"


def _load_marker(model_dir: Path) -> dict | None:
    marker_path = _marker_path(model_dir)
    if not marker_path.exists():
        return None
    try:
        return json.loads(marker_path.read_text())
    except Exception:
        return None


def _marker_expected_files(marker: dict) -> list[RemoteFile]:
    files = marker.get("files")
    if not isinstance(files, list):
        return []
    out: list[RemoteFile] = []
    for f in files:
        if not isinstance(f, dict):
            continue
        path = f.get("path")
        if not isinstance(path, str) or not path:
            continue
        size = int(f.get("size") or 0)
        sha256 = str(f.get("sha256") or "").lower()
        if size <= 0:
            continue
        out.append(RemoteFile(path=path, size=size, sha256=sha256))
    out.sort(key=lambda x: x.path)
    return out


def _modelscope_list_dir(client: httpx.Client, model_id: str, revision: str, root: str) -> list[dict]:
    # Root 为空表示列根目录
    params = {"Revision": revision}
    if root:
        params["Root"] = root

    url = f"{MODELSCOPE_API_BASE}/models/{model_id}/repo/files"
    r = client.get(url, params=params, timeout=60)
    r.raise_for_status()
    payload = r.json()
    if not payload.get("Success"):
        raise RuntimeError(f"ModelScope API error: {payload.get('Message')}")
    data = payload.get("Data") or {}
    files = data.get("Files") or []
    return files


def _modelscope_list_all_files(
    client: httpx.Client, model_id: str, revision: str
) -> list[RemoteFile]:
    blobs: list[RemoteFile] = []

    def walk(dir_path: str) -> None:
        entries = _modelscope_list_dir(client, model_id=model_id, revision=revision, root=dir_path)
        for e in entries:
            t = e.get("Type")
            p = e.get("Path")
            if not isinstance(p, str) or not p:
                continue
            if t == "tree":
                walk(p)
                continue
            if t == "blob":
                size = int(e.get("Size") or 0)
                sha256 = str(e.get("Sha256") or "").lower()
                blobs.append(RemoteFile(path=p, size=size, sha256=sha256))

    walk("")
    # 过滤掉 size=0 的奇怪条目
    blobs = [b for b in blobs if b.size > 0]
    blobs.sort(key=lambda x: x.path)
    return blobs


def _modelscope_download_url(model_id: str, revision: str, file_path: str) -> str:
    # 说明：这个接口会直接返回文件内容（大文件为 application/octet-stream）。
    base = httpx.URL(f"{MODELSCOPE_API_BASE}/models/{model_id}/repo")
    return str(base.copy_merge_params({"Revision": revision, "FilePath": file_path}))


def _download_one_file(
    client: httpx.Client,
    url: str,
    dest_path: Path,
    expected_size: int,
    expected_sha256: str,
    show_progress: bool,
) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    final_path = dest_path
    part_path = dest_path.with_name(dest_path.name + ".part")

    # 已完成则跳过（同时做快速校验）
    if final_path.exists() and final_path.is_file():
        st = final_path.stat()
        if st.st_size == expected_size:
            if expected_sha256:
                actual = _sha256_file(final_path)
                if actual == expected_sha256:
                    return
                # sha 不匹配：重下
            else:
                return

    # 处理上一次下载完成但尚未 rename 的情况
    if part_path.exists() and part_path.is_file():
        st = part_path.stat()
        if st.st_size == expected_size:
            if expected_sha256:
                actual = _sha256_file(part_path)
                if actual == expected_sha256:
                    part_path.replace(final_path)
                    return
                # sha 不匹配：删掉 part 重新下
                part_path.unlink(missing_ok=True)
            else:
                part_path.replace(final_path)
                return

    existing = 0
    if part_path.exists() and part_path.is_file():
        existing = part_path.stat().st_size
        if existing > expected_size:
            part_path.unlink(missing_ok=True)
            existing = 0

    headers = {}
    mode = "wb"
    if existing > 0:
        headers["Range"] = f"bytes={existing}-"
        mode = "ab"

    tqdm = _try_import_tqdm() if show_progress else None

    with client.stream("GET", url, headers=headers, timeout=None) as r:
        # 若服务端不支持 Range，可能会返回 200；此时需要从头写
        if existing > 0 and r.status_code == 200:
            part_path.unlink(missing_ok=True)
            existing = 0
            mode = "wb"

        if r.status_code not in (200, 206):
            r.raise_for_status()

        total = expected_size
        # Range 下载时，content-length 是剩余长度
        if r.status_code == 206:
            total_remaining = int(r.headers.get("content-length") or 0)
            if total_remaining > 0:
                total = existing + total_remaining

        if total != expected_size:
            # 某些情况下服务端会给出不同的总量；以 API 列表为准。
            total = expected_size

        bar = None
        if tqdm is not None:
            bar = tqdm(
                total=expected_size,
                initial=existing,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                leave=False,
                desc=final_path.name,
            )

        last_print = time.time()
        downloaded = existing
        with part_path.open(mode) as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 256):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)

                if bar is not None:
                    bar.update(len(chunk))
                else:
                    # 无 tqdm：每 0.5s 打印一次粗略进度
                    now = time.time()
                    if now - last_print >= 0.5:
                        pct = downloaded / expected_size * 100 if expected_size else 0
                        print(
                            f"  - {final_path.name}: {pct:6.2f}% ({_human_bytes(downloaded)}/{_human_bytes(expected_size)})",
                            flush=True,
                        )
                        last_print = now

        if bar is not None:
            bar.close()

    st = part_path.stat()
    if st.st_size != expected_size:
        raise RuntimeError(
            f"下载文件大小不匹配: {final_path} got={st.st_size} expected={expected_size}"
        )

    if expected_sha256:
        actual = _sha256_file(part_path)
        if actual != expected_sha256:
            raise RuntimeError(
                f"SHA256 校验失败: {final_path} got={actual} expected={expected_sha256}"
            )

    part_path.replace(final_path)


def _verify_model_local(
    model_dir: Path, expected_files: list[RemoteFile], *, check_sha256: bool
) -> tuple[bool, list[str]]:
    problems: list[str] = []

    for rf in expected_files:
        local = model_dir / rf.path
        if not local.exists():
            problems.append(f"缺少文件: {rf.path}")
            continue
        if not local.is_file():
            problems.append(f"不是文件: {rf.path}")
            continue
        st = local.stat()
        if st.st_size != rf.size:
            problems.append(f"大小不匹配: {rf.path} got={st.st_size} expected={rf.size}")
            continue
        if check_sha256 and rf.sha256:
            actual = _sha256_file(local)
            if actual != rf.sha256:
                problems.append(f"SHA256 不匹配: {rf.path}")

    return (len(problems) == 0, problems)


def _write_marker(model_dir: Path, spec: ModelSpec, revision: str, files: list[RemoteFile]) -> None:
    marker = {
        "name": spec.name,
        "kind": spec.kind,
        "source": "modelscope-api",
        "modelscope_id": spec.modelscope_id,
        "revision": revision,
        "downloaded_at": int(time.time()),
        "files": [
            {"path": f.path, "size": f.size, "sha256": f.sha256} for f in files
        ],
    }
    _marker_path(model_dir).write_text(json.dumps(marker, ensure_ascii=False, indent=2) + "\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="下载 FunASR 模型到本地 models/ 目录")
    parser.add_argument(
        "--models-dir",
        default=str(_project_root() / "models"),
        help="模型保存目录（默认：<project>/models）",
    )
    parser.add_argument(
        "--revision",
        default="master",
        help="ModelScope revision（默认：master）",
    )
    parser.add_argument(
        "--only",
        default="",
        help="只下载指定模型（逗号分隔）：paraformer-zh,fsmn-vad,ct-punc,cam++",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新下载（忽略已完成标记）",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="关闭进度显示（tqdm 或文本进度）",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="不做 SHA256 校验（不推荐）",
    )

    args = parser.parse_args(argv)

    models_dir = Path(args.models_dir).expanduser().resolve()
    models_dir.mkdir(parents=True, exist_ok=True)

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    specs = [m for m in MODELS if not only or m.name in only]
    if not specs:
        print("未匹配到任何模型。", file=sys.stderr)
        return 2

    # 预估磁盘空间
    try:
        import shutil

        free = shutil.disk_usage(models_dir).free
        print(f"models_dir={models_dir} (free={_human_bytes(free)})")
    except Exception:
        print(f"models_dir={models_dir}")

    headers = {
        # 让服务端返回字节流
        "User-Agent": "audio-journal-model-downloader/0.1",
    }

    with httpx.Client(headers=headers, follow_redirects=True) as client:
        for spec in specs:
            model_dir = _model_dir(models_dir, spec.name)
            marker = _marker_path(model_dir)

            print(f"\n==> {spec.name} ({spec.kind})")
            print(f"    ModelScope: {spec.modelscope_id} @ {args.revision}")

            if marker.exists() and not args.force:
                # marker 存在时做一次 size 级校验：快、能防止误跳过。
                marker_data = _load_marker(model_dir)
                expected = _marker_expected_files(marker_data or {})
                if expected:
                    ok, problems = _verify_model_local(model_dir, expected, check_sha256=False)
                    if ok:
                        print("    已存在（marker）且大小校验通过，跳过。")
                        continue
                    print("    本地模型不完整，将继续补齐/重下：")
                    for p in problems[:5]:
                        print(f"    - {p}")
                    if len(problems) > 5:
                        print(f"    - ... ({len(problems)} problems)")
                else:
                    print("    警告：已存在 marker，但内容不可用，将重新拉取远端文件列表。")

            # 获取远端文件列表（含 size/sha256）
            remote_files = _modelscope_list_all_files(client, spec.modelscope_id, args.revision)
            total_size = sum(f.size for f in remote_files)
            print(f"    远端文件数: {len(remote_files)} | 预计大小: {_human_bytes(total_size)}")

            model_dir.mkdir(parents=True, exist_ok=True)

            for rf in remote_files:
                dest = model_dir / rf.path
                url = _modelscope_download_url(spec.modelscope_id, args.revision, rf.path)
                expected_sha = "" if args.no_verify else rf.sha256
                _download_one_file(
                    client=client,
                    url=url,
                    dest_path=dest,
                    expected_size=rf.size,
                    expected_sha256=expected_sha,
                    show_progress=(not args.no_progress),
                )

            # 末尾再整体校验一次（size 级别）。
            # 注：文件级 SHA256 已在下载阶段完成（未开启 --no-verify 时）。
            ok, problems = _verify_model_local(model_dir, remote_files, check_sha256=False)
            if not ok:
                print("\n下载完成但校验未通过：", file=sys.stderr)
                for p in problems:
                    print(f"- {p}", file=sys.stderr)
                return 1

            _write_marker(model_dir, spec, args.revision, remote_files)
            print(f"    完成：{model_dir}")

    print("\n全部模型下载完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
