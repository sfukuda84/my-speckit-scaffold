#!/usr/bin/env python3
"""docs/project.md の収支の前提（```json speckit-plan ブロック）から収支表を計算する。

使い方:
    python3 plan.py <docs/project.md>            # 計算結果を表示する
    python3 plan.py <docs/project.md> --write    # 計算結果を project.md のマーカーの間に書き込む
    python3 plan.py <docs/project.md> --check    # 書かれている収支表が前提と一致するかを確かめる

計算の規則:
    売上   = 月額の単価 × 期中の平均の数量 × 期の月数（収益の項目ごと）
    費用   = 月額の固定費 × 期の月数 ＋ 期ごとの費用 ＋ 売上 × 変動費の率
    損益   = 売上 − 費用
    累積   = 各期の損益の累計 − 初期投資
    必要資金 = 累積の最小値が負のときの、その絶対値
    損益分岐の数量 =（月額の固定費 ＋ 期ごとの費用 ÷ 期の月数）÷（単価 ×（1 − 変動費の率の合計））
                   （収益の項目が 1 つのときだけ。期中に必要な平均の数量）

終了コード: エラーがあれば 1（--check で食い違いがあった場合を含む）、なければ 0。
macOS / Linux / Windows で動くように、標準ライブラリだけで書く（Python 3.9 以上）。
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

BLOCK_RE = re.compile(r"```json speckit-plan\s*\n(.*?)\n```", re.DOTALL)
BEGIN = "<!-- speckit-plan:begin（plan.py --write が生成する。手で編集しない） -->"
END = "<!-- speckit-plan:end -->"
MARKER_RE = re.compile(re.escape(BEGIN) + r"\n.*?" + re.escape(END), re.DOTALL)


class PlanError(Exception):
    pass


def load_plan(text: str) -> dict:
    blocks = BLOCK_RE.findall(text)
    if len(blocks) != 1:
        raise PlanError(f"```json speckit-plan のブロックが {len(blocks)} 個ある（1 個にする）")
    try:
        plan = json.loads(blocks[0])
    except json.JSONDecodeError as error:
        raise PlanError(f"speckit-plan の JSON を読めない: {error}") from error
    validate_plan(plan)
    return plan


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numbers(value, count: int, where: str) -> list[float]:
    if not isinstance(value, list) or len(value) != count:
        raise PlanError(f"{where}: 期の数（{count}）と同じ長さの数値の配列にする")
    for v in value:
        if not _is_number(v):
            raise PlanError(f"{where}: 数値でない値がある（{v!r}）")
    return [float(v) for v in value]


def validate_plan(plan: dict) -> None:
    periods = plan.get("periods")
    if not isinstance(periods, list) or not periods:
        raise PlanError("periods: 期の名前の配列にする（例: [\"1年目\", \"2年目\", \"3年目\"]）")
    n = len(periods)
    months = plan.get("months_per_period", 12)
    if not isinstance(months, int) or isinstance(months, bool) or months <= 0:
        raise PlanError("months_per_period: 1 以上の整数にする")
    scenarios = plan.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        raise PlanError("scenarios: シナリオ名をキーにした辞書にする（例: 楽観、標準、悲観）")
    for name, sc in scenarios.items():
        where = f"scenarios.{name}"
        if not isinstance(sc, dict):
            raise PlanError(f"{where}: revenue と costs を持つ辞書にする")
        revenue = sc.get("revenue")
        if not isinstance(revenue, list) or not revenue:
            raise PlanError(f"{where}.revenue: 収益の項目を 1 つ以上書く")
        for i, item in enumerate(revenue):
            w = f"{where}.revenue[{i}]"
            if not isinstance(item, dict):
                raise PlanError(f"{w}: name、unit_price、volume を持つ辞書にする")
            if not item.get("name"):
                raise PlanError(f"{w}.name がない")
            if not _is_number(item.get("unit_price")):
                raise PlanError(f"{w}.unit_price（月額の単価）がない、または数値でない")
            _numbers(item.get("volume"), n, f"{w}.volume（期中の平均の数量）")
        costs = sc.get("costs", [])
        if not isinstance(costs, list):
            raise PlanError(f"{where}.costs: 費用の項目の配列にする")
        for i, item in enumerate(costs):
            w = f"{where}.costs[{i}]"
            if not isinstance(item, dict):
                raise PlanError(f"{w}: name と monthly / per_period / rate のどれか 1 つを持つ辞書にする")
            if not item.get("name"):
                raise PlanError(f"{w}.name がない")
            kinds = [k for k in ("monthly", "per_period", "rate") if k in item]
            if len(kinds) != 1:
                raise PlanError(f"{w}: monthly（月額の固定費）、per_period（期ごとの費用）、rate（売上に対する率）のどれか 1 つを書く")
            if kinds[0] == "rate":
                rate = item["rate"]
                if not _is_number(rate) or not 0 <= rate < 1:
                    raise PlanError(f"{w}.rate: 0 以上 1 未満の数値にする")
            else:
                _numbers(item[kinds[0]], n, f"{w}.{kinds[0]}")
        if sum(c["rate"] for c in costs if "rate" in c) >= 1:
            raise PlanError(f"{where}.costs: 変動費の率の合計が 1 以上になっている（売上をすべて費用が上回る）")
        initial = sc.get("initial_investment", 0)
        if not _is_number(initial) or initial < 0:
            raise PlanError(f"{where}.initial_investment: 0 以上の数値にする")


def compute(plan: dict) -> dict:
    n = len(plan["periods"])
    months = plan.get("months_per_period", 12)
    result = {}
    for name, sc in plan["scenarios"].items():
        revenue = [0.0] * n
        for item in sc["revenue"]:
            vol = _numbers(item["volume"], n, "")
            for p in range(n):
                revenue[p] += item["unit_price"] * vol[p] * months
        rate_total = sum(c["rate"] for c in sc.get("costs", []) if "rate" in c)
        fixed_monthly = [0.0] * n
        per_period = [0.0] * n
        for c in sc.get("costs", []):
            if "monthly" in c:
                for p, v in enumerate(_numbers(c["monthly"], n, "")):
                    fixed_monthly[p] += v
            elif "per_period" in c:
                for p, v in enumerate(_numbers(c["per_period"], n, "")):
                    per_period[p] += v
        costs = [fixed_monthly[p] * months + per_period[p] + revenue[p] * rate_total for p in range(n)]
        profit = [revenue[p] - costs[p] for p in range(n)]
        cumulative, total = [], -float(sc.get("initial_investment", 0))
        for p in range(n):
            total += profit[p]
            cumulative.append(total)
        lowest = min([-float(sc.get("initial_investment", 0))] + cumulative)
        break_even = None
        if len(sc["revenue"]) == 1:
            margin = sc["revenue"][0]["unit_price"] * (1 - rate_total)
            if margin > 0:
                # 期ごとの費用（広告、外注など）も月割りして固定費に含める
                break_even = [math.ceil((fixed_monthly[p] + per_period[p] / months) / margin) for p in range(n)]
        result[name] = {
            "revenue": revenue, "costs": costs, "profit": profit, "cumulative": cumulative,
            "required_funding": -lowest if lowest < 0 else 0.0,
            "break_even": break_even, "break_even_unit": sc["revenue"][0].get("unit", ""),
        }
    return result


def yen(value: float) -> str:
    return f"{round(value):,}"


def render(plan: dict, result: dict) -> str:
    periods = plan["periods"]
    currency = plan.get("currency", "JPY")
    lines = [BEGIN, ""]
    for name, r in result.items():
        lines.append(f"#### {name}（単位: {currency}）")
        lines.append("")
        lines.append("| 項目 | " + " | ".join(periods) + " |")
        lines.append("|---|" + "---:|" * len(periods))
        for label, key in (("売上", "revenue"), ("費用", "costs"), ("損益", "profit"), ("累積損益", "cumulative")):
            lines.append(f"| {label} | " + " | ".join(yen(v) for v in r[key]) + " |")
        if r["break_even"] is not None:
            unit = f"（{r['break_even_unit']}）" if r["break_even_unit"] else ""
            lines.append(f"| 損益分岐の数量{unit} | " + " | ".join(f"{v:,}" for v in r["break_even"]) + " |")
        lines.append("")
        lines.append(f"- 必要資金（累積損益の最小値の不足分。初期投資を含む）: {yen(r['required_funding'])}")
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    path = Path(args[0])
    try:
        text = path.read_text(encoding="utf-8")
        plan = load_plan(text)
        rendered = render(plan, compute(plan))
        if "--write" in argv:
            if MARKER_RE.search(text):
                new_text = MARKER_RE.sub(lambda _m: rendered, text, count=1)
            else:
                raise PlanError(f"{path} にマーカー（{BEGIN} と {END}）がない。収支表を置く場所に 2 行を書く")
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(new_text)
            print(f"{path} の収支表を更新した")
        elif "--check" in argv:
            m = MARKER_RE.search(text)
            if not m:
                raise PlanError(f"{path} にマーカーがない")
            if m.group(0).strip() != rendered.strip():
                raise PlanError("収支表が前提と一致しない。plan.py --write で更新する")
            print("収支表は前提と一致している")
        else:
            print(rendered)
    except (PlanError, OSError) as error:
        print(f"[エラー] {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
