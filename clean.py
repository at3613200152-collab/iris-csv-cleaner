"""Iris CSV 清洗工具。只使用 Python 标准库，核心逻辑在 clean_rows。"""

import argparse
import codecs
import csv
import hashlib
import io
import json
import math
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


COLUMNS = [
    "sepal_length_cm", "sepal_width_cm", "petal_length_cm",
    "petal_width_cm", "species",
]
SPECIES = {
    "iris-setosa": "Iris-setosa",
    "iris-versicolor": "Iris-versicolor",
    "iris-virginica": "Iris-virginica",
}
MISSING = {"", "na", "n/a", "null", "none", "?"}
RULES_VERSION = "1.0"


class CleanError(Exception):
    """可以解释给使用者的输入错误。"""


def normalize_row(row):
    """检查一行。返回：(规范化后的一行, 错误代码, 错误说明)。"""
    if not row or all(cell.strip() == "" for cell in row):
        return None, "empty_row", "整行为空"
    if len(row) != len(COLUMNS):
        return None, "wrong_column_count", f"应有 5 列，实际有 {len(row)} 列"

    values = []
    for index, column in enumerate(COLUMNS):
        text = row[index].strip()
        if text.casefold() in MISSING:
            return None, "missing", f"必填字段缺失：{column}"

        if column == "species":
            species = SPECIES.get(text.casefold())
            if species is None:
                return None, "unknown_species", "品种不在允许的三个类别中"
            values.append(species)
        else:
            try:
                value = float(text)
            except ValueError:
                return None, "invalid_number", f"不能转换成数字：{column}"
            if not math.isfinite(value):
                return None, "non_finite", f"不允许 NaN 或无穷大：{column}"
            if value < 0:
                return None, "negative", f"不允许负数：{column}"
            # 0 是有效值，不当成缺失；把 -0.0 也统一成 0.0。
            if value == 0:
                value = 0.0
            values.append(str(value))

    return values, None, None


def clean_rows(rows, deduplicate=False):
    """清洗任意数量的同结构记录；不按固定行号或固定数据内容作判断。"""
    cleaned = []
    rejected = []
    seen = set()
    reasons = Counter()
    duplicates = 0
    duplicates_removed = 0
    invalid = 0

    for record_number, row in enumerate(rows, start=1):
        values, error, detail = normalize_row(row)
        if error is not None:
            invalid += 1
        else:
            key = tuple(values)
            if key in seen:
                duplicates += 1
                if deduplicate:
                    error = "duplicate"
                    detail = "规范化后整行重复；已保留首次出现的记录"
                    duplicates_removed += 1
            else:
                seen.add(key)

        if error is not None:
            reasons[error] += 1
            rejected.append([
                record_number, error, detail,
                json.dumps(row, ensure_ascii=False),
            ])
        else:
            cleaned.append(values)

    stats = {
        "input_records": len(rows),
        "output_records": len(cleaned),
        "invalid_records": invalid,
        "duplicate_records": duplicates,
        "duplicates_removed": duplicates_removed,
        "rejected_records": len(rejected),
        "rejection_reasons": dict(sorted(reasons.items())),
    }
    assert stats["input_records"] == stats["output_records"] + stats["rejected_records"]
    return cleaned, rejected, stats


def read_input(path, encoding, no_header=False):
    """严格解码、严格解析 CSV；有表头时允许调整列顺序，但不接受缺列/重名列。"""
    raw = path.read_bytes()
    text = raw.decode(encoding, errors="strict")
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    records = list(reader)
    if not records:
        raise CleanError("输入文件为空，没有可处理的记录")

    if no_header:
        rows = records
        original_rows = records
    else:
        header = [cell.strip() for cell in records[0]]
        if len(header) != 5 or len(set(header)) != 5 or set(header) != set(COLUMNS):
            raise CleanError("表头必须恰好包含这些列且不能重名：" + ", ".join(COLUMNS))
        order = [header.index(column) for column in COLUMNS]
        original_rows = records[1:]
        rows = []
        for row in original_rows:
            # 列数错误的记录保留原貌，让核心清洗逻辑隔离它。
            rows.append([row[index] for index in order] if len(row) == 5 else row)

    if not rows:
        raise CleanError("输入只有表头，没有数据记录")
    return rows, hashlib.sha256(raw).hexdigest(), original_rows


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def make_parser():
    parser = argparse.ArgumentParser(description="清洗 Iris CSV，输出干净数据、异常记录和 JSON 统计。")
    parser.add_argument("--input", required=True, type=Path, help="输入 CSV 或官方无表头 .data 文件")
    parser.add_argument("--output", required=True, type=Path, help="输出 CSV")
    parser.add_argument("--encoding", default="utf-8-sig", help="输入编码，默认 utf-8-sig；中文旧编码可指定 gb18030")
    parser.add_argument("--no-header", action="store_true", help="官方 .data 文件无表头，按固定五列顺序读取")
    parser.add_argument("--dedup", action="store_true", help="删除规范化后整行重复记录；默认只统计、不删除")
    parser.add_argument("--rejects", type=Path, help="异常记录 CSV，默认 <输出名>_rejected.csv")
    parser.add_argument("--report", type=Path, help="统计 JSON，默认 <输出名>_report.json")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有输出，但始终禁止覆盖输入文件")
    return parser


