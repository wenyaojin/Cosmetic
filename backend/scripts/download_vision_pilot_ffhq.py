"""Download a small FFHQ subset for the local vision pilot.

This helper uses the official FFHQ metadata JSON and downloads only the selected
image records instead of the full 89 GB image archive.

Usage:
    cd Q:/Cosmetic/backend
    python -m scripts.download_vision_pilot_ffhq
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "docs" / "vision_pilot" / "data"
METADATA_PATH = DATA_DIR / "ffhq-dataset-v2.json"
README_PATH = DATA_DIR / "README.md"

METADATA_URL = "https://drive.google.com/uc?id=16N0RV4fHI6joBuKbQAoG34V_cQk7vxSA"

# Spread across FFHQ instead of cherry-picking adjacent records. FFHQ metadata
# does not include demographic labels, so the final diversity check is manual.
DEFAULT_INDICES = [0, 42, 777, 1234, 5678, 16000, 34567, 65000]


def md5_file(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - dataset integrity check only.
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_google_drive_file(session: requests.Session, url: str, path: Path) -> None:
    with session.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        html_probe = response.headers.get("content-type", "").startswith("text/html")
        if html_probe:
            text = response.text
            match = re.search(r'action="([^"]+)".*?name="id" value="([^"]+)".*?name="confirm" value="([^"]+)".*?name="uuid" value="([^"]+)"', text, re.S)
            if not match:
                raise RuntimeError(f"Google Drive confirmation page could not be parsed for {url}")
            action, file_id, confirm, uuid = match.groups()
            params = {"id": file_id, "confirm": confirm, "uuid": uuid}
            with session.get(action, params=params, stream=True, timeout=60) as confirmed:
                confirmed.raise_for_status()
                write_stream(confirmed, path)
            return
        write_stream(response, path)


def write_stream(response: requests.Response, path: Path) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)
    tmp_path.replace(path)


def ensure_metadata(session: requests.Session) -> None:
    if METADATA_PATH.exists() and METADATA_PATH.stat().st_size > 200_000_000:
        return
    print("Downloading FFHQ metadata JSON...")
    download_google_drive_file(session, METADATA_URL, METADATA_PATH)


def load_metadata() -> dict[str, Any]:
    with METADATA_PATH.open("rb") as handle:
        return json.load(handle)


def download_image(session: requests.Session, index: int, item: dict[str, Any], ordinal: int) -> tuple[Path, dict[str, Any]]:
    image_spec = item["image"]
    metadata = item["metadata"]
    out_path = DATA_DIR / f"{ordinal:02d}_ffhq_{index:05d}.png"
    if out_path.exists() and md5_file(out_path) == image_spec["file_md5"]:
        print(f"Already present: {out_path.name}")
    else:
        print(f"Downloading {out_path.name}...")
        download_google_drive_file(session, image_spec["file_url"], out_path)

    file_md5 = md5_file(out_path)
    if file_md5 != image_spec["file_md5"]:
        raise RuntimeError(f"MD5 mismatch for {out_path}: expected {image_spec['file_md5']}, got {file_md5}")
    with Image.open(out_path) as image:
        if list(image.size) != image_spec["pixel_size"]:
            raise RuntimeError(f"Unexpected image size for {out_path}: {image.size}")

    return out_path, {
        "filename": out_path.name,
        "ffhq_index": index,
        "photo_url": metadata.get("photo_url", ""),
        "author": metadata.get("author", ""),
        "license": metadata.get("license", ""),
        "license_url": metadata.get("license_url", ""),
        "ffhq_image_path": image_spec.get("file_path", ""),
        "md5": file_md5,
    }


def write_readme(records: list[dict[str, Any]]) -> None:
    rows = "\n".join(
        "| {filename} | {ffhq_index} | {author} | {license} | {photo_url} | {license_url} |".format(**record)
        for record in records
    )
    README_PATH.write_text(
        f"""# Vision Pilot 数据目录

本目录包含用于 Cosmetic vision pilot 的 FFHQ 小样本。图片来自 FFHQ 官方元数据记录，只用于本地非商业研究验证。

## License Notes

- FFHQ README: https://github.com/NVlabs/ffhq-dataset
- FFHQ dataset metadata/license: Creative Commons BY-NC-SA 4.0 by NVIDIA Corporation.
- Individual images inherit their original Flickr licenses; each file's source and license are listed below.
- Do not use these images for facial recognition development or production user-facing features.

## Downloaded Images

| Filename | FFHQ index | Author | License | Source photo | License URL |
|---|---:|---|---|---|---|
{rows}

## Sampling Notes

- The records were spread across the FFHQ index range to avoid adjacent duplicates.
- FFHQ metadata does not provide authoritative age, gender, skin-tone, or expression labels. Before final scoring, manually review the images and replace any sample that fails the design doc's diversity goals.
- These local files are ignored by git; keep only this README and the scripts under version control.
""",
        encoding="utf-8",
    )


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    ensure_metadata(session)
    data = load_metadata()

    records = []
    for ordinal, index in enumerate(DEFAULT_INDICES, start=1):
        path, record = download_image(session, index, data[str(index)], ordinal)
        records.append(record)
        print(f"Verified {path.name}")
        time.sleep(0.2)
    write_readme(records)
    print(f"Wrote {README_PATH}")


if __name__ == "__main__":
    main()
