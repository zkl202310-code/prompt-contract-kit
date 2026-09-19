# eval/ · A/B 盲配对评测 harness

> 目标：为任一模型跑一次「优化器 B 对原始 A」的 20 题盲评，只改一处配置、跑一条命令、填一张预注册表。所有模型调用经 **Codex CLI**（`codex exec --json`）完成，事件流含用量；需要已登录的 Codex CLI（≥0.153）。

## 脚本
| 脚本 | 用途 | 典型命令 |
|---|---|---|
| `run_eval.py` | 两步式 A/B/C：优化 → 执行 → 判官 → 汇总 | `python3 run_eval.py --variant sol_medium --conds A,B --pairs AB --workers 2` |
| `run_inline.py` | 一步式 I（优化器与任务同对话）对 A / 对 B | `python3 run_inline.py --variant sol_inline` |
| `judge_cross.py` | 换判官重判既有输出对（拆判官口味与执行模型） | `python3 judge_cross.py --runs runs/sol_medium --pairs AB:B --judge-model gpt-5.6-sol --suffix soljudge` |
| `judge_pasted.py` | 网页端人工贴回的 A/B 输出做盲判（`--self-test` 用既有 runs 自检） | `python3 judge_pasted.py --record live_record.md --tasks tasks_holdout.md` |
| `make_calibration_sheet_v2.py` | 生成人工盲评表到 `results/`（答案键单独存，评审者不看）；按脚本方式运行，参数见脚本头 | `python3 make_calibration_sheet_v2.py sol_medium 10` |

任务文件：`tasks_example.jsonl`（4 条虚构示例，字段 id / 场景 / raw_prompt / attachment / 期望要点 / 典型失败 / 优化杠杆）。自己写 20 条时，任务原话要像真人随手打的；材料用虚构或脱敏内容。`run_eval.py` 默认读 `tasks_v1.jsonl`，把你的文件改成这个名字或改 `TASKS` 常量。

## 接入一个模型 = 在 `run_eval.py` 的 `VARIANTS` 加一条
```python
"my_variant": {"runs": "runs/my_variant",
    "optB": "../optimizers/task-contract-optimizer.zh.md",   # 或你的专版
    "wrapper": WRAP,                    # CLI 沙箱用的中性包装，保持一致以便可比
    "stem": "results_my_variant",
    "exec_model": "<模型 id>",           # gpt-5.6-sol / gpt-6-astra / gpt-5.6-luna / 其他供应商 id
    "exec_effort": "medium",            # None = 不传 -c，走 API 默认档；OpenAI 侧可填 none/low/medium/high/xhigh/max（无 minimal）
    "exec_cmd": None,                   # 其他供应商：填一个把 codex 指向该供应商的 shell 函数名（见下）
    "judge_model": "gpt-6-astra"}       # 判官须与执行模型不同
```
- `reuseA`：只在**同模型、同效果档、同包装**时才可复用 A 输出；换档必须重生成 A。
- 判官默认 `gpt-6-astra high` + `judge_prompt.md`（量规 v1）+ `judge_schema.json`；X/Y 按 md5(任务+对) 随机翻转，`_mapping` 记录。
- **其他供应商**（DeepSeek / Kimi / …）：推荐写一个**可执行包装脚本**放在 PATH 上（例如 `codex-deepseek`：用单独的 `CODEX_HOME` 与该供应商的 base_url / 密钥启动 `codex`，不打印任何凭据），`exec_cmd` 填脚本名，脚本直接调用、不加载 shell rc。若只定义了 shell 函数，脚本会回退到 `zsh -ic` 并打印警告——这会执行你的 rc。事件流只保留能解析成 JSON 的行，其余 stdout 与全部 stderr 写入 `stderr.log`；**两份日志都可能含 rc 打印的内容（包括开了调试跟踪时展开的密钥）**，分享 `runs/` 前先检查。非 OpenAI 模型会报「Model metadata not found」可忽略。
- 并发：作者环境下 OpenAI 侧 >3 并发出现过 403，默认 `--workers 2`；后台运行时 `stdin` 已接 `/dev/null`。
- 运行配置锁：每个 `runs/` 目录写 `run_config.json`（变体、执行模型、档位、包装文本，以及任务文件 / 优化器 / 对照文本的内容哈希）；任一不同就拒绝复用；已有结果但没有锁也拒绝；`reuseA` / `reuseB` 的来源目录必须有锁且执行配置一致。非零退出或空输出记为 `failed`，重跑时会重做；题数不完整的汇总标 `complete: false`，不算通过。
- **门槛版本**：仓库内三个脚本现在用同一套条件（总体 ≥ 0.55、不编造负 ≤ 2、长度比 ≤ 1.5，胜率与长度比都用未四舍五入的原始值、题数完整；`judge_pasted.py` 的题数完整靠 `--expect` 指定每组预期记录数）。每份 verdict 记签名（两份输出 + 题面：场景 / 原话 / 材料 / 参考要点）与判官配置（模型、档位、模板哈希）：任一变了就重判，汇总只统计签名与当前判官配置都匹配的 verdict；执行失败或缺失的输出不进判官也不计入；运行锁只管执行侧（含各输入文件哈希），换判官或量规不必换目录；复用别的目录的 A/B 时核对来源锁里的任务与优化器内容哈希。作者历史实验各表中标注的条件以各表说明为准，与当前代码无关；当前代码不能证明历史门槛确曾预注册。
- 产物位置：运行目录必须在 `eval/runs/` 下，汇总与人工表统一写到 `eval/results/`；两者都在 `.gitignore`。自定义参数不能把产物写到这两个目录之外。
- 一次 20 题 A/B 全量 = 80 次调用（20 优化 + 40 执行 + 20 判官）；Sol 约 15 分钟，Kimi K3 默认档约 70 分钟。

