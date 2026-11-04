# 计划协议 v1

新计划通过业务草案编译，采用 capability_policy: skills_first、capability_policy_version: 3。首次规划见 planning.md 与 draft-format.md；本页仅用于维护展开后的协议。旧版 selection-* 示例保留作兼容测试，不作为新任务模板。

新任务通过 flow.py init / assess / assign / publish 生成方案；prepare_plan.py 保留为编译器及旧任务入口。机制测试夹具位于源码仓库的 tests/fixtures，安装包只包含 SoS 自身。内容拆解按需查 [内容规划深度](planning-depth.md)。

顶层：id、title、goal、revision（正整数）、mode（plan_only / execute_after_confirmation）、requirements、materials、deliverables、nodes。具有多部分内容的成果增加 `content_outline`。可增加 assumptions、open_questions、constraints、capability_candidates、role_tasks；约束和交付标准同时写入可追踪 requirements。

需求为 `{id,text}`；材料为 `{id,title,path}`；交付物为 `{id,title,description,format?,outline_ids?,outline_level?}`。路径指向本次真实材料，未提供时明示缺口。`format` 使用 pptx、docx、csv 等实际文件格式。演示文稿需写 `format: "pptx"` 和非空 `outline_ids`，新计划默认显式设置 `outline_level: "sections"`，顺序表示汇报主题；用户需要逐页审阅时设为 `pages`，顺序即页序。未声明时沿用旧版逐页语义。其他成果按需要关联章节、分析项或功能。回答某份成果的内容或制作该成果时，先找到对应 deliverable，再按其 outline_ids 取内容；总内容数组可同时含比较表与 PPT，数组第一项可能属于另一份成果。

内容蓝图 `content_outline` 为数组，每项结构如下：

```json
{
  "id": "S1",
  "title": "哪些供应商满足预算、部署与上线约束？",
  "claim": "根据需求与报价核对候选是否满足硬性条件，形成可追溯比较。",
  "points": ["费用组成与后续维护口径", "部署方式与数据流向", "上线时间及其前置条件"],
  "sources": ["brief#需求边界", "brief#方案和报价"],
  "visual": "按条件组织比较表，并标注来源。",
  "acceptance": ["费用包含软件、硬件或平台、培训", "第二年维护单列", "推荐表述限定为讨论建议"]
}
```

`id` 全局唯一；`title`、`claim`、`visual` 为非空文本，`points`、`sources`、`acceptance` 为非空字符串数组。`sources` 使用材料 ID 加章节、表行、页码或其他真实定位。sections 模式每项表达本次问题或主题，具体内容由专业技能在执行中形成；pages 模式每项代表一页。`points` 保留重点和约束。分析任务以每个重点问题为蓝图项：title 写问题，claim 写待验证问题，points 写选题依据、采用方法和证据缺口，sources 同时定位材料与方法来源，acceptance 写回答问题所需的证据与检查。参考方法的材料路径使用已读取的本地快照；原 URL 记录在 source_url；未知来源不填造。`claim` 写这一部分要回答的问题；未知事实明确标为待核实，不编造数值或机制。章节大纲同样使用此结构，`visual` 可写表格、段落或交互组织方式。

模块字段：id、title、description、reason、method（direct / skill / human）、depends_on（模块 ID）、inputs（材料或上游产物 ID）、outputs（唯一产物 ID）、requirements（覆盖需求 ID）、done_when（自然语言完成条件）、checks、bindings。可增加 `outline_ids` 引用该模块负责或核对的内容。蓝图 ID 与产物 ID 分别使用；`inputs` 始终引用材料或产物。模块的描述、理由和检查写出本任务特有的口径、取舍和验收依据。

新版计划设置 `capability_contract_version: 1`，选中能力按 [能力参与规划](capability-planning.md) 填写 contract。ready 需要已核验的前置条件与调用依据；必需检查完整纳入节点 checks。

技能绑定：`{skill,scope,reason,readiness}`。skill 为当前宿主准确标识，scope 说明完整或限定范围，readiness 为 ready / needs_setup / unknown。可补充 source、version、prerequisites、verification。仅依据真实清单和运行条件写 ready。

检查规则：`{kind,artifact}`。file 检查非空文件；text_contains 加 values 字符串列表；csv_columns 加 values 列名列表；pptx_pages 加 value 整数，pages 模式数值与该成果 `outline_ids` 数量一致；sections 模式页数独立，仅在确切页数为要求时配置；review 等待宿主读取真实产物后的证据。native 接入专业 Skill 的实际验证命令记录，字段及运行方式见 [原生验证](native-checks.md)。复杂分析通常组合机械检查与 review。人工决策节点产出确认记录文件，保留用户决定原文。首次方案审批已经涵盖现有大纲，只有需要审阅后续计算或证据、或发生关键业务变化时才增加中途人工节点。

输入产物必须由依赖链中的模块生成。最终 deliverables.id 必须出现在输出中。中间产物也配置检查。多模块共用一个技能调用时由宿主协调，首次执行各模块仍遵循各自依赖和检查。

交互页面保留基础版本和内容哈希，编辑批次形成下一版本。保存服务通过 [元景交互方案](yuanjing.md) 接收增量，用 apply-edits 验证后原子保存，再核对语义影响。HTML 保存接口只接收 update_plan，执行请求来自用户对话。离线导出作为备份。已有执行记录与计划内容哈希绑定，实质修改用 reconcile 更新记录并重新确认受影响范围，展示名称修改保留已有证据；复用产物仍核对哈希。

当前协议的 selection_review_nodes 是编辑器派生的待复核模块列表。max_attempts 为可选正整数任务预算。执行记录使用排除 title/revision 的执行摘要哈希；页面冲突检查仍使用整个计划的内容哈希。URL 材料先保存本地快照，source_url 保留出处。
