---
name: skill-of-skills
author: ZhenyangHuang
description: 把你要干什么告诉Skill of Skills吧！不用想方设法构建复杂的提示词，也不用纠结琳琅满目的专业技能怎么选、选哪个，一句话感受agent的魅力！项目源码与更新：GitHub https://github.com/hzy24/skill-of-skills ｜ Gitee https://gitee.com/huang-zhenyang24/skill-of-skills
metadata:
  version: "1.2.0"
  build: "2026-11-06-competition-release"
  release-stage: "stable"
---

# Skill of Skills

用户用日常语言交办任务。SoS 找到合适的专业 Skill，组织可修改的方案；用户审阅确认后，由专业 Skill 完成工作。首轮交付 plan.html 和 plan.json，随后结束等待确认。“帮我分析”“准备报告”启动规划，保存页面不启动执行。

## 终态直接返回

工具返回 `terminal: true` 与 `dispatch: final_reply_only` 时，本轮工作已经结束。下一条消息仅发送 `final_reply` 的完整正文。该字段由程序从实际状态生成，承担交付与授权说明；不再调用工具、添加方案摘要、改写安装确认句或提出其他完成方式。此规则同时适用于正常交付和规划失败。

`planning_failed` 封存本次规划，普通“开始”“按方案执行”不能恢复或替换它。诊断已由程序保存，本轮无需继续排查。后续修复沿用用户另行提出的明确任务；失败本身不产生原生分析、工具替代或另开目录的授权。

## 首次规划

读取[规划入口](references/planning.md)，直接用 flow.py init 获取附件结构，随后完成：中文专业概念检索 → 核读并 assess 选型 → 按专业方法划分业务阶段 → route 登记路线 → review 核对阶段适配 → publish → 交付两个附件 → finish → 结束。文件名不明时先列出附件路径。

新能力从腾讯 SkillHub（skillhub.cn）发现，已安装能力也可比较。按原始需求映射专业领域，用中文概念检索，核读用途、方法和运行条件后 assess。直接契合的方法优先；同领域通用方法用 --coverage domain，可迁移的统计、数据分析或运筹方法用 --coverage method。比较依据、负责范围与判断边界写入方案；选型以实际方法为据，下载量辅助判断。具体规则见规划入口。已淘汰候选保持淘汰；下载方法文档保留外部来源，完整安装按具体提案取得用户授权。

每次执行至少有一个 Skill 承担核心工作。业务任务中的 xlsx、pptx、docx 等负责配套制作；纯转换、排版任务可由制作技能主导。按专业方法组织业务阶段，一个 Skill 可负责多个阶段，简单任务可用单阶段。方案保留总体目标，各阶段约定自己的问题、结果与依赖；字段解释、阈值核实、计算、判断、内容生成和专业验证交给确认后的专业 Skill。

选型后运行 route-template，按业务阶段填写 route.json 的问题、方法应用、成果、检查和依赖。程序生成引用与协议字段，并沿用配套制作角色。route 返回只读 context_file 与判断文件 review_file；核对后只填写 need、verdict、reason，运行 review_command。方法原文、来源和版本由程序维护。

规划工具用于读取入口、列出附件、编辑 route.json/review_file、读取 context_file、调用 flow.py 和交付两个附件。附件通过 init/probe/material 读取，方法通过 inspect/section/resource 读取。每次单独运行一条 flow.py 命令，直接读取返回；长内容用 view_command，返回丢失或解析异常用 status 的 last_result_command 恢复，无需追加 head、管道或 Python 解析。阶段问题保持为委托；业务计算、异常判断与正文撰写从用户确认且 execute.py open 返回 running 后开始。

任务状态保存在 init 返回的 task_dir，技能安装目录只读。程序隔离会话，重复 init 或另建目录沿用原任务及预算。登记路线后核对适配；补选用 reselect 指定阶段。publish 后用户通过 HTML 修改方案。

交付两个文件后立即 finish --files，传入附件工具返回的实际路径。程序核对最新方案与附件，生成版本、成果、安装提案和确认方式；按终态正文发送并结束。安装与执行沿用用户实际授权。

规划审计按当前任务的文件对象区分合法编辑与业务处理，并核对实际收尾；宿主终端工具的拦截权限由宿主管理。

## 修改、执行与检查

HTML 使用随包模板与保存服务。页面保存后，对话执行时读取原任务目录最新 plan.json。安装与执行遵循[执行协议](references/execution.md)，腾讯安装见[安装](references/discovery.md)。用户修改后按最新范围核对能力和依赖，保留用户修改。

专业 Skill 负责专业工作与验证。同一 Skill 可连续完成多个阶段，复用已核验原文和上游结果，分别保留阶段成果与执行记录。SoS 核对实际技能调用、约定成果、输入版本和 plan 中的检查记录。使用 execute.py open / submit / accept 推进；按返回动作准备与检查。换用能力通过 rebind.py 更新。岗位配置按需读[岗位工作流](references/role-planning.md)。

## 表达

用具体业务问题、方法用途和成果解释方案。进度报告新发现、阻塞或已完成事项；复用已读信息。用户看到任务路线与成果约定，内部字段留在工具记录中。
