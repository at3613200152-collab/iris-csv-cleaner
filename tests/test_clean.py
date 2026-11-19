"""小型、离线、确定性测试；人工异常不是原始数据质量结论。"""

import csv
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from clean import COLUMNS, clean_rows, normalize_row


ROOT = Path(__file__).resolve().parents[1]
GOOD = ["5.1", "3.5", "1.4", "0.2", "Iris-setosa"]
OTHER = ["4.9", "3.0", "1.4", "0.2", "Iris-setosa"]


class RowTests(unittest.TestCase):
    def test_valid_record_and_zero_are_preserved(self):
        cleaned, rejected, stats = clean_rows([["0", *GOOD[1:]]])
        self.assertEqual(cleaned[0][0], "0.0")
        self.assertEqual(rejected, [])
        self.assertEqual(stats["output_records"], 1)

    def test_whitespace_case_and_numeric_format_are_normalized(self):
        row = [" 5.10 ", "3.50", "1.4", "0.2", " IRIS-SETOSA "]
        self.assertEqual(normalize_row(row), (GOOD, None, None))

    def test_missing_markers_in_every_column(self):
        for column in range(5):
            for marker in ["", "  ", "NA", "n/a", "null", "None", "?"]:
                with self.subTest(column=column, marker=marker):
                    row = GOOD.copy()
                    row[column] = marker
                    self.assertEqual(normalize_row(row)[1], "missing")

    def test_non_numeric_value(self):
        row = GOOD.copy()
        row[1] = "abc"
        self.assertEqual(normalize_row(row)[1], "invalid_number")

    def test_nan_infinity_and_overflow_are_rejected(self):
        for text in ["NaN", "nan", "inf", "+inf", "-inf", "Infinity", "1e309"]:
            with self.subTest(text=text):
                row = GOOD.copy()
                row[0] = text
                self.assertEqual(normalize_row(row)[1], "non_finite")

    def test_negative_is_invalid_but_negative_zero_is_zero(self):
        row = GOOD.copy()
        row[2] = "-1"
        self.assertEqual(normalize_row(row)[1], "negative")
        row[2] = "-0.0"
        self.assertEqual(normalize_row(row)[0][2], "0.0")

    def test_unknown_species(self):
        row = GOOD.copy()
        row[4] = "未知品种"
        self.assertEqual(normalize_row(row)[1], "unknown_species")

    def test_column_count_and_blank_records(self):
        cases = [(GOOD[:4], "wrong_column_count"), (GOOD + ["extra"], "wrong_column_count"), ([], "empty_row"), ([""] * 5, "empty_row")]
        for row, error in cases:
            with self.subTest(row=row):
                self.assertEqual(normalize_row(row)[1], error)

    def test_duplicates_are_only_reported_by_default(self):
        cleaned, rejected, stats = clean_rows([GOOD, GOOD])
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(rejected, [])
        self.assertEqual(stats["duplicate_records"], 1)
        self.assertEqual(stats["duplicates_removed"], 0)

    def test_opt_in_dedup_uses_normalized_full_row(self):
        equivalent = ["5.10", "3.50", "1.40", "0.20", " iris-setosa "]
        cleaned, rejected, stats = clean_rows([GOOD, equivalent, OTHER], deduplicate=True)
        self.assertEqual(cleaned, [GOOD, OTHER])
        self.assertEqual(rejected[0][0:2], [2, "duplicate"])
        self.assertEqual(stats["duplicates_removed"], 1)

    def test_distinct_species_are_not_duplicates(self):
        row = GOOD.copy()
        row[4] = "Iris-versicolor"
        self.assertEqual(len(clean_rows([GOOD, row], True)[0]), 2)

    def test_bad_records_do_not_stop_later_good_records(self):
        cleaned, rejected, stats = clean_rows([["bad"], GOOD, [], OTHER])
        self.assertEqual(cleaned, [GOOD, OTHER])
        self.assertEqual([row[0] for row in rejected], [1, 3])
        self.assertEqual(stats["input_records"], stats["output_records"] + stats["rejected_records"])


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="iris_cleaner_test_")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.input = self.directory / "input.csv"
        self.output = self.directory / "clean.csv"

    def write_input(self, rows, header=COLUMNS, encoding="utf-8-sig"):
        with self.input.open("w", encoding=encoding, newline="") as file:
            writer = csv.writer(file)
            if header is not None:
                writer.writerow(header)
            writer.writerows(rows)

    def invoke(self, *extra, input_path=None, output_path=None):
        return subprocess.run(
            [sys.executable, str(ROOT / "clean.py"), "--input", str(input_path or self.input), "--output", str(output_path or self.output), *extra],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )

    def report(self, output=None):
        path = output or self.output
        return json.loads(path.with_name(path.stem + "_report.json").read_text(encoding="utf-8"))

    def test_success_writes_outputs_and_balanced_counts(self):
        self.write_input([GOOD, OTHER, ["", *GOOD[1:]]])
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.output.read_bytes().startswith(b"\xef\xbb\xbf"))
        report = self.report()
        self.assertEqual((report["input_records"], report["output_records"], report["rejected_records"]), (3, 2, 1))
        self.assertEqual(report["input_sha256"], hashlib.sha256(self.input.read_bytes()).hexdigest())

    def test_header_order_can_change(self):
        self.write_input([GOOD[::-1]], header=COLUMNS[::-1])
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.output.open(encoding="utf-8-sig", newline="") as file:
            self.assertEqual(list(csv.reader(file)), [COLUMNS, GOOD])

    def test_rejected_record_keeps_original_order_after_header_reordering(self):
        invalid = GOOD.copy()
        invalid[0] = "abc"
        self.write_input([GOOD[::-1], invalid[::-1]], header=COLUMNS[::-1])
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.output.with_name("clean_rejected.csv").open(encoding="utf-8-sig", newline="") as file:
            rejected = list(csv.DictReader(file))
        self.assertEqual(rejected[0]["source_record"], "2")
        self.assertEqual(json.loads(rejected[0]["raw_row"]), invalid[::-1])

    def test_header_duplicate_missing_or_extra_is_fatal(self):
        for header in [COLUMNS[:4], COLUMNS + ["extra"], [COLUMNS[0], *COLUMNS[:4]]]:
            with self.subTest(header=header):
                self.write_input([GOOD], header=header)
                self.assertEqual(self.invoke().returncode, 1)
                self.assertFalse(self.output.exists())

    def test_no_header_keeps_first_record(self):
        self.write_input([GOOD, OTHER], header=None)
        result = self.invoke("--no-header")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.report()["input_records"], 2)

    def test_encoding_gb18030_with_actual_chinese(self):
        invalid = GOOD.copy()
        invalid[4] = "未知品种"
        self.write_input([GOOD, invalid], encoding="gb18030")
        wrong_encoding = self.invoke()
        self.assertEqual(wrong_encoding.returncode, 1)
        self.assertIn("--encoding", wrong_encoding.stderr)
        self.assertFalse(self.output.exists())
        result = self.invoke("--encoding", "gb18030")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.report()["rejection_reasons"], {"unknown_species": 1})
        rejects = self.output.with_name("clean_rejected.csv").read_text(encoding="utf-8-sig")
        self.assertIn("未知品种", rejects)

    def test_corrupt_bytes_fail_without_silent_replacement(self):
        self.input.write_bytes(b"\xff\xfe\x80")
        self.assertEqual(self.invoke().returncode, 1)
        self.assertFalse(self.output.exists())

    def test_unknown_encoding_is_parameter_error(self):
        self.write_input([GOOD])
        self.assertEqual(self.invoke("--encoding", "not-a-real-encoding").returncode, 2)

    def test_non_text_codec_is_parameter_error_not_a_traceback(self):
        self.write_input([GOOD])
        result = self.invoke("--encoding", "base64_codec")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_parameters_exit_two_and_help_exits_zero(self):
        for arguments, expected in [([], 2), (["--help"], 0)]:
            result = subprocess.run([sys.executable, str(ROOT / "clean.py"), *arguments], capture_output=True, timeout=15)
            self.assertEqual(result.returncode, expected)

    def test_missing_input_or_directory_input_exits_one(self):
        self.assertEqual(self.invoke().returncode, 1)
        self.assertEqual(self.invoke(input_path=self.directory).returncode, 1)

    def test_empty_file_and_header_only_are_fatal(self):
        for text in ["", ",".join(COLUMNS) + "\n"]:
            with self.subTest(text=text):
                self.input.write_text(text, encoding="utf-8")
                self.assertEqual(self.invoke().returncode, 1)
                self.assertFalse(self.output.exists())

    def test_malformed_quoted_csv_is_fatal(self):
        self.input.write_text(",".join(COLUMNS) + '\n"unterminated,3,1,0.2,Iris-setosa\n', encoding="utf-8")
        self.assertEqual(self.invoke().returncode, 1)
        self.assertFalse(self.output.exists())

    def test_quoted_comma_is_one_field_not_an_extra_column(self):
        invalid = GOOD.copy()
        invalid[4] = "bad,kind"
        self.write_input([GOOD, invalid])
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.report()["rejection_reasons"], {"unknown_species": 1})

    def test_all_invalid_returns_one_but_writes_audit(self):
        self.write_input([["", *GOOD[1:]], ["bad"]])
        result = self.invoke()
        self.assertEqual(result.returncode, 1)
        report = self.report()
        self.assertEqual(report["status"], "no_valid_records")
        self.assertEqual((report["output_records"], report["rejected_records"]), (0, 2))
        with self.output.open(encoding="utf-8-sig", newline="") as file:
            self.assertEqual(list(csv.reader(file)), [COLUMNS])

    def test_existing_output_is_preserved_without_overwrite(self):
        self.write_input([GOOD])
        self.output.write_text("keep this file", encoding="utf-8")
        self.assertEqual(self.invoke().returncode, 1)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "keep this file")

    def test_explicit_overwrite_does_not_change_input(self):
        self.write_input([GOOD])
        original = self.input.read_bytes()
        self.assertEqual(self.invoke().returncode, 0)
        self.assertEqual(self.invoke("--overwrite").returncode, 0)
        self.assertEqual(self.input.read_bytes(), original)

    def test_input_cannot_be_an_output_even_with_overwrite(self):
        self.write_input([GOOD])
        original = self.input.read_bytes()
        self.assertEqual(self.invoke("--overwrite", output_path=self.input).returncode, 2)
        self.assertEqual(self.input.read_bytes(), original)

    def test_output_paths_cannot_collide(self):
        self.write_input([GOOD])
        self.assertEqual(self.invoke("--report", str(self.output)).returncode, 2)
        self.assertFalse(self.output.exists())

    def test_output_file_cannot_be_used_as_another_output_parent(self):
        self.write_input([GOOD])
        result = self.invoke("--report", str(self.output / "report.json"))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.output.exists())

    def test_input_file_cannot_be_used_as_output_parent(self):
        self.write_input([GOOD])
        original = self.input.read_bytes()
        self.assertEqual(self.invoke(output_path=self.input / "result.csv").returncode, 2)
        self.assertEqual(self.input.read_bytes(), original)

    def test_output_directory_and_unwritable_parent_fail_cleanly(self):
        self.write_input([GOOD])
        self.output.mkdir()
        self.assertEqual(self.invoke().returncode, 1)
        blocker = self.directory / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        self.assertEqual(self.invoke(output_path=blocker / "out.csv").returncode, 1)
        self.assertEqual(blocker.read_text(encoding="utf-8"), "not a directory")

    def test_cleaning_again_is_idempotent_for_csv(self):
        self.write_input([GOOD, GOOD, OTHER])
        self.assertEqual(self.invoke("--dedup").returncode, 0)
        second = self.directory / "second.csv"
        result = self.invoke("--dedup", input_path=self.output, output_path=second)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), second.read_bytes())
        self.assertEqual(self.report(second)["duplicate_records"], 0)


