#!/usr/bin/env python3
"""一步式补测 harness：执行 = gpt-6-astra medium（A / B 两步 / I 一步），判官 = gpt-5.6-sol high（量规 v1）。
复用 run_eval.py 的 codex_run / 判官逻辑；每次调用保存 events.jsonl（含 turn.completed.usage）。"""
import argparse, json, sys, hashlib, random, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval as E

EVAL = E.EVAL
VARIANTS = {
    # 一步式 I：优化器与任务同对话，契约不输出；对 A（原始）与对 B（两步式）各判一遍
    "astra_inline": {"runs": "runs/astra_inline", "optB": "../optimizers/task-contract-optimizer.zh.md", "optI": "../optimizers/task-contract-optimizer-inline.zh.md",
                     "stem": "results_astra_inline", "reuseA": None, "exec_model": "gpt-6-astra", "judge_model": "gpt-5.6-sol"},
    "sol_inline": {"runs": "runs/sol_inline", "optB": "../optimizers/task-contract-optimizer.zh.md", "optI": "../optimizers/task-contract-optimizer-inline.zh.md",
                   "stem": "results_sol_inline", "reuseA": "runs/sol_medium", "reuseB": "runs/sol_medium", "exec_model": "gpt-5.6-sol", "judge_model": "gpt-6-astra", "pairs": {"AI": "I", "BI": "I"}},
}
RUNS = EVAL / VARIANTS["astra_inline"]["runs"]
WRAPPER = E.WRAP
OPT_B = EVAL / VARIANTS["astra_inline"]["optB"]
OPT_I = EVAL / VARIANTS["astra_inline"]["optI"]
STEM = "results_inline"
CFG = {"exec_model": "gpt-6-astra", "exec_effort": "medium", "judge_model": "gpt-5.6-sol", "judge_effort": "high"}
JUDGE_TPL = (EVAL / "judge_prompt.md").read_text()
PAIRS = {"AI": "I", "BI": "I", "AB": "B"}   # pair -> treat
CRITS = ["answers_question", "no_fabrication", "directly_usable", "fidelity", "overall"]

def done(d): 
    p = d / "result.json"
    return p.exists() and not json.loads(p.read_text()).get("failed")

def opt_B(t):
    out = E.safe_child(RUNS, t["id"], "opt_B")
    if E.restore_optimized_prompt(out): return
    prompt = WRAPPER + OPT_B.read_text() + "\n\n---\n\n用户的原始任务如下（含其附带材料，原样）：\n\n" + E.raw_task_prompt(t)
    rec = E.codex_run(prompt, CFG["exec_model"], CFG["exec_effort"], out)
    E.safe_write(out / "optimized_prompt.md", E.strip_fence(rec["output"]))

def exec_cond(t, cond):
    out = E.safe_child(RUNS, t["id"], f"exec_{cond}")
    if done(out): return
    if cond == "A": prompt = WRAPPER + E.raw_task_prompt(t)
    elif cond == "B":
        opt = E.safe_child(RUNS, t["id"], "opt_B")
        if not E.restore_optimized_prompt(opt): raise RuntimeError(f"optimization missing or failed, not executing: {opt}")
        prompt = WRAPPER + (opt / "optimized_prompt.md").read_text()
    elif cond == "I": prompt = WRAPPER + OPT_I.read_text() + "\n\n---\n\n用户任务：\n\n" + E.raw_task_prompt(t)
    E.codex_run(prompt, CFG["exec_model"], CFG["exec_effort"], out)

def judge(t, pair):
    out = E.safe_child(RUNS, t["id"], f"judge_{pair}")
    a, b = pair[0], pair[1]
    oa = E.exec_output(E.safe_child(RUNS, t["id"], f"exec_{a}")); ob = E.exec_output(E.safe_child(RUNS, t["id"], f"exec_{b}"))
    sig = E.pair_sig(oa, ob, E.task_basis(t)); jcfg = E.judge_cfg(CFG["judge_model"], CFG["judge_effort"], JUDGE_TPL)
    if E.verdict_fresh(out / "verdict.json", sig, jcfg): return
    seed = int(hashlib.md5(f"inline{t['id']}{pair}".encode()).hexdigest(), 16)
    flip = random.Random(seed).random() < 0.5
    X, Y = (ob, oa) if flip else (oa, ob)
    mapping = {"X": b if flip else a, "Y": a if flip else b}
    prompt = JUDGE_TPL.format(scene=t["场景"], raw=t["raw_prompt"], attachment=t.get("attachment") or "无",
                              points="；".join(t["期望要点"]), fail=t["典型失败"], X=X, Y=Y)
    rec = E.codex_run(prompt, CFG["judge_model"], CFG["judge_effort"], out, schema=E.JUDGE_SCHEMA)
    txt = E.strip_fence(rec["output"])
    try: v = json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S); v = json.loads(m.group()) if m else {"parse_error": txt}
    v["_mapping"] = mapping; v["_lenX"] = len(X); v["_lenY"] = len(Y); v["_sig"] = sig; v["_judge_cfg"] = jcfg
    E.safe_write(out / "verdict.json", json.dumps(v, ensure_ascii=False, indent=1))

