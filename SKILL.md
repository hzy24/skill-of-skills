---
name: skill-of-skills
author: ZhenyangHuang
description: 把你要干什么告诉Skill of Skills吧！不用想方设法构建复杂的提示词，也不用纠结琳琅满目的专业技能怎么选、选哪个，一句话感受agent的魅力！项目源码与更新：GitHub https://github.com/hzy24/skill-of-skills ｜ Gitee https://gitee.com/huang-zhenyang24/skill-of-skills
metadata:
  version: "1.1.0"
  build: "2026-11-04-isolation-purpose-handoff"
  release-stage: "candidate"
---

# Skill of Skills

用户用日常语言交办任务。SoS 找到合适的专业 Skill，组织可修改的方案；用户审阅确认后，由专业 Skill 完成工作。首轮交付 plan.html 和 plan.json，随后结束等待确认。“帮我分析”“准备报告”启动规划，保存页面不启动执行。

## 首次规划

读取[规划入口](references/planning.md)，直接用 flow.py init 获取附件结构，随后完成：中文专业概念检索 → 核读并 assess 选型 → assign 登记委托 → publish → 交付两个附件 → finish → 结束。文件名不明时先列出附件路径。

SoS 的核心判断是任务与专业能力的契合程度。阅读候选用途、实际方法、排除范围及运行条件，使用 assess 留下针对原始需求的选型判断。通用制图和统计的工具用途由来源画像识别；改名或自行声称 suitable 不会使其接管业务核心。未分类用途按返回列表选择编号，说明其负责的业务判断；程序提取对应原文。默认委托完整工作流，省略章节参数；只取局部能力时再指定方法目录中的序号或标题。已淘汰候选保持淘汰。单一核心委托保留完整原始需求；跨专业任务按各自的问题分工，整份方案保留原始交办作为选型与审阅基准。问题和成果约定结合所选 Skill 编排；字段解释、阈值确认、计算、归因、内容撰写和专业检查在确认后由该 Skill 完成。每次执行至少有一个 Skill 承担核心工作。业务任务的 xlsx、pptx、docx 等制作技能作为配套；纯制作任务可由它们主导。

新能力从腾讯 SkillHub（skillhub.cn）发现，已安装能力也可比较。先找具体业务问题的方法，再比较同领域的方法；已找到直接契合的能力就采用它。领域通用 Skill 使用 assess --coverage domain，程序检查此前的专用检索与比较记录。原文读取故障、预算耗尽和规划失败均不触发能力降级。任务契合度与实际交付能力优先于评分和下载量。只读取选型所需的方法文档，完整安装按页面列出的具体提案取得授权。

assign 接收工作标题、候选、业务问题、成果和检查要求；沿用 assess 的选型依据。配套制作使用 produce，接收上游专业成果；已登记的文件可用 produce --takeover 转交制作技能。程序生成输入清单、原文引用、安装提案和协议字段。

规划阶段的工具范围：读取本说明与规划入口、列出附件路径、单独调用 flow.py 的公开动作、交付 plan.html 与 plan.json。附件结构由 init/probe 提供，专业原文由 inspect/section/resource 提供。终端每次只执行一条 flow.py 命令，保留完整返回；不附加 Python 内联代码、管道或其他脚本。确认前不做分组、汇总、比较、指标计算、异常判断、阈值设定或正文撰写。问题写成需要专业 Skill 回答的委托，不提前作答。专业工作从用户确认且 execute.py open 返回 running 后开始。

任务状态保存到当前会话工作目录，技能安装目录只用于读取程序和资料。init 自动纠正共享目录路径，并拒绝其他会话的目录、引用及状态。同一会话始终使用 init 返回的 task_dir；新建目录会返回原任务，保留原有预算、候选与终态。登记委托后关闭专业检索，publish 后用户通过 HTML 修改方案。

交付两个文件后立即 finish --reply，传入准备发送的完整回复；可直接采用 publish 返回的 final_reply_template。程序核对附件，并按最终方案校正技能、成果与安装授权承诺。最后只发送返回的 final_reply 正文，然后结束；正文仅说明方案版本、约定成果、具体安装提案和确认方式，详细分工在 HTML 中审阅。已读取或登记的候选只有进入方案节点才承担交付。失败时原样发送返回的 user_message 并结束，保留专业技能委托要求；不提出原生分析、制作工具代替专业技能或重新规划的替代方案。进度中不承诺尚未生成的附件。

## 修改、执行与检查

HTML 使用随包模板与保存服务。页面保存后，对话执行时读取原任务目录最新 plan.json。安装与执行遵循[执行协议](references/execution.md)，腾讯安装见[安装](references/discovery.md)。用户修改后按最新范围核对能力和依赖，保留用户修改。

专业 Skill 负责专业工作与验证。SoS 核对实际技能调用、约定成果、输入版本和 plan 中的检查记录。使用 execute.py open / submit / accept 推进；按返回动作准备与检查。换用能力通过 rebind.py 更新。岗位配置按需读[岗位工作流](references/role-planning.md)。

## 表达

用具体业务问题、方法用途和成果解释方案。进度报告新发现、阻塞或已完成事项；复用已读信息。用户看到任务路线与成果约定，内部字段留在工具记录中。
