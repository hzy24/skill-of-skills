---
name: skill-of-skills
description: 把你要干什么告诉Skill of Skills吧！不用想方设法构建复杂的提示词，也不用纠结琳琅满目的专业技能怎么选、选哪个，一句话感受agent的魅力！
metadata:
  version: "1.0.0"
  build: "2026-11-01-formal-1.0"
  release-stage: "release"
---

# Skill of Skills

首要交付是可审阅、可修改的任务方案。用户用日常语言描述目标；SoS 将任务映射到专业能力，选定后再组织委托与验收。每次执行至少有一个 Skill 承担核心业务工作。专业分析任务中的文档制作技能只能承担其实际覆盖的职责；内容制作本身就是用户目标时，制作技能可以承担核心工作。

## 形成方案

首次规划只读[规划入口](references/planning.md)。顺序为：需求与输入画像 → 业务领域/动作/输入条件到能力的映射 → 选定专业 Skill → 依据其方法组织业务委托 → 交付 HTML 与 JSON。专业能力负责内部分析、起草、计算和检查。确认前只看输入形状与方法适配。

用 `prepare_plan.py --starter --goal "用户的真实目标" --out draft.json` 获取业务骨架。读取 Skill 方法后运行 `method_source.py <原始SKILL.md>`，选择相关章节 ID 写入 method_sections；程序保存原文与版本，中文解释放在 fit_reason / input_fit。方案明确本次问题、材料可支持的判断、必要交接和成果标准；一个 Skill 能整体完成的工作保留为一个委托。`prepare_plan.py draft.json --out plan.json` 返回独立的 readiness；编译后按返回的 method-review.json 核读方法与输入适配，通过后再邀请确认；来源引用通过只代表原文可定位。引用问题可按返回指引定向修正一次。交付时按[元景保存](references/yuanjing.md)提供连接保存服务的 plan.html 和 plan.json，并准确说明可确认或仍待解决的事项。

复用适配的现有 Skill；数据分析可选[随包专业方法](references/composed-methods.md)，使用前核对本次适配。缺口只从元景市场和 Claude SkillHub（claudeskillhub.com）寻找。具体候选通过 acquire.py 限量读取并生成安装提案。新安装先在方案中列清技能名、真实渠道链接、方法优势、解决的问题、大小、版本及依赖，取得用户针对该提案的授权后再安装。普通执行确认不授予新安装权限。获取阶段禁止整仓库下载、归档和绕过限量入口。原文方法支持选择；热度用于召回。核心能力未落实时交付带缺口的方案，执行保持等待；专业原生降级路径已关闭。

用户在 HTML 保存后说“按方案执行”，宿主读取最新 plan.json。保存不启动任务。沿用已有明确执行授权；仅规划请求交付后结束。岗位工作流按需读[岗位配置](references/role-planning.md)。

## 执行与检查

确认执行时读取[执行协议](references/execution.md)，重新加载最新方案。使用 `execute.py open` 获取委托；未准备时按返回的 `ready` 命令一次登记核验结果。由宿主调用专业 Skill，用 `submit --record <已有真实日志> --applied <方法应用说明>` 自动登记成果和审阅快照；按随包 grader 的方法核读实际成果、执行记录及隐含主张，填写 review.json 的 quality 与逐项检查，再用 `accept` 收尾。模型填写实际日志与成果路径、方法应用和审阅发现，不手工维护 readiness 等关联字段。换用 Skill 时通过 `rebind.py` 同步方案；临时增加制作或辅助能力用 `--add-support` 明确负责成果，保留核心方法。新增安装仍需具体授权。专业或跨文件交付读取[质量检查](references/delivery-quality.md)。

专业 Skill 提供验证命令时按[原生验证](references/native-checks.md)记录实际结果；检查内容从用户标准、材料与所选方法生成。完成模块后读取真实产物，核对具体要求和输入版本；最终逐项回应原始需求。同一问题两轮无进展时定位原因并换方法；原授权范围内的修复继续推进，需要业务取舍时再与用户对齐。用户指定启动预算时通过 max_attempts 记录。

## 表达与资源

名称、解释和总结采用直接、具体的业务语言。说明工作对象、方法、用途与依据，删除重复解释和空泛口号。保留用户原话与来源引文的含义。

HTML 使用随包模板和保存服务。工作文件采用当前宿主可访问的任务目录；本地与远程通过附件交接。保存回执确认写入后才显示已保存。部署集成验收与日常任务分开，必要时按错误位置读取源码和参考。
