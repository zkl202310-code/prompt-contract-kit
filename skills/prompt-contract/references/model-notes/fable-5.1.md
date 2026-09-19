# Claude Fable 5.1 · 提示词消化笔记与结论

> 基于官方《Prompting Claude Fable 5.1》整理的作者笔记，含概括与改编，不收录官方文档的连续译文段落或 16 节症状→处方索引；非官方文档、无厂商背书，API 参数与价格以官方现行页为准。核对日期 2026-09-05 / 09-10。

## 一、消化笔记

### 1. 排障式指南 = 「先减后加」的另一种写法

GPT-5.6 Sol 指南（见 GPT-5.6 笔记（`gpt-5.6.md`））的第一条是删重复、删无效示例、删无关工具；Fable 5.1 指南把同一哲学做成了症状表：**没看到症状就什么都别加**。两家在这一点上完全同向：提示词不是 SOP，而是对实测失败的最小修补。

### 2. 编排四条在 harness 里的操作化

| 官方节 | 在 Claude Code 这类 harness 里怎么落 |
|---|---|
| 3 批量工具调用 | 子代理任务提示末尾加「先列需求，再一次并行发出所有独立请求」；主对话自己也照做（例如三个研究子代理一条消息并行派出） |
| 15 主代理不空等 | 派子代理时用后台模式，主对话继续做备份、读本地文件等独立工作 |
| 4 历史只追加 | 自建 harness 才需要操心；Claude Code / Codex 已替用户处理 |
| 8 干完再停 | Claude Code 这类成熟 harness 通常已内置类似指令；自建 agent loop 才需手动加那两段 |

### 3. Effort 策略：默认 high，执行型子代理往下走

官方数据点很直接：`medium` ≈ Fable 5，`low` 在每任务成本上打得过 Opus/Sonnet。所以决策层跑 `high`；执行型子代理（检索、提取、格式转换）从 `low`/`medium` 起步，只有 eval 证明才升。换模型必须重扫，因为档位名不等价。

### 4. 成本口径变了：看每完成任务，不看每 token

缓存读降到 $0.25/MTok（基价的 2.5%），官方说这**可能**让「为省钱早压缩」不再划算并建议实验（下面把它当作者推论用）；批处理半价。执行层选型时把 Opus 5（$5/$25）、Sonnet 5（$2/$10）和 Fable 5.1 `low` 放在同一张「每完成任务成本」表里比，而不是只比单价。

### 5. 强制工具调用没了，工具描述要写「何时用」

`tool_choice: any/tool` 返回 400，官方明说改靠提示词。这和 Sol 指南第 5 节「工具说明回答四件事：做什么、何时用、返回什么、报错怎样」是同一要求——skill 的 description 和工具描述都要写清触发条件。

### 6. 摘要类任务给一个完整正例

第 7 节的做法可直接迁移到笔记整理与写作流程：研究类子代理的提示里放一个「请求 + 回应 + 为何正确」的正例，比写十条「不要抄原文」更有效。

### 7. 我的迁移检查单（从 Opus 4.8 时代的提示词）

- [ ] 删反格式化语句，或改写成「何时用什么格式」
- [ ] 删「把发现留到最后再说」类进度抑制行
- [ ] agent loop 加一句 batching
- [ ] 文件编辑提示加一句 targeted edits
- [ ] 强制 `tool_choice` 改 `auto` + 显式指令 + `strict: true`
- [ ] 从 `high` 重扫 effort；执行型任务试 `low`/`medium`
- [ ] 摘要类任务补一个引用正例
- [ ] 一次只改一组，改后重跑同一批任务

---

## 二、可带走的结论

1. **没症状不加指令**：Fable 5.1 指南是排障表，不是模板；先观察，再对症补一句。
2. **编排四条**：独立调用一轮批发、主代理不空等、历史只追加、干完再停。
3. **Effort 默认 high，子代理往下走**：`medium` ≈ Fable 5，`low` 打得过 Opus/Sonnet；换模型重扫。
4. **成本看每完成任务**：缓存读 $0.25 可能让「早压缩」不再划算（作者推论，官方建议实验）；批处理半价。
5. **工具靠描述触发**：强制调用已移除，description 必须写清何时用。
6. **旧模型的反格式化、进度抑制、整文件重写习惯要主动清理**。

## 来源与版本说明

- 主文：[Prompting Claude Fable 5.1](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1)（16 节，无 H3）
- 配套：[What's new in Claude Fable 5.1](https://platform.claude.com/docs/en/models/fable-5-1/whats-new-fable-5-1)；[Migration guide](https://platform.claude.com/docs/en/models/fable-5-1/migration-guide)（只取 from Fable 5、from Opus 4.8 or earlier 两条路径）
- 模型 id：`claude-fable-5-1`、`claude-mythos-5-1`（后者仅 Project Glasswing，能力相同）；1M 上下文、128k 输出；价格 $10 / $50 每百万 token，缓存读 $0.25，批处理 $5 / $25。
- Fable 5 指南（[Prompting Claude Fable 5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5)）已被 5.1 版覆盖，只取了章节标题做差异，未单独沉淀。
- 核对日期：2026-09-05。提取方式：opus 子代理按固定 schema 保真提取，主对话抽检三节。页面无发布日期标注。
- 本文只含消化笔记与结论，官方原文请看上面的链接。API 参数与价格以官方现行页面为准。
