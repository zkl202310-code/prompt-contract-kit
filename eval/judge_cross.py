#!/usr/bin/env python3
"""事后诊断用：用指定判官模型重判某个 runs 目录里的既有输出对（量规 v1）。
用途：拆分「判官口味」与「执行模型」两个混杂因素。结果写到 judge_<pair>_<suffix>/verdict.json。"""
import argparse, json, hashlib, random, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval as E
JUDGE_TPL = (E.EVAL / "judge_prompt.md").read_text()
CRITS = ["answers_question", "no_fabrication", "directly_usable", "fidelity", "overall"]

def judge(runs, t, pair, model, effort, suffix):
    out = E.safe_child(runs, t["id"], f"judge_{pair}_{suffix}")
    a, b = pair[0], pair[1]
    oa = E.exec_output(E.safe_child(runs, t["id"], f"exec_{a}")); ob = E.exec_output(E.safe_child(runs, t["id"], f"exec_{b}"))
    sig = E.pair_sig(oa, ob, E.task_basis(t)); jcfg = E.judge_cfg(model, effort, JUDGE_TPL)
    if E.verdict_fresh(out / "verdict.json", sig, jcfg): return  # 输出、题面或判官模型/档位/模板任一变化都重判
    seed = int(hashlib.md5(f"{suffix}{t['id']}{pair}".encode()).hexdigest(), 16)
    flip = random.Random(seed).random() < 0.5
    X, Y = (ob, oa) if flip else (oa, ob)
    mapping = {"X": b if flip else a, "Y": a if flip else b}
    prompt = JUDGE_TPL.format(scene=t["场景"], raw=t["raw_prompt"], attachment=t.get("attachment") or "无",
                              points="；".join(t["期望要点"]), fail=t["典型失败"], X=X, Y=Y)
    rec = E.codex_run(prompt, model, effort, out, schema=E.JUDGE_SCHEMA)
    txt = E.strip_fence(rec["output"])
    try: v = json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S); v = json.loads(m.group()) if m else {"parse_error": txt}
    v["_mapping"] = mapping; v["_lenX"] = len(X); v["_lenY"] = len(Y); v["_judge"] = f"{model}/{effort}"; v["_sig"] = sig; v["_judge_cfg"] = jcfg
    E.safe_write(out / "verdict.json", json.dumps(v, ensure_ascii=False, indent=1))

def summarize(runs, tasks, pair, treat, suffix, jcfg):
    agg = {c: {"win": 0, "tie": 0, "loss": 0} for c in CRITS}; lens = []; rows = []
    for t in tasks:
        vp = runs / t["id"] / f"judge_{pair}_{suffix}" / "verdict.json"
        if not vp.exists(): continue
        v = json.loads(vp.read_text())
        if "parse_error" in v: continue
        try: cur = E.pair_sig(E.exec_output(runs / t["id"] / f"exec_{pair[0]}"), E.exec_output(runs / t["id"] / f"exec_{pair[1]}"), E.task_basis(t))
        except Exception: print(f"[warn] {t['id']} {pair}: 执行结果失败或缺失，verdict 不计", file=sys.stderr); continue
        if not E.verdict_valid(v, cur, jcfg): print(f"[warn] {t['id']} {pair}: verdict 过期（输出、题面或判官配置已变），已忽略", file=sys.stderr); continue
        for c in CRITS: agg[c][E.decode(v, c, treat)] += 1
        lt = v["_lenX"] if v["_mapping"]["X"] == treat else v["_lenY"]; lo = v["_lenY"] if v["_mapping"]["X"] == treat else v["_lenX"]
        lens.append(lt / max(lo, 1)); rows.append({"task": t["id"], "overall": E.decode(v, "overall", treat), "reason": v.get("reason", "")})
    n = sum(agg["overall"].values())
    return {"pair": pair, "treat": treat, "suffix": suffix, "n": n, "overall_win_rate": round(agg["overall"]["win"] / n, 3) if n else None,
            "mean_len_ratio": round(sum(lens) / len(lens), 2) if lens else None, "by_criterion": agg, "rows": rows}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True); ap.add_argument("--pairs", required=True, help="如 AB:B,AI:I（pair:处理组）")
    ap.add_argument("--judge-model", required=True); ap.add_argument("--judge-effort", default="high")
    ap.add_argument("--suffix", required=True); ap.add_argument("--workers", type=int, default=2); ap.add_argument("--tasks", default="")
    a = ap.parse_args()
    runs = E.safe_runs(a.runs); tasks = E.load_tasks([x for x in a.tasks.split(",") if x])
    if not E.SAFE_SEG.fullmatch(a.suffix): sys.exit("--suffix 只允许字母数字_-")
    pairs = [p.split(":") for p in a.pairs.split(",")]
    if any(len(x) != 2 or not re.fullmatch(r"[ABCI]{2}", x[0]) or x[1] not in ("A", "B", "C", "I") for x in pairs): sys.exit("--pairs 形如 AB:B,AI:I")
    errs = []
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(judge, runs, t, p, a.judge_model, a.judge_effort, a.suffix): (t["id"], p) for t in tasks for p, _ in pairs}
        for f in as_completed(futs):
            try: f.result(); print("ok", *futs[f], flush=True)
            except Exception as e: errs.append(futs[f]); print("ERR", *futs[f], str(e)[:200], flush=True)
    jcfg = E.judge_cfg(a.judge_model, a.judge_effort, JUDGE_TPL)
    out = {f"{p}_{a.suffix}": summarize(runs, tasks, p, tr, a.suffix, jcfg) for p, tr in pairs}
    E.RESULTS.mkdir(exist_ok=True)
    E.safe_write(E.RESULTS / f"results_cross_{runs.name}_{a.suffix}.json", json.dumps(out, ensure_ascii=False, indent=1))
    for k, v in out.items(): print(k, "n", v["n"], "win_rate", v["overall_win_rate"], "len", v["mean_len_ratio"], json.dumps(v["by_criterion"]["overall"]))
    if errs: print("ERRORS", len(errs)); sys.exit(1)

if __name__ == "__main__": main()
