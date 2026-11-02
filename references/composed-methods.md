# 方法适配与计划履约

SoS 负责选能力、组织计划、跟踪执行。专业分析、判断和专业检查由选定 Skill 完成。

## 规划时核对适配

编译返回 method-review.json。根据已读取的 Skill 原文与材料画像，确认方法能承担委托。填写 verdict、method_quote、reason、input_basis、limits，运行 `method_review.py accept plan.json`。判断依据是任务契合度；不提前开展专业分析或生成草稿。

## 执行后核对计划

capture 生成同一份核对表：

- items：按 plan 已确认的标准逐项核对输出、文件位置及约定检查记录。
- quality.observed_skills：实际采用的准确技能名，与 plan 绑定和执行日志对照。
- quality.findings：尚未解决的计划偏差；没有偏差填空列表。
- quality.result：本模块是否按计划完成。

无需额外填写 claims 或重新分析专业结论。专业 Skill 负责专业检查；SoS 核对该检查是否按计划完成及其交付记录。真实工具调用 JSON 可在 submit 时通过 --trace 传入，辅助核对实际调用。全部约定成果和检查通过后 accept；最终 audit 核对全计划完成情况。

新增技能通过 rebind.py 更新分工，再继续执行。修改成果后重新 capture，保留文件版本和记录关联。