## 预注册表（数据前写死；结果只追加不改）
```
### <名称>（<日期> 预注册）
- 对象：<哪个文件、哪个版本、改了什么>
- 设定：执行 <模型/档>；A <重生成 / 复用哪里>；判官 <模型/档>、量规 v1；目录 runs/<…>
- 门：对 A 总体 ≥ 0.55 且不编造负 ≤ 2（可加长度比 ≤ 1.5）
- 未过怎么办：<回退 / 停用 / 补测哪一档>
- 读数（不作门）：<I 对 B、长度、分项>
```

## 汇总怎么读
- `results_<stem>.json|md`：五项 W-T-L、`overall_win_rate`、`mean_len_ratio`（比值均值，另看极值）、逐题判官理由。
- 平局单列；字符数用 Python `len()`。
- 单次运行、20 题、LLM 判官——结论只写「在本组任务上」；人工校准 κ ≥ 0.4 才引用总体胜率。已知波动：同一文件两次运行编造项 8-11-1 与 8-9-3。

## 安全说明
- 脚本在你的机器上创建 `runs/<变体>/<任务>/…` 并写入提示词、模型输出、事件流与 `stderr.log`；任务 id、条件名、组名、后缀限定为 `[A-Za-z0-9_-]`（完全匹配），写入前校验目标仍在 `runs/` 内且路径上无符号链接，拒绝写穿既有符号链接。
- 任务原话与材料会**发送到所配置的模型服务**；事件流含完整工具输出。`-s read-only` 只约束 Codex 子进程，不约束外层 Python 与你的 rc；提示词里的「不要使用工具」不是权限隔离。
- `exec_cmd` 模式会执行你的包装脚本或 shell 函数，见上。
- `runs/`、`results/`（含汇总、人工盲评表与答案键）、`tasks_v1.jsonl`、`live_record.md` 都在 `.gitignore`；**手工打包上传时 `.gitignore` 不起作用**，请自行排除。模型输出里可能出现环境路径，发布任何输出前先看一遍。
