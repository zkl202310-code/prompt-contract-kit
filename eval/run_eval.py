#!/usr/bin/env python3
"""任务契约优化器 A/B 评测 harness（默认：执行/优化器 = gpt-5.6-sol，判官 = gpt-6-astra）。
每次模型调用都通过 Codex CLI 的 exec 子命令完成，并把完整事件流（含 turn.completed.usage）保存为 events.jsonl。"""
import argparse, json, os, random, re, subprocess, sys, time, hashlib, shlex, shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

EVAL = Path(__file__).resolve().parent
SANDBOX = EVAL / ".sandbox"
TASKS = EVAL / "tasks_v1.jsonl"
WRAP = "（说明：这是一次纯文本问答。不要创建、读取或修改任何文件，不要使用工具；把全部内容直接写在回复里。）\n\n"
VARIANTS = {
    # 两步式：优化器 B 把任务改写成契约 → 同模型执行；A = 原始任务直接执行；C = 通用优化器对照
    "sol_medium": {"runs": "runs/sol_medium", "optB": "../optimizers/task-contract-optimizer.zh.md", "wrapper": WRAP,
                   "stem": "results_sol_medium", "exec_model": "gpt-5.6-sol", "exec_effort": "medium"},
    "sol_none":   {"runs": "runs/sol_none", "optB": "../optimizers/task-contract-optimizer.zh.md", "wrapper": WRAP,
                   "stem": "results_sol_none", "exec_model": "gpt-5.6-sol", "exec_effort": "none"},
    "astra":      {"runs": "runs/astra", "optB": "../optimizers/task-contract-optimizer.zh.md", "wrapper": WRAP,
                   "stem": "results_astra", "exec_model": "gpt-6-astra", "exec_effort": "medium", "judge_model": "gpt-5.6-sol"},
    # 其他供应商：exec_cmd 指向一个把 codex 指到该供应商的 shell 函数 / 包装脚本（见 eval/README.md），exec_effort=None 走 API 默认档
    "api_example": {"runs": "runs/api_example", "optB": "../optimizers/task-contract-optimizer.zh.md", "wrapper": WRAP,
                    "stem": "results_api_example", "exec_model": "<provider-model-id>", "exec_effort": None, "exec_cmd": "codex-<provider>"},
}
RUNS = EVAL / VARIANTS["sol_medium"]["runs"]
OPT = {"B": EVAL / VARIANTS["sol_medium"]["optB"], "C": EVAL / "../optimizers/generic-optimizer.zh.md"}
WRAPPER = WRAP
STEM = "results_sol_medium"
JUDGE_TPL = (EVAL / "judge_prompt.md").read_text()
JUDGE_SUFFIX = ""
JUDGE_SCHEMA = EVAL / "judge_schema.json"
CFG = {"exec_model": "gpt-5.6-sol", "exec_effort": "medium",
       "judge_model": "gpt-6-astra", "judge_effort": "high", "exec_cmd": None}
FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$")

SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,32}")   # 任务 id（fullmatch）
SAFE_SEG = re.compile(r"[A-Za-z0-9_-]{1,80}")  # 目录段（fullmatch）：防止数据造成路径遍历
RUNS_ROOT = EVAL / "runs"; RESULTS = EVAL / "results"   # 全部生成产物只落这两个目录（均在 .gitignore）
REQUIRED = ("id", "场景", "raw_prompt", "期望要点", "典型失败")

def safe_child(root: Path, *parts) -> Path:
    for x in parts:
        if not SAFE_SEG.fullmatch(str(x)): raise ValueError(f"unsafe path segment: {x!r}")
    out = root.joinpath(*parts)
    if not out.resolve().is_relative_to(root.resolve()): raise ValueError(f"path escapes {root}: {out}")
    for q in (out, *out.parents):
        if q.is_symlink(): raise ValueError(f"symlink in output path: {q}")
        if q == root: break
    return out

def assert_no_symlink(path: Path, stop: Path):
    """path 及其到 stop 为止的每一级都不能是符号链接。"""
    q = path
    while True:
        if q.is_symlink(): raise ValueError(f"symlink in path: {q}")
        if q == stop or q.parent == q: break
        q = q.parent

def safe_write(path: Path, text: str):
    """所有产物写入都经此：目标与到 EVAL 为止的各级不能是符号链接。"""
    assert_no_symlink(path, EVAL); path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)