def aggregate(tasks):
    jcfg = E.judge_cfg(CFG["judge_model"], CFG["judge_effort"], JUDGE_TPL)
    res = {}
    for pair, treat in PAIRS.items():
        agg = {c: {"win": 0, "tie": 0, "loss": 0} for c in CRITS}; rows = []; lens = []
        for t in tasks:
            vp = RUNS / t["id"] / f"judge_{pair}" / "verdict.json"
            if not vp.exists(): continue
            v = json.loads(vp.read_text())
            if "parse_error" in v: continue
            try: cur = E.pair_sig(E.exec_output(RUNS / t["id"] / f"exec_{pair[0]}"), E.exec_output(RUNS / t["id"] / f"exec_{pair[1]}"), E.task_basis(t))
            except Exception: print(f"[warn] {t['id']} {pair}: 执行结果失败或缺失，verdict 不计", file=sys.stderr); continue
            if not E.verdict_valid(v, cur, jcfg): print(f"[warn] {t['id']} {pair}: verdict 过期（输出、题面或判官配置已变），已忽略", file=sys.stderr); continue
            for c in CRITS: agg[c][E.decode(v, c, treat)] += 1
            lt = v["_lenX"] if v["_mapping"]["X"] == treat else v["_lenY"]
            lo = v["_lenY"] if v["_mapping"]["X"] == treat else v["_lenX"]
            lens.append(lt / max(lo, 1))
            rows.append({"task": t["id"], "overall": E.decode(v, "overall", treat), "reason": v.get("reason", ""), "len_ratio": round(lt / max(lo, 1), 2)})
        n = sum(agg["overall"].values())
        res[pair] = {"n": n, "treat": treat, "control": pair[0] if pair[1] == treat else pair[1], "by_criterion": agg,
                     "overall_win_rate": round(agg["overall"]["win"] / n, 3) if n else None,
                     "mean_len_ratio": round(sum(lens) / len(lens), 2) if lens else None, "_mean_len_ratio_raw": (sum(lens) / len(lens)) if lens else None, "_overall_win_rate_raw": (agg["overall"]["win"] / n) if n else None, "rows": rows}
    tot = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0, "calls": 0}
    by_model = {}
    for rj in RUNS.rglob("result.json"):
        r = json.loads(rj.read_text()); u = r.get("usage") or {}
        for k in list(tot)[:-1]: tot[k] += u.get(k, 0)
        tot["calls"] += 1
        bm = by_model.setdefault(r.get("model"), {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        bm["calls"] += 1; bm["input_tokens"] += u.get("input_tokens", 0); bm["output_tokens"] += u.get("output_tokens", 0)
    res["usage_total"] = tot; res["usage_by_model"] = by_model
    ai = res.get("AI")
    # 预注册门（与 run_eval 同一套，见 eval/README.md「门槛版本」）：I 对 A 总体 ≥ 0.55、不编造负 ≤ 2、长度比 ≤ 1.5、题数完整
    if ai:
        nf = ai["by_criterion"]["no_fabrication"]; lr = ai.get("_mean_len_ratio_raw")
        res["gate_inline"] = {"I_vs_A_win_rate_ge_0.55": (ai.get("_overall_win_rate_raw") or 0) >= 0.55, "I_no_fabrication_loss_le_2": nf["loss"] <= 2,
                              "len_ratio_le_1.5": (lr if lr is not None else 9) <= 1.5, "complete": ai["n"] == len(tasks)}
    else:
        res["gate_inline"] = {"I_vs_A_win_rate_ge_0.55": False, "I_no_fabrication_loss_le_2": False, "len_ratio_le_1.5": False, "complete": False}
    res["gate_inline"]["pass"] = all(res["gate_inline"].values())
    if not res["gate_inline"]["complete"]: print(f"[warn] AI 判定 {ai['n'] if ai else 0}/{len(tasks)} 题，结果不完整，不算通过", file=sys.stderr)
    E.RESULTS.mkdir(exist_ok=True)
    E.safe_write(E.RESULTS / f"{STEM}.json", json.dumps(res, ensure_ascii=False, indent=1))
    lines = [f"# 结果汇总（自动生成，{STEM}）", "", f"预注册门（见 eval/README.md）：{json.dumps(res['gate_inline'], ensure_ascii=False)}", ""]
    for pair, treat in PAIRS.items():
        if pair not in res: continue
        r = res[pair]
        lines += [f"## {pair}（处理组 = {treat}；对照 = {r['control']}）", f"- n = {r['n']}，overall 胜率 = {r['overall_win_rate']}，处理组平均长度比 = {r['mean_len_ratio']}", "", "| 判项 | 胜 | 平 | 负 |", "|---|---|---|---|"]
        for c in CRITS: a = r["by_criterion"][c]; lines.append(f"| {c} | {a['win']} | {a['tie']} | {a['loss']} |")
        lines += ["", "| 任务 | overall | 长度比 | 判官理由 |", "|---|---|---|---|"]
        for row in r["rows"]: lines.append(f"| {row['task']} | {row['overall']} | {row['len_ratio']} | {row['reason']} |")
        lines.append("")
    lines.append(f"用量合计：{json.dumps(tot, ensure_ascii=False)}"); lines.append(f"按模型：{json.dumps(by_model, ensure_ascii=False)}")
    E.safe_write(E.RESULTS / f"{STEM}.md", "\n".join(lines))
    print(json.dumps({k: ({kk: vv for kk, vv in v.items() if kk != 'rows'} if isinstance(v, dict) else v) for k, v in res.items()}, ensure_ascii=False, indent=1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="", help="只执行指定题目；汇总始终覆盖完整任务集"); ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--phase", default="all", choices=["optimize", "execute", "judge", "aggregate", "all"])
    ap.add_argument("--variant", default="astra_inline", choices=list(VARIANTS))
    a = ap.parse_args()
    global RUNS, OPT_B, OPT_I, STEM, PAIRS
    V = VARIANTS[a.variant]; RUNS = E.safe_runs(V["runs"]); OPT_B = EVAL / V["optB"]; OPT_I = EVAL / V["optI"]; STEM = V["stem"]
    if V.get("exec_model"): CFG["exec_model"] = V["exec_model"]
    if V.get("judge_model"): CFG["judge_model"] = V["judge_model"]
    if V.get("pairs"): PAIRS = V["pairs"]
    cfg_now = {"variant": a.variant, "optB": str(OPT_B.resolve()), "optI": str(OPT_I.resolve()), "tasks": str(E.TASKS.resolve()), "wrapper": WRAPPER,
               "exec_model": CFG["exec_model"], "exec_effort": CFG["exec_effort"], "exec_cmd": CFG.get("exec_cmd")}
    E.config_lock(RUNS, cfg_now, {"tasks": E.TASKS, "optB": OPT_B, "optI": OPT_I})  # 先上锁再复制复用结果
    E.SANDBOX.mkdir(exist_ok=True)
    def verified_source(rel):
        src = E.safe_runs(rel); lock = src / "run_config.json"
        if not lock.exists(): sys.exit(f"复用来源 {rel} 没有 run_config.json，拒绝复用")
        sc = json.loads(lock.read_text())
        sh = sc.get("input_sha256") or {}
        if any(sc.get(k) != cfg_now.get(k) for k in ("exec_model", "exec_effort", "exec_cmd", "wrapper")) or sh.get("tasks") != E.file_sha(E.TASKS) or sh.get("optB") != E.file_sha(OPT_B):
            sys.exit(f"复用来源 {rel} 的执行配置 / 任务内容 / 优化器内容与本次不同，拒绝复用")
        return src
    import shutil
    if V.get("reuseB"):
        src = verified_source(V["reuseB"])
        for sub in ("opt_B", "exec_B"):
            for s_ in src.glob(f"*/{sub}"):
                if not E.SAFE_ID.fullmatch(s_.parent.name): continue
                dst = E.safe_child(RUNS, s_.parent.name, sub)
                if not dst.exists(): shutil.copytree(s_, dst, symlinks=False)
    if V.get("reuseA"):
        src = verified_source(V["reuseA"])
        for s_ in src.glob("*/exec_A"):
            if not E.SAFE_ID.fullmatch(s_.parent.name): continue
            dst = E.safe_child(RUNS, s_.parent.name, "exec_A")
            if not dst.exists(): shutil.copytree(s_, dst, symlinks=False)
        E.safe_write(RUNS / "README_A_reuse.md", f"exec_A 复制自 {V['reuseA']}（已核对执行模型、档位、包装、任务、优化器一致），未重新调用。")
    ids = [x for x in a.tasks.split(",") if x]
    all_tasks = E.load_tasks()
    tasks = [t for t in all_tasks if not ids or t["id"] in ids]
    def run_all(jobs, label):
        errs = []
        with ThreadPoolExecutor(a.workers) as ex:
            futs = {ex.submit(fn, *args): (label, args[0]["id"], args[1] if len(args) > 1 else "") for fn, *args in jobs}
            for f in as_completed(futs):
                tag = futs[f]
                try: f.result(); print("ok", *tag, flush=True)
                except Exception as e: errs.append((tag, str(e))); print("ERR", *tag, str(e)[:200], flush=True)
        return errs
    errs = []
    if a.phase in ("optimize", "all"): errs += run_all([(opt_B, t) for t in tasks], "optimize")
    if a.phase in ("execute", "all"): errs += run_all([(exec_cond, t, c) for t in tasks for c in ("A", "B", "I")], "execute")
    if a.phase in ("judge", "all"): errs += run_all([(judge, t, p) for t in tasks for p in PAIRS], "judge")
    if a.phase in ("aggregate", "all"): aggregate(all_tasks)
    if errs: print("ERRORS:", len(errs)); sys.exit(1)

if __name__ == "__main__": main()
