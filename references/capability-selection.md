# 执行前复核能力

首次规划遵循 [规划入口](planning.md)，编写 [业务草案](draft-format.md)，程序生成选择协议。此页用于执行准备和用户修改后的复核。

## 复核范围

从最新 plan.json 读取用户目标、mapping、核心委托和选定技能。逐项对照原文中的方法、输入条件与检查，核对选择依据仍成立。成果制作技能仅覆盖其实际业务范围；专业任务需要专业方法。至少一个 Skill 负责核心工作，任何核心缺口未解决时保持等待。

高星、维护和官方来源可用于候选召回；使用效果仍需实际产物验证。专业 Skill 内部可使用 pandas、numpy 或其他工具。方法与任务不匹配时重新选型，不能通过标为 basic 或补一个无关文件技能规避缺口。

## 准备与绑定

运行 execute.py open；未准备时返回 preparation_required、plan_hash 和完整 ready 命令。读取方法并核验入口及必要依赖后，用 ready --base-hash <值> --verification '实际核验结果' 一次登记。用户编辑后的适配复核也通过该命令记录，关联字段由程序更新。

外部技能先按[受控获取](discovery.md)展示具体提案，取得安装授权并安装。普通执行确认不授予新安装权限。原文、版本和授权记录缺失时保持等待。

专业模块 decision.kind 使用 skill 或 deferred。basic/direct 仅用于基础交接。新策略 v3 关闭专业 direct/reference 降级路径，不接收 fallback_authorization。旧方案保持可读；迁移时基于实际方法重做选择。

## 修改与证据

HTML 保存可以成功，执行前复核 selection_review_nodes 涉及的模块。完成复核后更新依据，清除对应选择复核标记，调用 reconcile；范围未变化时沿用已有执行授权。程序负责关联字段，用户无需维护它们。

method_support 指向实际原文，工作节点携带该输入。编译记录原文哈希，start 核对版本；finish 核对实际执行记录、方法版本及所负责输出。引用或记录存在只证明文件和关联齐全，专业适配与实际方法采用仍需宿主审阅。完整流程见 [执行与证据](execution.md)。
