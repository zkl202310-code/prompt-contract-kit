#!/usr/bin/env python3
"""对从网页端（ChatGPT / Kimi 等）人工贴回的 A/B 输出做盲判（量规 v1，X/Y 随机）。
记录文件格式见 live_record_template.md。结果目录 runs/chatgpt_live/<任务>_<组>_r<轮>/judge_AB/verdict.json；
汇总 results_chatgpt_live.json|md，按组（Thinking / Instant）分别给 W-T-L、胜率、长度比与门。
--self-test：用 runs/sol_medium 的两题既有输出拼成记录，判一次并与既有 verdict 方向对比。"""
import argparse, json, re, sys, hashlib, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval as E

CRITS = ["answers_question", "no_fabrication", "directly_usable", "fidelity", "overall"]
NO_REF = "（无预设参考，只按原始任务与材料判定）"
HDR = re.compile(r"^## +(\S+?) *\| *组[:：] *(\S+?) *\| *轮[:：] *(\d+)", re.M)

def load_holdout(path):
    tasks = {}
    for line in Path(path).read_text().splitlines():
        m = re.match(r"^\| *([NR]\d+) *\| *([^|]+?) *\| *(.+?) *\|$", line)
        if m: tasks[m.group(1)] = {"id": m.group(1), "场景": m.group(2), "raw_prompt": m.group(3)}
    return tasks

def parse_record(path):
    text = Path(path).read_text()
    heads = list(HDR.finditer(text)); recs = []
    for i, h in enumerate(heads):
        body = text[h.end(): heads[i+1].start() if i+1 < len(heads) else len(text)]
        secs = {}
        # 只认六个固定小节名，回答正文里自带的 ### 标题不会被当成分节
        SEC = r"^### +(契约|A|B|备注|任务原话|材料) *$"
        for m in re.finditer(SEC + r"\n(.*?)(?=" + SEC + r"|\Z)", body, re.M | re.S):
            secs[m.group(1)] = m.group(2).strip()
        if not secs.get("A") or not secs.get("B"): continue  # 空模板行跳过
        if not (E.SAFE_ID.fullmatch(h.group(1)) and E.SAFE_ID.fullmatch(h.group(2))):
            print(f"[skip] 任务号/组名含不允许的字符（只允许字母数字_-）：{h.group(1)} {h.group(2)}", file=sys.stderr); continue
        recs.append({"task": h.group(1), "group": h.group(2), "round": int(h.group(3)), **secs})
    keys = [(r["task"], r["group"], r["round"]) for r in recs]
    dup = {k for k in keys if keys.count(k) > 1}
    if dup: raise ValueError(f"记录重复（任务/组/轮）：{sorted(dup)}；请合并或改轮次")
    return recs

def rec_sig(rec, task):
    """签名覆盖判官看到的一切：A/B 输出、贴回的任务原话与材料、留出集里的场景与原话。"""
    return E.pair_sig(rec["A"], rec["B"], rec.get("任务原话") or "", rec.get("材料") or "", json.dumps(task, ensure_ascii=False, sort_keys=True))

def judge(rec, task, runs, model, effort):
    out = E.safe_child(runs, f"{rec['task']}_{rec['group']}_r{rec['round']}", "judge_AB")
    a, b = rec["A"], rec["B"]
    sig = rec_sig(rec, task); jcfg = E.judge_cfg(model, effort, E.JUDGE_TPL)
    if E.verdict_fresh(out / "verdict.json", sig, jcfg): return  # 记录内容、题面或判官配置变了就重判
    seed = int(hashlib.md5(f"live{rec['task']}{rec['group']}{rec['round']}".encode()).hexdigest(), 16)
    flip = random.Random(seed).random() < 0.5
    X, Y = (b, a) if flip else (a, b); mapping = {"X": "B" if flip else "A", "Y": "A" if flip else "B"}
    raw = rec.get("任务原话") or task.get("raw_prompt", "（见材料）")
    prompt = E.JUDGE_TPL.format(scene=task.get("场景", "未知"), raw=raw, attachment=rec.get("材料") or "见任务原话中的材料说明；判官不得假定材料内容",
                                points=NO_REF, fail=NO_REF, X=X, Y=Y)
    r = E.codex_run(prompt, model, effort, out, schema=E.JUDGE_SCHEMA)
    txt = E.strip_fence(r["output"])
    try: v = json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S); v = json.loads(m.group()) if m else {"parse_error": txt}
    v.update({"_mapping": mapping, "_lenX": len(X), "_lenY": len(Y), "_judge": f"{model}/{effort}", "_group": rec["group"], "_round": rec["round"], "_sig": sig, "_judge_cfg": jcfg})
    E.safe_write(out / "verdict.json", json.dumps(v, ensure_ascii=False, indent=1))

