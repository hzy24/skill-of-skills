# 业务草案 v2：补充字段与兼容

首次规划的完整最小格式见[规划入口](planning.md)，starter 输出实际骨架。每个输入为 name/path，每个成果为 title/format/criteria 对象；名称唯一。questions、criteria 接受文本或文本列表。inputs 的上游成果引用决定依赖。多个模块复用技能时逐项核对职责覆盖。

skills 的 method_sections 引用 `method_source.py` 返回的 ID；唯一的准确章节标题也可使用。work.method_sections 可覆盖技能默认选择。程序保存原文，不要求模型抄写。旧 method_excerpt 继续读取：它必须是原文中的连续片段；新草案优先用章节选择。选择章节不证明专业适配，fit_reason / input_fit 仍需根据本次任务填写。workflow / checks 为可选补充。

final_checks 仅根据明确 artifacts 引用安排联合审阅；局部 criteria 保持原位。constraints、assumptions 为执行时必须保留的判断边界与条件，open_questions 只列影响执行的待决定事项。不需要限制时用空列表。

role=core 对应用户核心目的；support 为配套交付；basic 为基础交接。未找到方法时 skill=null 并填写 gap。核心缺口会阻止执行，配套制作不能替代专业方法。已有原文的方法型 Skill 可以由宿主按其完整指令采用。

编译器生成 ID、需求、引用、依赖、绑定和检查字段。业务草案不填写 bindings、contract、readiness 或 fallback_authorization。版本、许可和依赖未知时保持待核对。已安装能力填 origin="installed"；外部能力填 origin="external"、proposal="受控获取的提案路径"。执行前用 execute.py ready 登记真实入口和依赖验证；旧 plan 可继续读取、编辑与检查。

当前规划 CLI 为新方案启用 review_protocol_version=2，自动生成适配审阅表；业务草案无需填写这一字段。旧方案继续兼容原协议；采用新检查时运行 `method_review.py open plan.json` 升级并完成适配审阅，后续 capture 会生成实质审阅字段。
