> **2026-11-15 说明**：本稿核对于 2026-09。GPT-6 Astra 仍是现行家族里最吃重工作的选项，但 2026-11 的官方《Using GPT-6》页已同时覆盖 6.1 Sol / 6.1 Terra / Luna；家族对照与迁移要点见同目录 `gpt-6.1.md`。本稿保留作当时的消化笔记。

# GPT-6 Astra · 提示词消化笔记与结论

> 基于官方《Using GPT-6 Astra》整理的作者笔记，含概括与改编，不收录官方文档的连续译文段落；非官方文档、无厂商背书，API 参数与价格以官方现行页为准。核对日期 2026-09-05 / 09-10。

## 一、消化笔记

### 1. 从「做减法」到「点名冲突」

Sol 时代的第一动作是删；Astra 指令跟随更强、但对 skill 指令更敏感、易被带偏，所以第一动作变成**给指令分优先级、要求模型指认冲突来源**。对三层规则（全局入口 → 提示词协议 → 模型笔记）的意义：在协议里明写「用户指令 > 全局规则 > skill 文件」，并要求模型在停顿时说出是哪个文件让它停。

### 2. 委派不足是官方点名的短板

behavior 引子直说 Astra 可能派得比你需要的少。主对话跑 Astra 编排时，提示词里要明写「有收益就并行派子代理」，Codex 侧还要给触发短语（如 spawn two agents、delegate this work in parallel），因为本地 Codex 只在 AGENTS.md 或 skill 指令要求时才委派。

### 3. 测试方向看似反转，其实是补了停止条件

Sol 说「结束前必须真的检查」，Astra 官方对**低影响、可逆、且测试只会镜像实现本身**的改动放宽了测试要求，并强调过了就停——不是所有改动都不必测。两句合起来才完整：验证是契约的一部分，但验证本身也要有停止规则，否则模型会无限重跑测试。

### 4. 成本：单价同 Fable 5.1，缓存贵四倍，靠少输出赢回来

$10 / $50 与 Fable 5.1 完全相同；缓存输入 $1 对 Fable 5.1 的 $0.25。OpenAI 的抵消论据是输出 token 更少。结论一样：比「每完成任务成本」，不比单价。

### 5. Sol 指南没过时，它降级为执行层指南

Astra 页没提的 Sol 第 5/6/7 节（工具路由、PTC、检索预算）恰恰是执行型子代理最需要的。给 Sol 子代理写任务提示时，继续用 GPT-5.6 笔记（`gpt-5.6.md`） 的模板和检索预算写法。

### 6. 写作风格条款可直接用于中文成稿

一段一个主意、列表只在并列/有序/对比时用、主动语态、删套话——和「去 AI 味」写作检查表同向。

### 7. 我的迁移检查单

- [ ] 只换模型名，effort 保持原档（`none`/`minimal` 升 `low`），先跑基线
- [ ] 去掉 `temperature`/`top_p`/`top_logprobs`
- [ ] 若有「停下等审批」症状，补 initiative 段；若委派不足，补 delegation 段
- [ ] 指令冲突时要求模型点名文件
- [ ] 一次只改一组，改后重跑同一批任务

---

## 二、可带走的结论

1. **Astra 的三种偏移**：更爱问、更爱格式化长答、派得少；处方分别是偏向行动、限制格式、明写并行委派。
2. **指令冲突要让模型点名**：指令跟得好也更易被 skill 指令带偏，优先级要显式。
3. **验证要有停止条件**：官方只对低影响、可逆、测试只会镜像实现的改动放宽测试；其余仍要验证，过了就停。
4. **成本比每完成任务**：单价同 Fable 5.1，缓存贵，靠少输出赢。
5. **Sol 指南降级为执行层指南**，工具路由/检索预算等仍用它。
6. **迁移是 API 层动作**：effort 不能 none、Responses API、去采样参数、`configuration_update`。

## 来源与版本说明

- 主文：[Using GPT-6 Astra](https://developers.openai.com/api/docs/guides/latest-model)（Markdown 源 `latest-model/gpt-6-astra.md`）；旧的 `prompt-guidance-*` 与 `upgrading-to-*` 独立页模式在这一代废弃（`upgrading-to-gpt-6-astra` 返回 404）。[GPT-5.6 Sol 指南](https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6) 仍可访问。
- 模型页：[gpt-6-astra](https://developers.openai.com/api/docs/models/gpt-6-astra)。
- 编排相关：[Responses multi-agent](https://developers.openai.com/api/docs/guides/responses-multi-agent)（`/root` 路径、`max_concurrent_subagents` 默认 3 且含后代、子代理共享请求模型）；[Codex subagents](https://developers.openai.com/codex/subagents)（TOML 定义，可按代理设 `model` 与 `model_reasoning_effort`，未设则继承父代理）。两者是不同产品面，规则不同。
- 初次核对：2026-09-05，由 opus 子代理经 WebFetch 摘要层提取，当时六小节示例提示块未完整取回。2026-09-10 已通过官方文档工具取回完整 Markdown；仍不把 `high` 称为 Astra 统一官方默认。引用与实现以现行官方页为准。
- 本文只含消化笔记与结论，官方原文请看上面的链接。
