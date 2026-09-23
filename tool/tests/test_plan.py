"""speckit-project の plan.py（収支の前提から収支表を計算する）のテスト。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "speckit" / "speckit-project" / "scripts"
PLAN = SCRIPTS / "plan.py"
sys.path.insert(0, str(SCRIPTS))

import plan as plan_module  # noqa: E402

BASE = {
    "currency": "JPY",
    "periods": ["1年目", "2年目"],
    "months_per_period": 12,
    "scenarios": {
        "標準": {
            "revenue": [{"name": "月額利用料", "unit": "店舗", "unit_price": 3000, "volume": [10, 50]}],
            "costs": [
                {"name": "インフラ", "monthly": [10000, 20000]},
                {"name": "開発外注", "per_period": [500000, 0]},
                {"name": "決済手数料", "rate": 0.04},
            ],
            "initial_investment": 100000,
        }
    },
}


def document(plan: dict) -> str:
    return (
        "# 事業計画\n\n```json speckit-plan\n" + json.dumps(plan, ensure_ascii=False, indent=2) + "\n```\n\n"
        + plan_module.BEGIN + "\n" + plan_module.END + "\n"
    )


class ComputeTest(unittest.TestCase):
    def test_values(self) -> None:
        r = plan_module.compute(BASE)["標準"]
        # 売上 = 3000 × 10 × 12 = 360,000 / 3000 × 50 × 12 = 1,800,000
        self.assertEqual(r["revenue"], [360000, 1800000])
        # 費用 = 10000×12 + 500000 + 360000×0.04 = 634,400 / 20000×12 + 0 + 1800000×0.04 = 312,000
        self.assertAlmostEqual(r["costs"][0], 634400)
        self.assertAlmostEqual(r["costs"][1], 312000)
        self.assertAlmostEqual(r["profit"][0], -274400)
        # 累積 = −100,000 − 274,400 = −374,400 → +1,488,000 = 1,113,600
        self.assertAlmostEqual(r["cumulative"][0], -374400)
        self.assertAlmostEqual(r["cumulative"][1], 1113600)
        self.assertAlmostEqual(r["required_funding"], 374400)
        # 損益分岐 = ceil((10000 + 500000 / 12) / (3000 × 0.96)) = ceil(51666.7 / 2880) = 18、ceil(20000 / 2880) = 7
        self.assertEqual(r["break_even"], [18, 7])

    def test_multiple_revenue_lines_skip_break_even(self) -> None:
        plan = json.loads(json.dumps(BASE))
        plan["scenarios"]["標準"]["revenue"].append({"name": "オプション", "unit_price": 500, "volume": [1, 2]})
        self.assertIsNone(plan_module.compute(plan)["標準"]["break_even"])

    def test_validation_errors(self) -> None:
        bad = json.loads(json.dumps(BASE))
        bad["scenarios"]["標準"]["revenue"][0]["volume"] = [1]
        with self.assertRaises(plan_module.PlanError):
            plan_module.validate_plan(bad)
        bad = json.loads(json.dumps(BASE))
        bad["scenarios"]["標準"]["costs"][0]["rate"] = 0.1
        with self.assertRaises(plan_module.PlanError):
            plan_module.validate_plan(bad)
        for mutate in (
            lambda p: p["scenarios"].update({"標準": "bad"}),
            lambda p: p["scenarios"]["標準"].update({"revenue": ["x"]}),
            lambda p: p["scenarios"]["標準"]["revenue"][0].update({"unit_price": True}),
            lambda p: p["scenarios"]["標準"]["revenue"][0].update({"volume": [True, 1]}),
            lambda p: p["scenarios"]["標準"]["costs"].append({"name": "手数料2", "rate": 0.97}),
        ):
            bad = json.loads(json.dumps(BASE))
            mutate(bad)
            with self.assertRaises(plan_module.PlanError):
                plan_module.validate_plan(bad)


class CommandTest(unittest.TestCase):
    def run_plan(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(PLAN), *args], capture_output=True, text=True, encoding="utf-8")

    def test_write_then_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.md"
            path.write_text(document(BASE), encoding="utf-8")
            self.assertEqual(self.run_plan(str(path), "--check").returncode, 1)
            self.assertEqual(self.run_plan(str(path), "--write").returncode, 0)
            text = path.read_text(encoding="utf-8")
            self.assertIn("| 売上 | 360,000 | 1,800,000 |", text)
            self.assertIn("| 損益分岐の数量（店舗） | 18 | 7 |", text)
            self.assertIn("必要資金（累積損益の最小値の不足分。初期投資を含む）: 374,400", text)
            self.assertEqual(self.run_plan(str(path), "--check").returncode, 0)
            # 前提を変えると食い違いを検出する
            path.write_text(text.replace('"unit_price": 3000', '"unit_price": 3500'), encoding="utf-8")
            proc = self.run_plan(str(path), "--check")
            self.assertEqual(proc.returncode, 1)
            self.assertIn("一致しない", proc.stderr)

    def test_missing_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.md"
            path.write_text(document(BASE).replace(plan_module.BEGIN, ""), encoding="utf-8")
            self.assertEqual(self.run_plan(str(path), "--write").returncode, 1)


if __name__ == "__main__":
    unittest.main()