def safe_runs(rel: str) -> Path:
    if RUNS_ROOT.is_symlink() or EVAL.is_symlink(): raise ValueError(f"{RUNS_ROOT} 或 {EVAL} 是符号链接，拒绝运行")
    runs = EVAL / rel
    if not runs.resolve().is_relative_to(RUNS_ROOT.resolve()): raise ValueError(f"runs 目录必须在 {RUNS_ROOT} 下: {rel}")
    if runs.exists(): assert_no_symlink(runs, EVAL)
    return runs

def exec_output(d: Path) -> str:
    """读取某条件的执行输出；失败或非零退出的结果不进入判官。"""
    rec = json.loads((d / "result.json").read_text())
    if rec.get("failed") or rec.get("exit", 0) != 0: raise RuntimeError(f"exec result failed, not judging: {d}")
    return rec["output"]

def task_basis(t: dict) -> str:
    """判官看到的题面：场景、原话、材料、参考要点、典型失败。任一改动都应使 verdict 失效。"""
    return json.dumps({k: t.get(k) for k in ("场景", "raw_prompt", "attachment", "期望要点", "典型失败")}, ensure_ascii=False, sort_keys=True)

def pair_sig(*texts) -> str:
    h = hashlib.sha256()
    for t in texts: h.update((t or "").encode()); h.update(b"\0")
    return h.hexdigest()

def verdict_valid(v: dict, sig: str, jcfg: dict) -> bool:
    """汇总时只统计：有签名、签名等于当前输入对、判官配置等于当前判官配置的 verdict。"""
    return bool(v.get("_sig")) and v.get("_sig") == sig and v.get("_judge_cfg") == jcfg

def judge_cfg(model: str, effort: str, template: str) -> dict:
    return {"judge_model": model, "judge_effort": effort, "template_sha256": hashlib.sha256(template.encode()).hexdigest()}

def verdict_fresh(vp: Path, sig: str, jcfg: dict) -> bool:
    """既有 verdict 只有在输入对与判官配置都相同时才复用。"""
    if not vp.exists(): return False
    v = json.loads(vp.read_text())
    return v.get("_sig") == sig and v.get("_judge_cfg") == jcfg

def load_tasks(ids=None):
    ts = [json.loads(l) for l in TASKS.read_text().splitlines() if l.strip()]
    seen = set()
    for t in ts:
        miss = [k for k in REQUIRED if k not in t]
        if miss: raise ValueError(f"task {t.get('id')!r} 缺字段 {miss}")
        if not isinstance(t["id"], str) or not SAFE_ID.fullmatch(t["id"]): raise ValueError(f"task id must be str and fullmatch {SAFE_ID.pattern}: {t['id']!r}")
        for k in ("场景", "raw_prompt", "典型失败"):
            if not isinstance(t[k], str) or not t[k].strip(): raise ValueError(f"task {t['id']}: 字段 {k} 须为非空字符串")
        if not isinstance(t["期望要点"], list) or not all(isinstance(x, str) for x in t["期望要点"]): raise ValueError(f"task {t['id']}: 期望要点 须为字符串列表")
        if "attachment" in t and t["attachment"] is not None and not isinstance(t["attachment"], str): raise ValueError(f"task {t['id']}: attachment 须为字符串")
        if t["id"] in seen: raise ValueError(f"duplicate task id: {t['id']!r}")
        seen.add(t["id"])
    return [t for t in ts if not ids or t["id"] in ids]

def file_sha(path) -> str: return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def config_lock(runs: Path, cfg: dict, content_files: dict):
    """同一 runs 目录只对应一套配置（含各输入文件的内容哈希）；不同就拒绝；已有结果但无锁也拒绝。"""
    cfg = {**cfg, "input_sha256": {k: file_sha(v) for k, v in content_files.items()}}
    lock = runs / "run_config.json"
    if lock.exists():
        if json.loads(lock.read_text()) != cfg: sys.exit(f"runs 目录 {runs} 已有不同配置/输入的结果（见 run_config.json）；请换一个 runs 目录")
    elif any(runs.glob("*/")): sys.exit(f"runs 目录 {runs} 已有结果但没有 run_config.json；请换一个 runs 目录")
    safe_write(lock, json.dumps(cfg, ensure_ascii=False, indent=1))

