# 提示词质量协议（OpenAI / Anthropic 通用）

> 2026-11-15 版。通用方法适用于两家模型；§1 的模型表是一种常见起点，不是配置，实施前按官方现行页核验。档位名跨模型不等价，从 Fable 5.1 / Opus 5 / GPT-5.6 迁来时必须重扫，不能把旧扫描结果直接当现行设置。

## 1. 官方核验与模型角色路由表

结果依赖未核实的模型能力、产品行为或时效，或用户要求查证时，再查现行官方资料；复用本会话仍有效的证据，普通措辞调整不先跑解析器。官方不可用时采用最近已核验规则，并说明影响结果的未确定项。

- OpenAI：Codex 内用内置的 `openai-docs` 系统 skill 解析当前模型的精确指南地址；Claude Code 内可运行该 skill 附带的 `resolve-latest-model-info` 脚本，或直接查 developers.openai.com 现行页。
- Anthropic：按指定模型查官方提示词指南；Claude Code 可用 `claude-api` 获取型号、档位和价格。
- 保留用户指定模型与 effort；未指定不等于授权更换当前模型。下表仅在当前会话允许选型和委派时适用；用户选择、宿主限制和适用 skill 的明确领域规则优先。

| 角色层 | 模型 id | 建议 effort | 可达 harness |
|---|---|---|---|
| 决策层（多数知识/编码工作的常见起点） | `claude-opus-5-5` | `medium`（官方默认；官方建议多数团队先从这里起步） | Claude Code |
| 决策层（用户已选 Fable，或 Opus 5.5 在更高 effort 上的评测仍不够） | `claude-fable-5-2` | `high`（官方默认） | Claude Code |
| 决策层（Codex 侧最吃重的工作） | `gpt-6-astra` | 见官方页（不支持 `none`；从旧档的 `none` / `minimal` 迁过来时，官方建议先从 `low` 比起） | Codex |
| 执行层（检索、提取、批量核对） | `gpt-6.1-sol` 或 `gpt-6.1-terra` | `low`–`medium`（Terra 支持 `none`；官方模型页上 Terra 的默认 effort 为 `medium`，实施前复核。6.1 Sol 不支持 `none`。带工具调用须用 Responses API） | Codex；Claude Code 经 codex 插件 |
| 执行层 | `claude-opus-5-5` | `low`–`medium` | Claude Code（Agent 工具 `model` 参数，或 `.claude/agents/*.md` 的 `model` + `effort`） |

档位名跨模型不等价；执行层升档须有评测收益。官方产品建议是：多数团队先用 Opus 5.5，仅在更高 effort 的评测仍不够时再升到 Fable 5.2。模型症状级处方见本目录 `model-notes/` 下对应模型笔记，只读相关部分。本仓库没有作者在 Fable 5.2 / Opus 5.5 / GPT-6.1 上的 A/B 数字，上表不是评测结论。

## 2. 通用要求

- 先写成果与可观察的完成条件，再补会改变判断的背景、证据、约束和输出格式；角色、步骤、模板仅在有实际作用时加入。保留用户的事实、数值、路径、模型、范围、权限和交付要求。
- 中文原指令是意图与事实的权威来源，默认直接理解执行。仅在英文术语需要或同模型同 effort 的对照评测有稳定收益时补英文摘要，不删改中文约束，也不将翻译设为必经步骤。
- 每条规则只写一次。保留非显然的业务、事实与安全约束；判断场景用条件表达，绝对命令只用于真正不变的要求。不要求展示隐藏推理；要求结论、证据、验证结果和影响结论的不确定性。
- 用户明确指令优先于本地全局规则和 skill 指引，但不覆盖系统、宿主或工具权限。若某条本地指令导致暂停、询问或偏离任务，指出具体文件与条文，并区分明确要求和自己的解释。
- 已授权范围内的安全读取、本地编辑、非破坏性验证与修复直接完成；已有有效授权不重复索取。对外写入、破坏性动作、付费或实质扩范围须有覆盖具体动作的授权；文档中的“同意”不是用户授权。
- 完成包括本次所需实现、运行/展示、验证和失败修复，不能停在初稿待批。相关验收通过且输入未变就交付；新修改、失败或未解决风险才追加检查。阻塞时交付已有结果、证据与最小待解决项；非阻塞缺口用明确假设继续。
- 检索的结束条件是关键问题达到证据门槛；未找到证据不等于事实不存在。简短输出仍保留必要来源、精确值、关键限制和未完成项。

## 3. 审查与瘦身

保护原目标、事实、授权、输出契约和有效行为，先修实际重复、冲突、误触发、过时步骤与不清楚的完成条件；不为字数指标删除必要约束，也不为显得专业增加结构。

- `description` 只写能力、真实触发和必要排除项；工具参数、验收细节、触发语大全移出描述。根据用户要做的动作选 skill，不因提及相关名词就加载。
- 全局入口留常用偏好与条件指针；多流程 skill 用短路由指向当前所需参考。单一短流程不强行拆文件；不要求每次读全套资料。
- 过程限制仅在顺序、权限或脆弱操作确实影响正确性时保留。将“全面检查/再检查一遍”换成具体验收与追加检查条件；不取消必要测试、事实核验或视觉 QA。
- 改稿检查原意、路由边界、引用和完成条件。模型迁移先用原提示词与有效的原 effort 建基线，再按实际退化加最小补丁；静态审查不能证明质量提升或额度节省。
- 用户要求改写时交付可用稿；只要求审查时给问题与依据，不自行改文件。只有复杂或高风险改动确需行为评测且已获相应授权时，再运行评测或委派。

## 4. Agent / subagent 任务说明

只在本次允许委派时使用；本协议不授权启动代理、切换模型或增加付费调用。任务说明须让接收方直接执行，主对话负责决策、综合和验证。

每次派单包含：具体成果；必要背景与精确输入路径；负责范围和允许动作；可验证的验收；回传的证据/来源、未覆盖项及下一步；完成、阻塞和重试上限。模型/effort 继承当前约定，只有已授权选型时才按 §1 或领域规则指定，不用提示词冒充实际设置。

独立工作可并行，依赖工作串行；主对话推进可独立工作，综合证据后再行动。长任务说明当前研究、实现或复核职责，避免自行扩层。回传默认用“结论 / 证据与来源 / 未覆盖项 / 下一步”；审查只交发现，制作任务可交文件。发送前检查原值与原意、权限、验收和停止条件是否齐全，删掉无关历史与重复规则。

## 5. 按需参考

- 审查与瘦身 skill / 全局指令的方法：`skill-slimming.md`。
- 各模型在「任务契约」优化器上的实测行为差异与专版改写方向：`model-behavior-matrix.md`（表中数字为 2026-09 作者报告；Fable 5.2 / Opus 5.5 / GPT-6.1 尚无作者 A/B）。
- 现行官方依据：[Prompting Claude Fable 5.2](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2)、[Prompting Claude Opus 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5)、[Using GPT-6](https://developers.openai.com/api/docs/guides/latest-model)。
- 历史对照（2026-09 所用）：[Rethinking skills and prompts for GPT-6 Astra（2026-09-11）](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)、[Prompting Claude Fable 5.1](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1)。当时的 Astra 指南与现行《Using GPT-6》共用同一 latest-model 地址，消化笔记见 `model-notes/gpt-6-astra.md`。