def aggregate(recs, runs, stem, expect=None, tasks=None, jcfg=None):
    groups = {}
    for rec in recs:
        vp = runs / f"{rec['task']}_{rec['group']}_r{rec['round']}" / "judge_AB" / "verdict.json"
        if not vp.exists(): continue
        v = json.loads(vp.read_text())
        if "parse_error" in v: continue
        if not E.verdict_valid(v, rec_sig(rec, (tasks or {}).get(rec["task"], {})), jcfg): print(f"[warn] {rec['task']} {rec['group']} r{rec['round']}: verdict 过期（记录、题面或判官配置已变），已忽略", file=sys.stderr); continue
        g = groups.setdefault(rec["group"], {"agg": {c: {"win": 0, "tie": 0, "loss": 0} for c in CRITS}, "lens": [], "rows": []})
        for c in CRITS: g["agg"][c][E.decode(v, c, "B")] += 1
        lb = v["_lenX"] if v["_mapping"]["X"] == "B" else v["_lenY"]; la = v["_lenY"] if v["_mapping"]["X"] == "B" else v["_lenX"]
        g["lens"].append(lb / max(la, 1))
        g["rows"].append({"task": rec["task"], "round": rec["round"], "overall": E.decode(v, "overall", "B"), "len_ratio": round(lb / max(la, 1), 2), "reason": v.get("reason", "")})
    res = {}; lines = [f"# ChatGPT 内实测汇总（{stem}）", ""]
    for gname, g in groups.items():
        n = sum(g["agg"]["overall"].values()); o = g["agg"]["overall"]; nf = g["agg"]["no_fabrication"]
        wr = round(o["win"] / n, 3) if n else None; lr = round(sum(g["lens"]) / len(g["lens"]), 2) if g["lens"] else None
        lr_raw = (sum(g["lens"]) / len(g["lens"])) if g["lens"] else None
        # 与 run_eval 同一套预注册门：总体 ≥ 0.55、不编造负 ≤ 2、长度比 ≤ 1.5（网页端记录无「题数完整」项，n 需自行核对）
        wr_raw = (o["win"] / n) if n else 0
        # 门：总体 ≥ 0.55（原始比例）、不编造负 ≤ 2、长度比 ≤ 1.5、且判定数 = --expect（每组预期记录数；不给就不算通过）
        gate = {"win_rate_ge_0.55": wr_raw >= 0.55, "nofab_loss_le_2": nf["loss"] <= 2, "len_ratio_le_1.5": (lr_raw if lr_raw is not None else 9) <= 1.5,
                "complete": (expect is not None and n == expect)}; gate["pass"] = all(gate.values())
        if not gate["complete"]: print(f"[warn] 组 {gname}: 判定 {n} 条，预期 {expect}（未给 --expect 或不相等），不算通过", file=sys.stderr)
        res[gname] = {"n": n, "overall_win_rate": wr, "mean_len_ratio": lr, "by_criterion": g["agg"], "gate": gate, "rows": g["rows"]}
        lines += [f"## 组：{gname}", f"- n = {n}，总体 B 对 A = {o['win']}-{o['tie']}-{o['loss']}（{wr}），长度比 {lr}，门 {json.dumps(gate, ensure_ascii=False)}", "", "| 判项 | 胜 | 平 | 负 |", "|---|---|---|---|"]
        lines += [f"| {c} | {g['agg'][c]['win']} | {g['agg'][c]['tie']} | {g['agg'][c]['loss']} |" for c in CRITS]
        lines += ["", "| 任务 | 轮 | overall | 长度比 | 判官理由 |", "|---|---|---|---|---|"]
        lines += [f"| {r['task']} | {r['round']} | {r['overall']} | {r['len_ratio']} | {r['reason']} |" for r in g["rows"]]; lines.append("")
    E.safe_write(E.RESULTS / f"{stem}.json", json.dumps(res, ensure_ascii=False, indent=1)); E.safe_write(E.RESULTS / f"{stem}.md", "\n".join(lines))
    for gname, r in res.items(): print(gname, "n", r["n"], "win_rate", r["overall_win_rate"], "len", r["mean_len_ratio"], "gate", r["gate"])
    return res