def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        codecs.lookup(args.encoding)
        decoder = codecs.getincrementaldecoder(args.encoding)(errors="strict")
        if not isinstance(decoder.decode(b"", final=True), str):
            raise LookupError("不是字节到文本的编码")
    except (LookupError, TypeError, UnicodeError):
        parser.error("不支持的文本编码名称：" + args.encoding)

    rejects_path = args.rejects or args.output.with_name(args.output.stem + "_rejected.csv")
    report_path = args.report or args.output.with_name(args.output.stem + "_report.json")

    try:
        input_path = args.input.resolve()
        if input_path.exists() and not input_path.is_file():
            raise CleanError("输入必须是文件，不能是文件夹或其他对象")
        output_paths = [path.resolve() for path in (args.output, rejects_path, report_path)]
        if input_path in output_paths or len(set(output_paths)) != 3:
            parser.error("输入和三个输出必须使用不同的路径，禁止覆盖输入")
        # 额外检查硬链接，避免 --overwrite 间接改写原始输入。
        if input_path.exists():
            for path in output_paths:
                if path.exists() and path.samefile(input_path):
                    parser.error("输出与输入指向同一个文件，禁止覆盖输入")
        for index, path in enumerate(output_paths):
            if input_path in path.parents:
                parser.error("不能把输入文件当成输出目录")
            if path.is_dir():
                raise CleanError(f"输出路径是文件夹，不是文件：{path}")
            if path.exists() and not args.overwrite:
                raise CleanError(f"输出已存在，未覆盖：{path}；确需覆盖请加 --overwrite")
            for other in output_paths[index + 1:]:
                if path in other.parents or other in path.parents:
                    parser.error("不能把一个输出文件当成另一个输出的目录")
                if path.exists() and other.exists() and path.samefile(other):
                    parser.error("多个输出指向同一个文件")

        rows, input_hash, original_rows = read_input(input_path, args.encoding, args.no_header)
        cleaned, rejected, stats = clean_rows(rows, args.dedup)
        # 即便表头换序，异常表仍保留输入中的原始字段顺序，便于回查。
        for rejection in rejected:
            rejection[3] = json.dumps(original_rows[rejection[0] - 1], ensure_ascii=False)
        report = {
            "status": "ok" if cleaned else "no_valid_records",
            "rules_version": RULES_VERSION,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": platform.python_version(),
            "input_path": str(input_path),
            "input_sha256": input_hash,
            "input_encoding": args.encoding,
            "input_has_header": not args.no_header,
            "output_encoding": "utf-8-sig",
            "deduplicate": args.dedup,
            "columns": COLUMNS,
            **stats,
        }

        write_csv(output_paths[0], COLUMNS, cleaned)
        write_csv(output_paths[1], ["source_record", "error", "detail", "raw_row"], rejected)
        output_paths[2].parent.mkdir(parents=True, exist_ok=True)
        output_paths[2].write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"输入 {len(rows)} 条；保留 {len(cleaned)} 条；隔离 {len(rejected)} 条；发现重复 {stats['duplicate_records']} 条。")
        print(f"结果：{output_paths[0]}")
        if not cleaned:
            print("ERROR: 没有有效数据；已保存空结果表、异常记录和统计报告。", file=sys.stderr)
            return 1
        return 0
    except UnicodeError as error:
        print(f"ERROR: 编码处理失败：{error}。请检查 --encoding；未忽略任何非法字节。", file=sys.stderr)
    except (OSError, csv.Error, CleanError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
