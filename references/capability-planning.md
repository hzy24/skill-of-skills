# 实际调用约定

首次规划使用 [规划入口](planning.md)。本页在需要实际调用技能时读取，核对调用入口、分支、交接和必要检查；方法参考保留在选型依据及内容来源中。

## 责任与交接

模块约定目标、具体范围、输入输出、关键约束和验收。专业 Skill 负责内部方法、步骤和验证。用户要求与组织规则约束交付；技能默认做法与它们冲突时说明影响并调整，保留专业方法所需条件。超出授权或改变范围的取舍回到用户。

首次业务草案只填写 planning.md 的业务字段，contract 由编译器生成。维护展开后的协议时，一个完整 Skill 负责整个模块可用 `{ "inherit": "node", "invocation": "本次准确调用入口" }`。prepare_plan 从节点复制输入、输出、检查，从绑定候选复制来源和证据，不设置可用或批准状态。多个绑定和局部流程按实际分工维护各自约定。展开后的 plan.json 为唯一保存和执行依据。

## 能力约定

新版计划顶层写 `capability_contract_version: 1`。每个 binding 保留原有 skill、scope、reason、readiness，并增加 contract：

```json
{
  "source": "当前宿主的准确技能路径或版本引用",
  "source_evidence": "实际读到的分支、资源和质量要求的位置",
  "mode": "full",
  "invocation": "当前宿主提供的调用入口和准确技能标识",
  "inputs": ["approved_content"],
  "outputs": ["slides"],
  "prerequisites": [
    {"requirement": "制作和渲染工具可用", "status": "pending", "evidence": ""}
  ],
  "required_checks": [
    {"id": "slides-content-layout", "kind": "review", "artifact": "slides", "criteria": "逐页核对确认的大纲、来源与渲染图，记录溢出、遮挡和旧占位文字的检查结果。"}
  ],
  "verification": ""
}
```

- inputs/outputs 使用该模块的材料或产物 ID。required_checks 完整加入该模块 checks，review 的 criteria 写本任务的检查标准。使用现有检查类型；没有程序检查器的内容由宿主阅读真实产物审阅。
- mode 为 full 或 branch。branch 须补 branch_basis，指出技能明确支持的分支与保留的前置、质量步骤。不要任意截取一段指令。
- prerequisites 无额外条件可用空列表。verified 必须有具体 evidence；ready 还需要 verification 记录当前调用条件的核验依据。未核验保持 unknown 或 needs_setup，交付方案可以保留缺口，执行前补齐。
- 方法依据通过 candidate_id / capability_need_ids 引用；新计划不重复填写 contract.planning_effect。旧字段保留兼容。
- 结构检查可发现引用、状态和检查遗漏；实际调用与审阅证据按执行协议记录。

旧计划缺少该版本字段时保留兼容并提示补充。新生成的计划始终采用本协议；升级旧计划时保留材料与用户修改，补齐约定后重新审阅受影响的安排。

确认执行后，专业 Skill 的检查按 [原生验证](native-checks.md) 接入。需要 Office 交付时再读 [Office 成果](office-deliveries.md)，并核对当前实际能力。