def codex_run(prompt: str, model: str, effort: str, outdir: Path, schema: Path = None, timeout=600, wrapper_cmd: str = None):
    outdir.mkdir(parents=True, exist_ok=True)
    files = {n: outdir / n for n in ("prompt.md", "last.md", "events.jsonl", "stderr.log", "result.json")}
    for f in files.values():
        if f.is_symlink(): raise ValueError(f"refusing to write through symlink: {f}")
    files["prompt.md"].write_text(prompt)
    last = files["last.md"]; events = files["events.jsonl"]
    cmd = [wrapper_cmd or "codex", "exec", "--json", "--skip-git-repo-check", "--model", model,
           "-s", "read-only", "-C", str(SANDBOX), "-o", str(last)]
    if effort: cmd[6:6] = ["-c", f"model_reasoning_effort={effort}"]
    if schema: cmd += ["--output-schema", str(schema)]
    cmd.append(prompt)
    if wrapper_cmd:
        exe = shutil.which(wrapper_cmd)
        if exe: cmd[0] = exe  # 优先用 PATH 上的可执行包装脚本：不加载 shell rc
        else:  # 回退：shell 函数须经交互 zsh 加载，会执行你的 rc；rc 打印的任何内容都可能进入下面两个日志
            print(f"[warn] {wrapper_cmd} 不在 PATH 上，改用 zsh -ic 加载 shell 函数（会执行你的 rc；日志可能含 rc 输出）", file=sys.stderr)
            cmd = ["zsh", "-ic", shlex.join(cmd)]
        timeout = max(timeout, 900)
    t0 = time.time()
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    usage, failed, ev_lines, other = None, None, [], []
    for line in r.stdout.splitlines():  # 只有能解析成 JSON 的事件行进事件流；其余（含 rc 的 stdout）进 stderr.log
        if line.startswith("{"):
            try: ev = json.loads(line)
            except Exception: other.append(line); continue
            ev_lines.append(line)
            if ev.get("type") == "turn.completed": usage = ev.get("usage")
            if ev.get("type") in ("turn.failed", "error"): failed = ev
        elif line.strip(): other.append(line)
    events.write_text("\n".join(ev_lines) + ("\n" if ev_lines else ""))
    files["stderr.log"].write_text((r.stderr or "") + ("\n--- non-JSON stdout ---\n" + "\n".join(other) if other else ""))
    text = last.read_text() if last.exists() else ""
    if r.returncode != 0 or not text.strip():
        failed = failed or {"type": "harness", "exit": r.returncode, "reason": "nonzero exit or empty output"}
    rec = {"model": model, "effort": effort, "seconds": round(time.time() - t0, 1),
           "usage": usage, "failed": failed, "exit": r.returncode, "output": text}
    files["result.json"].write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    if failed:
        raise RuntimeError(f"run failed (exit {r.returncode}): {outdir} {failed}")
    return rec

def raw_task_prompt(t):
    return t["raw_prompt"] + (f"\n\n材料：\n{t['attachment']}" if t.get("attachment") else "")

def strip_fence(s):
    s = s.strip()
    if s.startswith("```"): s = re.sub(r"^```[^\n]*\n", "", s); s = re.sub(r"\n```\s*$", "", s)
    return s.strip()

def restore_optimized_prompt(out):
    """Recover the derived prompt from a successful result, without a model call."""
    result = out / "result.json"
    if not result.exists(): return False
    rec = json.loads(result.read_text())
    if rec.get("failed") or rec.get("exit", 0) != 0: return False
    text = strip_fence(rec.get("output") or "")
    if not text: return False
    prompt = out / "optimized_prompt.md"
    try: current = prompt.read_text()
    except (FileNotFoundError, UnicodeDecodeError): current = None  # 中断写入可能截断 UTF-8 字符
    if current != text:
        safe_write(prompt, text)
    return True

def phase_optimize(t, cond):
    out = safe_child(RUNS, t["id"], f"opt_{cond}")
    if restore_optimized_prompt(out): return
    prompt = WRAPPER + OPT[cond].read_text() + "\n\n---\n\n用户的原始任务如下（含其附带材料，原样）：\n\n" + raw_task_prompt(t)
    rec = codex_run(prompt, CFG["exec_model"], CFG["exec_effort"], out, wrapper_cmd=CFG["exec_cmd"])
    safe_write(out / "optimized_prompt.md", strip_fence(rec["output"]))

