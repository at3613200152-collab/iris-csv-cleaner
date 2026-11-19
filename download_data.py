"""重新获取官方公开原始文件；日常运行演示不需要联网。"""

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from clean import normalize_row


ROOT = Path(__file__).resolve().parent
SOURCE_URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/iris/bezdekIris.data"
SOURCE_PAGE = "https://archive.ics.uci.edu/dataset/53/iris"


def main():
    parser = argparse.ArgumentParser(description="从 UCI 下载 Iris 原始数据，不对内容进行清洗或修补。")
    parser.add_argument("--refresh", action="store_true", help="明确允许替换本项目保存的原始数据和来源元数据")
    args = parser.parse_args()
    destination = ROOT / "data" / "raw" / "bezdekIris.data"
    metadata_path = destination.with_name("provenance.json")
    if (destination.exists() or metadata_path.exists()) and not args.refresh:
        print("ERROR: 原始文件或来源记录已存在；未覆盖。确需重下请加 --refresh。", file=sys.stderr)
        return 1
    try:
        request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "IrisCleaningTeachingProject/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("下载内容超过预期大小，拒绝作为该数据集保存")
        rows = list(csv.reader(io.StringIO(raw.decode("ascii")), strict=True))
        rows = [row for row in rows if row]
        if len(rows) != 150 or any(normalize_row(row)[1] is not None for row in rows):
            raise ValueError("下载内容与 Iris 官方数据结构不符，未保存")
        metadata = {
            "dataset": "Iris",
            "variant": "bezdekIris.data",
            "source_url": SOURCE_URL,
            "dataset_page": SOURCE_PAGE,
            "doi": "https://doi.org/10.24432/C56C76",
            "citation": "Fisher, R. (1936). Iris [Dataset]. UCI Machine Learning Repository.",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "records": len(rows),
            "modified": False,
            "note": "原始下载字节原样保存；人工构造的异常只存在于 examples 中。",
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已保存官方原始数据：{destination}，共 {len(rows)} 条；SHA-256={metadata['sha256']}")
        return 0
    except (OSError, ValueError, UnicodeError, csv.Error) as error:
        print(f"ERROR: 下载失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