class PublicDataTests(unittest.TestCase):
    def test_bundled_public_source_matches_provenance_and_has_150_valid_rows(self):
        path = ROOT / "data" / "raw" / "bezdekIris.data"
        provenance = json.loads(path.with_name("provenance.json").read_text(encoding="utf-8"))
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), provenance["sha256"])
        manifest = json.loads((ROOT / "examples" / "fixture_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["original_sha256"], provenance["sha256"])
        rows = list(csv.reader(io.StringIO(raw.decode("ascii"))))
        cleaned, rejected, stats = clean_rows(rows)
        self.assertEqual(len(cleaned), 150)
        # 官方字节快照的末尾还有空分隔行；审计它，不偷偷删除后再宣称“零异常”。
        blank_count = sum(1 for row in rows if not row or all(cell.strip() == "" for cell in row))
        self.assertEqual(len(rejected), blank_count)
        self.assertTrue(all(row[1] == "empty_row" for row in rejected))
        self.assertEqual(stats["input_records"], 150 + blank_count)
        self.assertEqual(cleaned[0], GOOD)

    def test_both_synthetic_encodings_match_independent_expected_output(self):
        expected = (ROOT / "examples" / "expected_clean.csv").read_bytes()
        for filename, encoding in [("dirty.csv", "utf-8-sig"), ("dirty_gb18030.csv", "gb18030")]:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory(prefix="iris_fixture_test_") as folder:
                output = Path(folder) / "clean.csv"
                result = subprocess.run(
                    [sys.executable, str(ROOT / "clean.py"), "--input", str(ROOT / "examples" / filename), "--output", str(output), "--encoding", encoding, "--dedup"],
                    capture_output=True, text=True, encoding="utf-8", timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output.read_bytes(), expected)
                report = json.loads(output.with_name("clean_report.json").read_text(encoding="utf-8"))
                self.assertEqual((report["input_records"], report["output_records"], report["invalid_records"], report["duplicates_removed"]), (15, 4, 10, 1))


if __name__ == "__main__":
    unittest.main()
