"""离线运行三个演示，每次建立新输出目录，不覆盖以前结果。"""

import csv
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from prepare_examples import EXAMPLE_FILES, main as prepare_examples


ROOT = Path(__file__).resolve().parent


def main():
    source = ROOT / "data" / "raw" / "bezdekIris.data"
    if not source.exists():
        print("ERROR: 原始数据尚未下载，请先运行 python download_data.py。", file=sys.stderr)
        return 1
    try:
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        provenance = json.loads(source.with_name("provenance.json").read_text(encoding="utf-8"))
        if source_hash != provenance["sha256"]:
            raise ValueError("原始文件哈希不匹配，停止演示，未修改原始数据")
        fixture_paths = [ROOT / "examples" / name for name in EXAMPLE_FILES]
        if not any(path.exists() for path in fixture_paths):
            if prepare_examples([]) != 0:
                return 1
        elif not all(path.exists() for path in fixture_paths):
            raise ValueError("样例文件不完整；请核对后显式运行 python prepare_examples.py --overwrite")

        manifest = json.loads((ROOT / "examples" / "fixture_manifest.json").read_text(encoding="utf-8"))
        if manifest["original_sha256"] != source_hash:
            raise ValueError("人工样例来自另一份原始快照；请核对后显式重建样例")

        beijing_time = datetime.now(timezone(timedelta(hours=8)))
        directory = ROOT / "output" / ("demo_" + beijing_time.strftime("%Y%m%d_%H%M%S_%f"))
        cases = [
            ("official", source, ["--no-header"]),
            ("dirty", ROOT / "examples" / "dirty.csv", ["--dedup"]),
            ("gb18030", ROOT / "examples" / "dirty_gb18030.csv", ["--dedup", "--encoding", "gb18030"]),
        ]
        reports = []
        for name, input_path, flags in cases:
            output_path = directory / (name + "_clean.csv")
            command = [sys.executable, str(ROOT / "clean.py"), "--input", str(input_path), "--output", str(output_path), *flags]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            print(f"[{name}] {result.stdout.strip()}")
            if result.returncode != 0:
                raise ValueError(result.stderr.strip() or "清洗进程未成功退出")
            report_path = output_path.with_name(output_path.stem + "_report.json")
            reports.append((name, json.loads(report_path.read_text(encoding="utf-8"))))
            if name != "official" and output_path.read_bytes() != (ROOT / "examples" / "expected_clean.csv").read_bytes():
                raise ValueError(name + " 演示输出与独立预期文件不一致")

        if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
            raise ValueError("演示前后原始文件哈希发生改变")

        with (directory / "dirty_clean.csv").open(encoding="utf-8-sig", newline="") as file:
            preview_rows = list(csv.reader(file))
        lines = [
            "# 演示结果", "", "本文件由 run_demo.py 根据实际运行结果生成；不是模型训练成绩。", "",
            "| 输入 | 记录数 | 保留 | 非法/缺失等异常 | 删除重复 | 隔离总数 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for name, report in reports:
            lines.append(f"| {name} | {report['input_records']} | {report['output_records']} | {report['invalid_records']} | {report['duplicates_removed']} | {report['rejected_records']} |")
        lines += [
            "", "- official：原始公开数据，只统计重复，不删除。",
            "- 当前原始快照为 150 条有效观测外加 1 条末尾空行；空行单独隔离，不称为观测字段缺失。",
            "- dirty / gb18030：人工注入的演示异常，启用整行去重。",
            "- 两个编码版本均已与 examples/expected_clean.csv 逐字节比对一致。",
            "- 原始公开数据 SHA-256 在演示前后保持不变。", "",
            "输出目录的时间戳采用北京时间（UTC+08:00）。", "",
            "## 人工样例清洗后的四条记录", "", "```csv",
            *[",".join(row) for row in preview_rows], "```", "",
            "异常原因见 dirty_clean_rejected.csv，统计见各 *_report.json。", "",
            "原始文件 SHA-256：`" + source_hash + "`", "",
        ]
        (directory / "演示结果.md").write_text("\n".join(lines), encoding="utf-8")
        (ROOT / "output" / "latest.json").write_text(json.dumps({"directory": str(directory), "preview": str(directory / "演示结果.md")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"演示通过。预览：{directory / '演示结果.md'}")
        return 0
    except (OSError, ValueError, KeyError, csv.Error) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
