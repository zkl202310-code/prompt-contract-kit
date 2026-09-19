#!/usr/bin/env python3
"""v2 人工盲评表：只填「总体」+ 一句理由；参数：variant(= runs/ 下子目录名) N seed。顺序与模型判官一致（读 judge_AB/verdict.json 的 _mapping）。"""
import json, random, sys
from pathlib import Path
EVAL = Path(__file__).resolve().parent
variant = sys.argv[1] if len(sys.argv) > 1 else "sol_medium"; N = int(sys.argv[2]) if len(sys.argv) > 2 else 10; seed = int(sys.argv[3]) if len(sys.argv) > 3 else 20260906
import run_eval as E
RUNS = E.safe_runs(f"runs/{variant}")  # variant = runs 子目录名
E.RESULTS.mkdir(exist_ok=True)
tasks = [json.loads(l) for l in (EVAL / "tasks_v1.jsonl").read_text().splitlines() if l.strip()]
done = [t for t in tasks if (RUNS / t["id"] / "judge_AB" / "verdict.json").exists()]
pick = random.Random(seed).sample(done, min(N, len(done)))
sheet = ["---", f"created: {__import__('datetime').date.today()}", "公开性: 需脱敏", f"source: make_calibration_sheet_v2.py {variant}（A vs B，顺序与模型判官一致）", "---", "",
         f"# 人工盲评表 · {variant}（A vs B，只填总体）", "", "> 每对只判「眼前这两份哪份更好」：X / Y / 平，加一句理由。不熟悉的任务写「弃权」。填完把每个任务的「我的判定」行发回即可。", ""]
answers = {}
for t in pick:
    v = json.loads((RUNS / t["id"] / "judge_AB" / "verdict.json").read_text()); m = v["_mapping"]; answers[t["id"]] = m
    outs = {c: json.loads((RUNS / t["id"] / f"exec_{c}" / "result.json").read_text())["output"] for c in ("A", "B")}
    X, Y = outs[m["X"]], outs[m["Y"]]
    sheet += [f"## {t['id']} · {t['场景']}", f"**原始任务**：{t['raw_prompt']}"]
    if t.get("attachment"): sheet += ["**材料**：", "```", t["attachment"], "```"]
    sheet += ["", "### 回答 X", "", X.strip(), "", "### 回答 Y", "", Y.strip(), "", "### 我的判定", "总体（X / Y / 平 / 弃权）：", "理由：", "", "---", ""]
E.safe_write(E.RESULTS / f"human_sheet_{variant}.md", "\n".join(sheet))
E.safe_write(E.RESULTS / f"human_key_{variant}.json", json.dumps(answers, ensure_ascii=False, indent=1))
print("sheet:", len(pick), "pairs ->", E.RESULTS / f"human_sheet_{variant}.md")
