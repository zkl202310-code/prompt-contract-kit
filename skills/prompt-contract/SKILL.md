---
name: prompt-contract
version: 0.2.0
summary: "把提示词、skill 与子代理任务说明写成任务契约（目标、验收、约束、证据、停止条件），并按需路由到现行模型笔记。"
description: "Write, review, or slim prompts, skills, and agent task briefs as task contracts (goal, success criteria, constraints, evidence, stop rules); route to per-model notes for Claude Fable 5.2, Claude Opus 5.5, the GPT-6.1 family, plus dated notes for Fable 5.1, GPT-6 Astra, and GPT-5.6. Use when asked to draft or audit a prompt, SKILL.md, CLAUDE.md/AGENTS.md entry, or subagent brief. Not for executing the task itself."
tags:
  - prompts
  - skills
  - agents
  - task-contract
keywords:
  - task contract
  - prompt engineering
  - SKILL.md
docs_url: https://github.com/zkl202310-code/prompt-contract-kit
---

# prompt-contract

把提示词当**验收合同**写，不当 SOP 写：先写成果与可观察的完成条件，再补会改变判断的背景、证据、约束和输出格式；角色、步骤、模板只在有实际作用时加入。全文中文亦可直接执行，不把翻译设为必经步骤。

## 何时读哪份参考（只读当前任务需要的）
| 任务 | 读 |
|---|---|
| 写新提示词 / 子代理任务说明 | `references/protocol.md` §2、§4 |
| 审查或瘦身已有 skill / 全局指令 | `references/protocol.md` §3 + `references/skill-slimming.md` |
| 目标模型是 Fable 5.2 / Opus 5.5 / GPT-6.1 家族，或仍在用 Fable 5.1 / GPT-6 Astra / GPT-5.6，且出现具体症状 | `references/model-notes/<model>.md` 的对应条目 |
| 想给网页版模型套「任务契约」优化器，或评估它值不值 | `references/model-behavior-matrix.md`；优化器文本与装法在仓库根目录 `optimizers/`（只复制本 skill 目录时不随附） |

## 硬规则（少数，真的不变）
- 保留用户的事实、数值、路径、模型、范围、权限和交付要求；每条规则只写一次；绝对命令只用于安全红线、固定 schema、不可逆动作。
- 用户明确指令优先于全局规则和 skill 指引，但不覆盖系统、宿主或工具权限；若某条本地指令导致暂停或偏离，指出具体文件与条文。
- 本 skill 不授权委派、换模型、付费或扩大范围；保留本次模型与 effort。
- 用户要求改写时交付可用稿；只要求审查时给问题与依据，不自行改文件。

## 输出
写作任务：交可直接使用的提示词或任务说明，末尾一行列出你**删掉或没加**的东西及原因。审查任务：按「问题 / 依据（文件与条文）/ 建议」列出，不重写全文。