def phase_execute(t, cond):
    out = safe_child(RUNS, t["id"], f"exec_{cond}")
    if (out / "result.json").exists() and not json.loads((out/"result.json").read_text()).get("failed"): return
    if cond == "A": prompt = WRAPPER + raw_task_prompt(t)
    else:
        opt = safe_child(RUNS, t["id"], f"opt_{cond}")
        if not restore_optimized_prompt(opt): raise RuntimeError(f"optimization missing or failed, not executing: {opt}")
        prompt = WRAPPER + (opt / "optimized_prompt.md").read_text()
    codex_run(prompt, CFG["exec_model"], CFG["exec_effort"], out, wrapper_cmd=CFG["exec_cmd"])

def phase_judge(t, pair):  # pair like "AB" or "BC"
    out = safe_child(RUNS, t["id"], f"judge_{pair}{JUDGE_SUFFIX}")
    a, b = pair[0], pair[1]
    oa = exec_output(safe_child(RUNS, t["id"], f"exec_{a}")); ob = exec_output(safe_child(RUNS, t["id"], f"exec_{b}"))
    sig = pair_sig(oa, ob, task_basis(t)); jcfg = judge_cfg(CFG["judge_model"], CFG["judge_effort"], JUDGE_TPL)
    if verdict_fresh(out / "verdict.json", sig, jcfg): return  # 输入对、题面与判官配置都没变才复用
    seed = int(hashlib.md5(f"{t['id']}{pair}".encode()).hexdigest(), 16)
    flip = random.Random(seed).random() < 0.5
    X, Y = (ob, oa) if flip else (oa, ob)
    mapping = {"X": b if flip else a, "Y": a if flip else b}
    prompt = JUDGE_TPL.format(scene=t["场景"], raw=t["raw_prompt"], attachment=t.get("attachment") or "无",
                              points="；".join(t["期望要点"]), fail=t["典型失败"], X=X, Y=Y)
    rec = codex_run(prompt, CFG["judge_model"], CFG["judge_effort"], out, schema=JUDGE_SCHEMA)
    txt = strip_fence(rec["output"])
    try: v = json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S); v = json.loads(m.group()) if m else {"parse_error": txt}
    v["_mapping"] = mapping; v["_lenX"] = len(X); v["_lenY"] = len(Y); v["_sig"] = sig; v["_judge_cfg"] = jcfg
    safe_write(out / "verdict.json", json.dumps(v, ensure_ascii=False, indent=1))

def decode(v, key, treat):
    """把 X/Y 判定翻译成 treat 条件的 win/tie/loss"""
    r = v.get(key)
    if r == "tie": return "tie"
    return "win" if v["_mapping"].get(r) == treat else "loss"

