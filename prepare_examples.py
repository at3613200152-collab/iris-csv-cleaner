"""从原始公开数据派生人工异常样例；不改动 data/raw。"""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from clean import COLUMNS


ROOT = Path(__file__).resolve().parent
EXAMPLE_FILES = ["dirty.csv", "dirty_gb18030.csv", "expected_clean.csv", "fixture_manifest.json"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="制作明确标注为人工注入异常的演示数据。")
    parser.add_argument("--overwrite", action="store_true", help="明确允许重建已有演示样例；原始数据始终不改")
    args = parser.parse_args(argv)
    directory = ROOT / "examples"
    if not args.overwrite and any((directory / name).exists() for name in EXAMPLE_FILES):
        print("ERROR: 样例已存在，未覆盖。确需重建请加 --overwrite。", file=sys.stderr)
        return 1
    try:
        source = ROOT / "data" / "raw" / "bezdekIris.data"
        raw = source.read_bytes()
        provenance = json.loads(source.with_name("provenance.json").read_text(encoding="utf-8"))
        if hashlib.sha256(raw).hexdigest() != provenance["sha256"]:
            raise ValueError("原始文件哈希与来源记录不符；请先核对，不自动覆盖")
        rows = list(csv.reader(raw.decode("ascii").splitlines()))

        selected = [0, 1, 0, 2, 3, 4, 5, 6, 7, 50, 8, 100, 9, 10]
        dirty = [rows[index].copy() for index in selected]
        dirty[1] = ["  " + cell + "  " for cell in dirty[1]]
        dirty[3][0] = ""
        dirty[4][0] = "abc"
        dirty[5][1] = "-3.6"
        dirty[6][2] = "NaN"
        dirty[7][4] = "未知品种"
        dirty[8] = dirty[8][:4]
        dirty[10][3] = "?"
        dirty[12].append("多余字段")
        dirty[13][0] = "inf"
        dirty.append([])

        # 独立列出预期输出，而不是调用清洗函数生成“正确答案”。
        expected = [
            ["5.1", "3.5", "1.4", "0.2", "Iris-setosa"],
            ["4.9", "3.0", "1.4", "0.2", "Iris-setosa"],
            ["7.0", "3.2", "4.7", "1.4", "Iris-versicolor"],
            ["6.3", "3.3", "6.0", "2.5", "Iris-virginica"],
        ]
        changes = [
            "正常记录", "增加首尾空白", "复制第 1 条", "清空第 1 列",
            "第 1 列改成 abc", "第 2 列改成负数", "第 3 列改成 NaN",
            "品种改成中文未知类别", "删除第 5 列", "正常记录", "第 4 列改成 ?",
            "正常记录", "追加多余列", "第 1 列改成 inf", "追加空行",
        ]
        manifest = {
            "synthetic_errors": True,
            "description": "下面的异常是为测试人工注入的，不能当成 UCI 原始数据质量结论。",
            "original_sha256": provenance["sha256"],
            "expected_with_dedup": {"input_records": 15, "output_records": 4, "invalid_records": 10, "duplicates_removed": 1, "rejected_records": 11},
            "records": [
                {"example_record": index + 1, "source_record": selected[index] + 1 if index < len(selected) else None, "change": change}
                for index, change in enumerate(changes)
            ],
        }
        directory.mkdir(parents=True, exist_ok=True)
        for name, encoding, content in [
            ("dirty.csv", "utf-8-sig", dirty),
            ("dirty_gb18030.csv", "gb18030", dirty),
            ("expected_clean.csv", "utf-8-sig", expected),
        ]:
            with (directory / name).open("w", encoding=encoding, newline="") as file:
                writer = csv.writer(file)
                writer.writerow(COLUMNS)
                writer.writerows(content)
        (directory / "fixture_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("已生成 15 条人工演示记录、GB18030 编码版本、独立预期输出及注入说明。")
        return 0
    except (OSError, ValueError, KeyError, csv.Error) as error:
        print(f"ERROR: 样例制作失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