def build_selftest(runs_src, ids):
    """用既有 CLI 输出拼一份记录文件，验证解析与判官链路。"""
    tasks = {t["id"]: t for t in E.load_tasks(ids)}
    parts = []
    for tid in ids:
        a = json.loads((E.EVAL / runs_src / tid / "exec_A" / "result.json").read_text())["output"]
        b = json.loads((E.EVAL / runs_src / tid / "exec_B" / "result.json").read_text())["output"]
        parts.append(f"## {tid} | 组: selftest | 轮: 1\n### 任务原话\n{tasks[tid]['raw_prompt']}\n### 材料\n{tasks[tid].get('attachment') or '无'}\n### A\n{a}\n### B\n{b}\n")
    p = E.RUNS_ROOT / "chatgpt_live_selftest_record.md"; E.safe_write(p, "\n".join(parts)); return p, tasks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", default="live_record.md"); ap.add_argument("--tasks", default="tasks_holdout.md")
    ap.add_argument("--runs", default="runs/chatgpt_live"); ap.add_argument("--stem", default="results_chatgpt_live")
    ap.add_argument("--judge-model", default="gpt-6-astra"); ap.add_argument("--judge-effort", default="high"); ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--expect", type=int, default=None, help="每组预期记录数（如 20 题 + 5 题重复 = 25）；不给则任何组都不算通过")
    a = ap.parse_args()
    if a.self_test:
        src = E.EVAL / "runs/sol_medium"
        if not (src / "T01" / "exec_B" / "result.json").exists(): sys.exit("自检需要先跑过 `run_eval.py --variant sol_medium`（至少 T01、T02 两题）")
        rec_path, tasks = build_selftest("runs/sol_medium", ["T01", "T02"]); a.runs = "runs/chatgpt_live_selftest"; a.stem = "results_chatgpt_live_selftest"
        for t in tasks.values(): t["场景"] = t["场景"]
    else:
        rec_path = E.EVAL / a.record; tasks = load_holdout(E.EVAL / a.tasks)
    if not E.SAFE_SEG.fullmatch(a.stem): sys.exit("--stem 只允许字母数字_-")
    recs = parse_record(rec_path); runs = E.safe_runs(a.runs); runs.mkdir(parents=True, exist_ok=True)
    print(f"records: {len(recs)}", flush=True)
    errs = []
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(judge, r, tasks.get(r["task"], {}), runs, a.judge_model, a.judge_effort): (r["task"], r["group"], r["round"]) for r in recs}
        for f in as_completed(futs):
            try: f.result(); print("ok", *futs[f], flush=True)
            except Exception as e: errs.append(futs[f]); print("ERR", *futs[f], str(e)[:200], flush=True)
    res = aggregate(recs, runs, a.stem, expect=(2 if a.self_test else a.expect), tasks=tasks, jcfg=E.judge_cfg(a.judge_model, a.judge_effort, E.JUDGE_TPL))
    if a.self_test:
        for tid in ("T01", "T02"):
            old = json.loads((E.EVAL / "runs/sol_medium" / tid / "judge_AB" / "verdict.json").read_text())
            new = json.loads((runs / f"{tid}_selftest_r1" / "judge_AB" / "verdict.json").read_text())
            print(tid, "既有 overall:", E.decode(old, "overall", "B"), "本次 overall:", E.decode(new, "overall", "B"))
    if errs: print("ERRORS", len(errs)); sys.exit(1)

if __name__ == "__main__": main()
