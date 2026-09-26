"""speckit-concept-2-feature の validate.py のテスト（予約番号 000 / 999 の規則を中心に）。"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

VALIDATE = (Path(__file__).resolve().parents[2]
            / "skills" / "speckit" / "speckit-concept-2-feature" / "scripts" / "validate.py")

FEATURE = """# {title}

**状態**: 未着手 | **区分**: {category} | **想定順序**: {order} | **依存**: {deps}

## 概要

{title}を提供する。

## 位置づけ

中核価値を支える。

## 主な要求

- **要求**:
  - 利用者が{title}を使える

主なエンティティ: なし

## 前提・設計原則との関係

- **共通標準**: docs/architecture.md

## スコープ外

- なし

## 根拠

- premises.md P1: テスト

## /speckit-specify に渡す記述案

> {title}。
"""


def build(root: Path, features: list[tuple[str, str, str, int, str]], order: list[str]) -> Path:
    """features: (slug, title, category, order, deps)。order: spec_order.md に並べる slug の順。"""
    d = root / "docs" / "feature"
    d.mkdir(parents=True)
    by_slug = {f[0]: f for f in features}
    for slug, title, category, num, deps in features:
        (d / f"{slug}.md").write_text(
            FEATURE.format(title=title, category=category, order=num, deps=deps), encoding="utf-8")
    rows = [f"| {n} | [{t}](./{s}.md) | {c} | 未着手 | {dp} | 一言 |" for s, t, c, n, dp in features]
    (d / "README.md").write_text(
        "# 機能バックログ\n\n## 一覧\n\n| # | 機能 | 区分 | 状態 | 依存 | 一言 |\n|---|---|---|---|---|---|\n"
        + "\n".join(rows) + "\n", encoding="utf-8")
    lines = [f"- **{by_slug[s][3]}. [{by_slug[s][1]}](./{s}.md)**: 一言" for s in order]
    (d / "spec_order.md").write_text("# 推奨仕様化順\n\n" + "\n".join(lines) + "\n", encoding="utf-8")
    (d / "premises.md").write_text("# 前提メモ\n\n| ID | 項目 | 状態 |\n|---|---|---|\n| P1 | 目的 | 確定 |\n",
                                   encoding="utf-8")
    return d


class ValidateReservedOrders(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_validate(self, feature_dir: Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(VALIDATE), str(feature_dir)],
                              capture_output=True, text=True, encoding="utf-8")

    def test_valid_with_basic_and_nfr(self) -> None:
        d = build(self.tmp, [
            ("000-app-basic", "アプリ基盤", "MVP", 0, "—"),
            ("001-booking", "予約", "MVP", 1, "000-app-basic"),
            ("002-report", "集計", "拡張", 2, "001-booking"),
            ("999-app-nfr", "運用基盤", "MVP", 999, "000-app-basic"),
        ], ["000-app-basic", "001-booking", "999-app-nfr", "002-report"])
        proc = self.run_validate(d)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        warnings = [l for l in proc.stdout.splitlines() if l.startswith("[警告]") and "backlog.md がない" not in l]
        self.assertEqual(warnings, [], proc.stdout)

    def test_basic_must_be_first_mvp_without_deps(self) -> None:
        d = build(self.tmp, [
            ("000-app-basic", "アプリ基盤", "拡張", 0, "001-booking"),
            ("001-booking", "予約", "MVP", 1, "—"),
        ], ["001-booking", "000-app-basic"])
        out = self.run_validate(d).stdout
        self.assertIn("共通基盤（000）の区分は MVP にする", out)
        self.assertIn("共通基盤（000）はほかの機能に依存できない", out)
        self.assertIn("共通基盤 000-app-basic は先頭に並べる", out)

    def test_warns_missing_basic_dependency_and_nfr_dependents(self) -> None:
        d = build(self.tmp, [
            ("000-app-basic", "アプリ基盤", "MVP", 0, "—"),
            ("001-booking", "予約", "MVP", 1, "—"),
            ("002-report", "集計", "MVP", 2, "999-app-nfr"),
            ("999-app-nfr", "運用基盤", "MVP", 999, "000-app-basic"),
        ], ["000-app-basic", "001-booking", "999-app-nfr", "002-report"])
        out = self.run_validate(d).stdout
        self.assertIn("001-booking.md: 共通基盤 000-app-basic に（間接的にも）依存していない", out)
        self.assertNotIn("002-report.md: 共通基盤", out)  # 999 経由で間接的に依存している
        self.assertIn("002-report.md: 運用基盤 999-app-nfr に依存している", out)

    def test_reserved_numbers_excluded_from_sequence_check(self) -> None:
        d = build(self.tmp, [
            ("000-app-basic", "アプリ基盤", "MVP", 0, "—"),
            ("001-booking", "予約", "MVP", 1, "000-app-basic"),
            ("999-app-nfr", "運用基盤", "MVP", 999, "000-app-basic"),
        ], ["000-app-basic", "001-booking", "999-app-nfr"])
        self.assertNotIn("連番", self.run_validate(d).stdout)

    def test_output_survives_cp932_console(self) -> None:
        """H5: Windows の日本語環境（標準出力が cp932）でも、— を含む警告の出力で落ちない。"""
        import os

        d = build(self.tmp, [
            ("000-app-basic", "アプリ基盤", "MVP", 0, "—"),
            ("001-booking", "予約", "MVP", 1, "—"),
        ], ["000-app-basic", "001-booking"])
        proc = subprocess.run([sys.executable, str(VALIDATE), str(d)], capture_output=True,
                              env={**os.environ, "PYTHONIOENCODING": "cp932"})
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertIn("依存していない", proc.stdout.decode("utf-8"))

    def test_without_reserved_features_behaves_as_before(self) -> None:
        d = build(self.tmp, [
            ("001-booking", "予約", "MVP", 1, "—"),
            ("003-report", "集計", "MVP", 3, "001-booking"),
        ], ["001-booking", "003-report"])
        proc = self.run_validate(d)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("1 からの連番になっていない", proc.stdout)

    def test_accepts_human_pending_status(self) -> None:
        """人のタスクだけが残った機能の状態「人の作業待ち（specs/…）」を受け付ける。"""
        d = build(self.tmp, [
            ("000-app-basic", "アプリ基盤", "MVP", 0, "—"),
            ("001-booking", "予約", "MVP", 1, "000-app-basic"),
        ], ["000-app-basic", "001-booking"])
        status = "人の作業待ち（specs/001-booking）"
        for name in ("001-booking.md", "README.md"):
            path = d / name
            text = path.read_text(encoding="utf-8")
            if name == "README.md":
                text = text.replace("(./001-booking.md) | MVP | 未着手 |", f"(./001-booking.md) | MVP | {status} |")
            else:
                text = text.replace("**状態**: 未着手", f"**状態**: {status}")
            path.write_text(text, encoding="utf-8")
        proc = self.run_validate(d)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertNotIn("状態「", proc.stdout)


if __name__ == "__main__":
    unittest.main()
