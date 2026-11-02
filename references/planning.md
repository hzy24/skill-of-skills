# 首次规划：从需求到专业委托

本页包含首次规划所需字段与判断。使用已经读过的内容；执行协议、制作手册与展开后的 plan 结构在相应阶段读取。

## 1. 输入画像

运行 `prepare_plan.py --starter --goal "用户原始目标" --out <任务目录>/draft.json`。输出包含可填写骨架，无需另读一个示例。填写 title、goal、mapping 和 inputs。

用 `profile_inputs.py <材料路径...> --out input-profile.json` 查看字段、规模、缺失与样本；文本查看章节和约束。足以判断方法适用性后继续。分组比较、达标率、排名、归因、草稿和图表属于确认后的专业工作。复用画像，不提前生成业务结论，也不在规划时安装制作依赖。

## 2. 选择专业方法

mapping 填 domain（领域）、action（需完成的判断或工作）、input_condition（现有材料条件）、capabilities（1–3个方法关键词）。先核对最相关的已启用 Skill；数据任务可按需选用[随包方法](composed-methods.md)，确认方法覆盖本次判断；能力缺口通过 `discover.py --draft draft.json --out search.json` 生成两处渠道请求，由宿主实际搜索元景市场与 Claude SkillHub（claudeskillhub.com）。目录摘要与星数用于召回，选择依据来自原始方法。其他目录域名不能登记为这两个渠道；GitHub用于候选原文追溯与下载。

至多细读三个候选；首轮仅找到工具或制作能力时，可补一轮相邻方法检索。找到适配方法即停止。原文地址来自实际详情链接或仓库目录；同一候选最多两种获取方式，不循环猜路径。同一任务的手工查询也使用该目录计时。五分钟是停止扩展检索的目标；宿主工具等待仍需如实计入总耗时。

外部候选先按[受控获取](discovery.md)使用 acquire inspect 阅读原文与目录元数据并生成安装提案，安装留待用户具体授权。读取候选入口及影响选择的必要方法后，运行 `method_source.py <原始SKILL.md>`。它返回章节目录与 ID；需要补读选定段落时加 `--sections <ID...>`。将实际采用的章节写入 method_sections，编译器自动提取原文、位置与版本。中文适配解释放在 fit_reason、input_fit；原文保持不变。来源可定位只是引用检查，方法是否能承担本次判断仍需核读。

skills 每项只需：
`{"name":"准确名称","source":"真实发现渠道与原文位置","method_file":"原文路径","method_sections":["目录中的ID"],"fit_reason":"支持本次哪个判断","input_fit":"现有输入如何满足方法条件"}`
已安装能力加 origin="installed"；新能力加 origin="external"、proposal="acquire 返回的 proposal.json 路径"。提案固定来源、版本、大小、理由和依赖。可选 version、license、installation；按已知事实填写。workflow/checks 可补充关键方法要求，无需复制整份 Skill。原文没有覆盖的业务或制作职责，另选适用能力。未选到时 work.skill 留 null，gap 写具体缺口与下一步。

## 3. 组织委托与边界

选定方法后，再按真实交接组织 work。一个成熟 Skill 可整体完成多个内部步骤；仅在不同能力接手、真实依赖或用户决策处拆分。专业 Skill 决定内部算法、重点调查、详细大纲、起草与修复。

每项 work 填 title、role（core/support/basic）、skill、inputs（材料或上游成果名称）、questions（本次待回答问题）、deliverables。成果写成对象：`{"title":"成果名称","format":"md","criteria":["本次可检查的标准"]}`。所有核心业务都有专业 Skill 承担；basic 用于基础交接。用户要排版本身时，排版可为 core。成果形式按用户需要确定。

交付承诺逐项对照材料与方法：对象和比较口径是什么，材料能支持什么判断，哪些条件会实质改变结论。已知边界写入 constraints，采用的条件性假设写入 assumptions（均为短文本列表）；它们随最新方案传入执行委托。重要而未解决、确实需要用户决定的事项写入 open_questions。可缩小结论范围完成主要目标时，写明范围继续规划。问清关键取舍，避免为可自行解决的细节反复提问。

例如，汇总记录支持表现比较，具体措施的效果需要措施记录；历史材料的截止判断需要评估时点。时间范围不等于采集时点，也不能自动采用系统日期。这些是证据适用性示意；本次限制由实际材料和专业方法决定。

检查按实际输入安排：当前材料的核对留在当前委托；依赖上游口径或结论时，把该成果名称写入 inputs。跨成果检查写入 final_checks：`{"artifacts":["成果一","成果二"],"criteria":"两者需要如何核对"}`，程序按这些引用安排位置。它不按“一致性”等词猜测依赖。用户明确页数时可在 pptx 成果增加 pages；否则细纲与页数由制作 Skill 在执行时展开。

## 4. 编译、修正与交付

运行 `prepare_plan.py draft.json --out plan.json`。程序生成结构、引用、合约与依赖，返回 readiness：

- needs_method_review：原文引用已核对；读取返回的 method-review.json，按[实质审阅](composed-methods.md)核对方法与输入适配，一次填写后 accept。
- ready_for_confirmation：专业适配已审阅，可确认执行。
- needs_installation_details：候选下载大小待核实；补齐提案后申请安装。
- needs_installation_approval：先展示具体安装提案并取得安装授权。普通执行确认不包含新安装。
- needs_capability：方案可审阅，列出未解决问题；先解决再邀请执行。若只是章节引用错误，按返回的 repair 命令修正一次，无需重新搜索。
- needs_decision / needs_review：尚需业务决定或编辑后的适配复核。
- plan_only：仅供规划参考。

首次成功编译与一次定向引用修正共两次。JSON 语法和草案结构先做输入校验，失败返回字段位置，不消耗编译机会；在原草案上定向修复，保留计时与已选方法。相同输入报错时先改对应位置，不重复运行。`--repair --base-hash <返回值>` 只允许修改原文章节引用，保留原方案备份；用户已编辑时拒绝覆盖。草案只使用 starter 的业务字段；capability_candidates 等执行结构由编译器生成。结构错误按诊断修正，停止猜字段或读完整源码。检索截止不阻止已有原文的本地修复；引用修正预算耗尽后交付明确缺口，不能填造证据。没有实际生成 plan.json 与 HTML 时，说明规划未完成并继续定位可修复的输入问题；草案不能替代可执行方案。

按[元景保存](yuanjing.md)交付 HTML 与 JSON。聊天、页面和程序的就绪状态应一致：未解决的问题直接说明；完成安装、保存或方法验证的表述均需对应实际记录。
