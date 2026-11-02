# 复用的方法与审阅

随包方法保留上游原文、固定版本、文件哈希和许可证，详见 [manifest](../vendor/manifest.json)。它们作为可读取的方法资源使用，无需安装 Claude 插件、连接数据库或启动其他 Agent。宿主仍负责调用与脚本执行。

| 资源 | 适用工作 | 边界 |
| --- | --- | --- |
| [analyze](../vendor/knowledge-work/data/skills/analyze/SKILL.md) | 数据问题澄清、比较、分析报告、结果验证 | 可处理用户提供的 CSV/Excel；领域制度和因果判断另核对 |
| [statistical-analysis](../vendor/knowledge-work/data/skills/statistical-analysis/SKILL.md) | 分布、关联、趋势、统计推断的方法选择 | 先核对样本与假设；不为简单描述强加检验 |
| [validate-data](../vendor/knowledge-work/data/skills/validate-data/SKILL.md) | 分析口径、计算逻辑、偏差与结论证据检查 | 按本次分析读取相关段落 |
| [grader](../vendor/skill-creator/skills/skill-creator/agents/grader.md) | 事实、过程、质量主张和验收标准的实质审阅 | 审阅需要实际文件和记录；程序不替模型作专业判断 |
| [verification-before-completion](../vendor/superpowers/skills/verification-before-completion/SKILL.md) | 完成前取得最新验证证据 | 借鉴验证原则，不引入完整开发流程 |

数据分析需要这些方法时，可将准确名称和本地原文路径登记为 `origin: installed` 的候选，source 写随包上游来源。方法适合才选择；业务规则或专门方法存在缺口时，仍从元景市场与 Claude SkillHub 查找。随包数据方法不替代法律、医疗、财务制度、工程等领域方法。

## 两个实质审阅时点

在当前任务上下文完成这两个短审阅；复用已读的原文与画像，仅补读疑点对应片段。无需另外启动评审会话、Agent 或一套全量评测流程。

规划编译自动返回 `method-review.json`。结合已读的方法与输入画像，一次填写各需求的 verdict、method_quote、reason、input_basis、limits，再运行：

```
python <skill>/scripts/method_review.py accept <任务目录>/plan.json
```

这一步回答“方法覆盖本次什么判断，输入满足什么条件，哪里需要限制”。不分析完整数据、不写草稿。源引文通过只是定位成功。能力不适配记 fail，解决方法缺口后重开审阅。修改范围或换用技能后用 `method_review.py open plan.json` 生成当前表；纯准备状态更新不重审。

交付时 `capture` 在同一张审阅表中生成 quality。按 grader 方法检查各成果中的实际主张、执行记录和验收标准，填写：

- observed_skills：实际采用的全部专业和制作技能。
- claims：重要事实、推断、原因、建议、过程或质量主张；逐项写成果位置、来源证据、判定。标准没有列出但影响结论的主张也需检查。
- check_coverage：标准是否覆盖用户的实际问题，有无遗漏。
- findings：尚未解决的问题；result 表示整体审阅判定。

这些内容由本次任务与成果生成。只做简单转换时，一条核对内容与原文的质量主张即可。复杂分析要核查影响决策的主张，不能用“文件正常、数字一致”替代。

宿主提供真实工具调用 JSON 时，submit 加 `--trace <路径>`；程序能识别显式 Skill 调用和直接执行的技能脚本。无调用记录时通过真实方法执行日志与成果审阅，不宣称工具轨迹已自动验证。读取 SKILL.md、导入 pandas 和引用技能名称均不能单独证明方法已应用。

临时新增辅助技能，用 `rebind.py plan.json --node N1 --skill helper.json --add-support --outputs D1_1 --reason '实际分工' --verification '入口与依赖核验' --base-hash <最新哈希>`。helper.json 使用原有 skills 对象格式；命令保留核心技能与原范围，更新辅助职责、输入、审阅及受影响执行记录。外部安装继续按具体提案取得授权。