def aggregate(tasks):
    crits = ["answers_question", "no_fabrication", "directly_usable", "fidelity", "overall"]
    jcfg = judge_cfg(CFG["judge_model"], CFG["judge_effort"], JUDGE_TPL)
    res = {}
    for pair, treat in (("AB", "B"), ("BC", "B")):
        if not any((RUNS / t["id"] / f"judge_{pair}{JUDGE_SUFFIX}" / "verdict.json").exists() for t in tasks): continue
        agg = {c: {"win": 0, "tie": 0, "loss": 0} for c in crits}; rows = []; lens = []
        for t in tasks:
            vp = RUNS / t["id"] / f"judge_{pair}{JUDGE_SUFFIX}" / "verdict.json"
            if not vp.exists(): continue
            v = json.loads(vp.read_text())
            if "parse_error" in v: continue
            try: cur = pair_sig(exec_output(RUNS / t["id"] / f"exec_{pair[0]}"), exec_output(RUNS / t["id"] / f"exec_{pair[1]}"), task_basis(t))
            except Exception: print(f"[warn] {t['id']} {pair}: 执行结果失败或缺失，verdict 不计", file=sys.stderr); continue
            if not verdict_valid(v, cur, jcfg): print(f"[warn] {t['id']} {pair}: verdict 过期（输出、题面或判官配置已变），已忽略", file=sys.stderr); continue
            for c in crits: agg[c][decode(v, c, treat)] += 1
            lt = v["_lenX"] if v["_mapping"]["X"] == treat else v["_lenY"]
            lo = v["_lenY"] if v["_mapping"]["X"] == treat else v["_lenX"]
            lens.append(lt / max(lo, 1))
            rows.append({"task": t["id"], "overall": decode(v, "overall", treat), "reason": v.get("reason", ""), "len_ratio": round(lt / max(lo, 1), 2)})
        n = sum(agg["overall"].values())
        res[pair] = {"n": n, "treat": treat, "by_criterion": agg,
                     "overall_win_rate": round(agg["overall"]["win"] / n, 3) if n else None,
                     "_overall_win_rate_raw": (agg["overall"]["win"] / n) if n else None,
                     "mean_len_ratio": round(sum(lens) / len(lens), 2) if lens else None,
                     "_mean_len_ratio_raw": (sum(lens) / len(lens)) if lens else None, "rows": rows}
    # usage totals
    tot = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0, "calls": 0}
    for rj in RUNS.rglob("result.json"):
        u = json.loads(rj.read_text()).get("usage") or {}
        for k in list(tot)[:-1]: tot[k] += u.get(k, 0)
        tot["calls"] += 1
    res["usage_total"] = tot
    ab = res.get("AB")
    # 预注册门（与 eval/README.md「门槛版本」一致）：总体 ≥ 0.55、不编造负 ≤ 2、长度比 ≤ 1.5（用未四舍五入值）、题数完整
    if ab:
        nf = ab["by_criterion"]["no_fabrication"]
        res["gate"] = {"win_rate_ge_0.55": (ab["_overall_win_rate_raw"] or 0) >= 0.55, "nofab_loss_le_2": nf["loss"] <= 2,
                       "len_ratio_le_1.5": (ab["_mean_len_ratio_raw"] if ab["_mean_len_ratio_raw"] is not None else 9) <= 1.5,
                       "complete": ab["n"] == len(tasks)}
    else:
        res["gate"] = {"win_rate_ge_0.55": False, "nofab_loss_le_2": False, "len_ratio_le_1.5": False, "complete": False}
    res["gate"]["pass"] = all(res["gate"].values())
    if not res["gate"]["complete"]: print(f"[warn] AB 判定 {ab['n'] if ab else 0}/{len(tasks)} 题，结果不完整，不算通过", file=sys.stderr)
    RESULTS.mkdir(exist_ok=True)
    safe_write(RESULTS / f"{STEM}{JUDGE_SUFFIX}.json", json.dumps(res, ensure_ascii=False, indent=1))
    lines = [f"# 结果汇总（自动生成，{STEM}{JUDGE_SUFFIX}）", "", f"预注册门：{json.dumps(res['gate'], ensure_ascii=False)}", ""]
    for pair in ("AB", "BC"):
        if pair not in res: continue
        r = res[pair]
        lines += [f"## {pair}（处理组 = B 专属优化；对照 = {pair[0] if pair=='AB' else 'C'}）", f"- n = {r['n']}，overall 胜率 = {r['overall_win_rate']}，B 平均长度比 = {r['mean_len_ratio']}", "", "| 判项 | 胜 | 平 | 负 |", "|---|---|---|---|"]
        for c in crits: a = r["by_criterion"][c]; lines.append(f"| {c} | {a['win']} | {a['tie']} | {a['loss']} |")
        lines += ["", "| 任务 | overall | 长度比 | 判官理由 |", "|---|---|---|---|"]
        for row in r["rows"]: lines.append(f"| {row['task']} | {row['overall']} | {row['len_ratio']} | {row['reason']} |")
        lines.append("")
    lines.append(f"用量合计：{json.dumps(tot, ensure_ascii=False)}")
    safe_write(RESULTS / f"{STEM}{JUDGE_SUFFIX}.md", "\n".join(lines))
    print(json.dumps({k: ({kk: vv for kk, vv in v.items() if kk != 'rows'} if isinstance(v, dict) else v) for k, v in res.items() if k != 'usage_total'}, ensure_ascii=False, indent=1))
    print("usage_total", tot)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="", help="只执行指定题目；汇总始终覆盖完整任务集")
    ap.add_argument("--phase", default="all", choices=["optimize", "execute", "judge", "aggregate", "all"])
    ap.add_argument("--workers", type=int, default=2, help="作者环境下 OpenAI 侧 >3 并发出现过 403，默认 2")
    ap.add_argument("--variant", default="sol_medium", choices=list(VARIANTS))
    ap.add_argument("--judge", default="v1", choices=["v1", "v2"], help="v2 = 按任务类型判长度的量规，结果写入 judge_*_v2")
    ap.add_argument("--conds", default="A,B,C", help="执行条件，如 A,B")
    ap.add_argument("--pairs", default="AB,BC", help="判官对照对，如 AB")
    a = ap.parse_args()
    global RUNS, OPT, WRAPPER, STEM, JUDGE_TPL, JUDGE_SUFFIX
    if a.judge == "v2":
        JUDGE_TPL = (EVAL / "judge_prompt_v2.md").read_text(); JUDGE_SUFFIX = "_v2"
    V = VARIANTS[a.variant]
    RUNS = safe_runs(V["runs"]); OPT = {"B": EVAL / V["optB"], "C": EVAL / "../optimizers/generic-optimizer.zh.md"}
    WRAPPER = V["wrapper"]; STEM = V["stem"]
    if V.get("exec_model"): CFG["exec_model"] = V["exec_model"]
    if "exec_effort" in V: CFG["exec_effort"] = V["exec_effort"]
    if V.get("judge_model"): CFG["judge_model"] = V["judge_model"]
    if V.get("exec_cmd"): CFG["exec_cmd"] = V["exec_cmd"]
    # 锁只管执行侧（任务、优化器、对照、包装、执行模型/档位）；判官配置记在每份 verdict 里，换判官或量规不需要换目录
    cfg_now = {"variant": a.variant, "optB": str(OPT["B"].resolve()), "tasks": str(TASKS.resolve()), "wrapper": WRAPPER,
               **{k: CFG[k] for k in ("exec_model", "exec_effort", "exec_cmd")}}
    config_lock(RUNS, cfg_now, {"tasks": TASKS, "optB": OPT["B"], "optC": OPT["C"]})
    conds = [c for c in a.conds.split(",") if c]; pairs = [q for q in a.pairs.split(",") if q]
    if any(c not in ("A", "B", "C") for c in conds) or any(not re.fullmatch(r"[ABC]{2}", q) for q in pairs): sys.exit("--conds 只接受 A,B,C；--pairs 只接受两字母组合如 AB,BC")
    if V.get("reuseA"):  # 复用 A 输出：来源目录必须有锁，且执行模型 / 档位 / 包装 / 任务哈希与本次一致
        import shutil
        src_lock = safe_runs(V["reuseA"]) / "run_config.json"
        if not src_lock.exists(): sys.exit(f"reuseA 来源 {V['reuseA']} 没有 run_config.json，无法核对，拒绝复用")
        sc = json.loads(src_lock.read_text())
        if any(sc.get(k) != cfg_now.get(k) for k in ("exec_model", "exec_effort", "exec_cmd", "wrapper")) or (sc.get("input_sha256") or {}).get("tasks") != file_sha(TASKS):
            sys.exit(f"reuseA 来源 {V['reuseA']} 的执行配置或任务文件内容与本次不同，拒绝复用")
        for src in safe_runs(V["reuseA"]).glob("*/exec_A"):
            if not SAFE_ID.fullmatch(src.parent.name): continue
            dst = safe_child(RUNS, src.parent.name, "exec_A")
            if not dst.exists(): shutil.copytree(src, dst, symlinks=False)
        safe_write(RUNS / "README_A_reuse.md", f"exec_A 复制自 {V['reuseA']}（已核对执行模型、档位、包装、任务文件一致），未重新调用。")
    ids = [x for x in a.tasks.split(",") if x]
    all_tasks = load_tasks()
    tasks = [t for t in all_tasks if not ids or t["id"] in ids]
    SANDBOX.mkdir(exist_ok=True)
    def run_all(jobs, label):
        errs = []
        with ThreadPoolExecutor(a.workers) as ex:
            futs = {ex.submit(fn, *args): (fn.__name__, args[0]["id"], args[1]) for fn, *args in [(j[0], *j[1:]) for j in jobs]}
            for f in as_completed(futs):
                tag = futs[f]
                try: f.result(); print("ok", label, tag[1], tag[2], flush=True)
                except Exception as e: errs.append((tag, str(e))); print("ERR", label, tag[1], tag[2], str(e)[:200], flush=True)
        return errs
    errs = []
    if a.phase in ("optimize", "all"): errs += run_all([(phase_optimize, t, c) for t in tasks for c in conds if c != "A"], "optimize")
    if a.phase in ("execute", "all"): errs += run_all([(phase_execute, t, c) for t in tasks for c in conds], "execute")
    if a.phase in ("judge", "all"): errs += run_all([(phase_judge, t, p) for t in tasks for p in pairs], "judge")
    if a.phase in ("aggregate", "all"): aggregate(all_tasks)
    if errs: print("ERRORS:", len(errs)); sys.exit(1)

if __name__ == "__main__": main()
