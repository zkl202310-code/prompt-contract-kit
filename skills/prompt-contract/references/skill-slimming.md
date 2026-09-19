# Agent 与 Skill 文档精简原则

来源（作者整理与改编，非官方文档、无厂商背书）：OpenAI 2026-09-11 文章 [Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra) 与 [Astra 指令遵循指南](https://developers.openai.com/api/docs/guides/latest-model#gpt-6-astra-instruction-following)；Anthropic 的 [CLAUDE.md 导入文档](https://code.claude.com/docs/en/memory#import-additional-files) 与 [Skills 文档](https://code.claude.com/docs/en/skills#add-supporting-files)。核对日期 2026-09-12。

官方建议集中在五点：技能描述写准触发；多流程按需展开；全局资料按任务读取；边界表达避免无谓停顿；完成条件涵盖实际交付与验证。文章没有承诺固定的压缩率或额度收益。

## 方法：逐条问「它会改变什么决策」
再决定保留、合并、下沉或删除。把权限、事实、业务规则和验收要求视为需要保护的内容，字数只用于观察改动量。**模型更强不构成删除这些条件的依据。**

| 常见问题 | 处理 |
|---|---|
| 全局入口列出多条重叠触发，并要求完整读某协议 | 合并为任务意图，指向协议的对应章节 |
| 协议重复列出构造模块、派单要素和发送前检查 | 合并为结果、约束、证据、输出与停止条件 |
| skill 描述夹带流程细节、参数和大量触发语 | 描述只保留真实操作与必要排除项，细节留在正文 |
| 互不相同的多个流程一起加载 | 原流程移入各自参考文件，入口只做路由 |
| 路由表容易被理解为「每次都要显式换模型」 | 保留表，注明选型须受本次授权与宿主限制约束 |

## 边界
- 指令冲突需要可见：若 skill 造成暂停或偏离请求，应指出文件和条文、解释适用条件；用户明确请求高于 skill 指引，系统与工具权限仍有效。
- 维护时先确认真实问题，再改最小范围；一次小修不触发全库审计；已有检查通过且输入未变就停止复核。
- 复杂改动若需要行为评测，另固定输入、模型、effort 和验收标准，记录失败与重试；**字符减少不能换算成质量或额度提升**。
- Claude Code 的 `@文件` 导入会在启动时展开；按需参考应说明触发条件，不把拆文件本身当作减少加载。Skill 入口保留目的、边界和导航，细节由参考文件承载。
- 模型症状仍按各自模型笔记判断（例如 Fable 5.1 长任务有时需要明确持续完成；低 effort 下查证要求不能随精简删除）。无人值守示例中的「用户不能即时回答」只适用于真实无人值守任务。
