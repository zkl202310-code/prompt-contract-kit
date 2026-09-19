# prompt-contract-kit

> 把随手写的任务改写成「任务契约」再交给模型执行——附一套 20 题盲配对评测 harness，以及作者在 GPT-5.6 / GPT-6 / DeepSeek / Kimi 上跑出的结果。**先说结论：在开着推理的前沿模型上，这类优化器的边际价值有限；在作者的任务集上最一致的效果是「较少加入材料里没有的内容」，代价是回答更保守。** 这是一个开源的可选护栏与评测工具，不是「让 AI 更聪明」的秘方。
>
> *A task-contract prompt optimizer for frontier models, with a 20-task blind pairwise eval harness and the author's measured results across GPT-5.6, GPT-6, DeepSeek and Kimi. Headline: with reasoning on, gains are marginal; the most consistent effect on this task set is less fabrication, at the cost of more conservative answers. Chinese-first. Unofficial; not affiliated with OpenAI or Anthropic.*

## 里面有什么

| 目录 | 内容 | 给谁 |
|---|---|---|
| `skills/prompt-contract/` | 一个 agent skill（Claude Code / Codex 通用格式）：写、审、瘦身提示词与 agent 任务说明时的协议，附 Fable 5.1 / GPT-6 Astra / GPT-5.6 三份模型笔记（作者整理与改编，官方原文见各篇链接） | 用 Claude Code / Codex 的人 |
| `optimizers/` | 两份纯文本优化器（两步式、一步式）+ 一份评测对照组文本 + 每个模型、每个档位的实测胜负表与装法 | 用 ChatGPT / Kimi / DeepSeek 网页版的人 |
| `eval/` | A/B 盲配对评测 harness：两步式、一步式、换判官重判、网页端贴回判官、人工盲评表；预注册模板 | 想自己测一遍再决定用不用的人 |

## 三个实测观察（均为**作者报告**：20 题自编任务、单次运行、模型判官；公开包不含原始输出，无法独立复算。细节与口径见 `optimizers/README.md`、`skills/prompt-contract/references/model-behavior-matrix.md`）

1. **GPT-5.6 不开推理时，优化后更差。** effort=none（API 侧，网页端 Instant 的等价性未验证）下 7 胜 1 平 12 负——契约里列出的输出项被照单全做，回答更长、更偏离原任务范围。low / medium 档下 13-1-6 / 12-1-7。
2. **在这组任务上 GPT-6 用不上两步式。** GPT-6 Astra 上 3-0-17：原始回答已经简洁有结构，压短规则被执行过头。
3. **跨模型的效果性质相近。** DeepSeek V4.1 Flash、Kimi K3 上原样使用：「较少擅自补充」17-3-0 / 13-4-3，回答完整度明显下降；长度在 GPT-5.6 上略长（比值 1.1–1.25）、在 DeepSeek / Kimi 上更短（0.59 / 0.71）。「较少编造」是相对比较，不是防编造保证。

## 快速开始

**Claude Code / Codex**：把 `skills/prompt-contract/` 复制到 `~/.claude/skills/` 或 `~/.codex/skills/`（通用安装路径）。之后请它「把这个任务写成给子代理的说明」「审一下这个 skill 的 description」时触发。

**ChatGPT Plus**：新建项目 → 项目指令贴入 `optimizers/task-contract-optimizer.zh.md` 全文 → 在项目里发任务得契约 → 复制到项目外新对话、切到 Thinking 后发送。网页端效果未经与 API 实验等价的验证，请自己对照几题。

**自己评测（4 题示例运行；原实验为 20 题）**：
```bash
cd eval
cp tasks_example.jsonl tasks_v1.jsonl        # 换成你自己的任务文件亦可，格式见 eval/README.md
python3 run_eval.py --variant sol_medium --conds A,B --pairs AB --workers 2
```
需要已登录的 Codex CLI。**运行边界**：脚本在你的机器上写 `eval/runs/` 与 `eval/results/`；任务与材料会发送到所配置的模型服务；`-s read-only` 只约束 Codex 子进程，不约束外层脚本；接入其他供应商时会执行你的 shell 函数或包装脚本，日志可能含 rc 输出，分享前先检查。详见 `eval/README.md` 安全说明。

## 来源、许可与免责
- 模型笔记与协议是作者基于 OpenAI / Anthropic 官方文档的整理与改编，含概括、也可能含个别接近原文的表述；不收录官方文档的连续译文段落，每篇末尾给出官方链接。**非官方文档，与 OpenAI、Anthropic 无关，无任何厂商背书。**
- MIT 许可覆盖本项目有权授权的原创内容（代码、评测设计、作者笔记）；引用或改编的第三方表达按其原始条款处理。
- 评测任务示例为虚构；原始 20 题任务与全部模型输出不随库发布（含个人材料）。

## 状态
2026-09-18 首版。欢迎按 `eval/README.md` 的预注册表提交你在其他模型上的 A/B 结果。
