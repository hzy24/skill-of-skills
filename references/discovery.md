# 专业能力发现与安装

先核对最相关的已启用技能。缺口仅从元景市场和 Claude SkillHub（https://claudeskillhub.com）寻找。搜索命中其他域名时忽略该结果；渠道不可访问时如实记录限制，保留能力缺口。

## 小范围检索与阅读

`discover.py --draft draft.json --out search.json` 生成最多两轮请求。宿主使用实际市场/网页工具搜索，持久计时由 starter 开始。找到适配方法后停止扩展；五分钟到达后用已取得的方法编译或交付带缺口的方案。此阶段只查看输入画像，不做业务计算、起草或制作。

进入 Claude SkillHub 真实详情页，跟随仓库链接定位具体 Skill 的 SKILL.md 。文件链接可以包含分支，程序将其解析为固定 commit。每个候选最多两种定位尝试；遇到访问限制就保留缺口，不循环猜路径。GitHub 只追溯已确定的候选。Claude SkillHub 包含订阅技能；详情页没有公开原文或下载元数据时记录访问限制，不能默认免费开源，也不能猜测 GitHub 仓库。此时可先交付带缺口的方案，用户提供合法取得的原文和包后再核验。

候选获取统一使用：

```sh
python <skill>/scripts/acquire.py inspect --task-dir <任务目录> --catalog-url <ClaudeSkillHub详情HTTPS链接> --method-url <GitHub具体技能SKILL.md文件链接> --reason '原文或样例显示的适配优势' --solves '本任务交给它解决的问题' --dependencies '运行依赖及额外下载需求；未知写待核验' --license '已核实许可或待核验'
```

程序核对详情页实际仓库链接，只读原文和目录元数据，返回 method_file、proposal 与 proposal_hash。单个响应上限 256 KiB；每候选最多 12 次目录请求、60 秒；同一任务最多三个新候选请求，共享五分钟检索预算。相同请求复用经过版本检查的本地原文与提案，避免重复下载。它不下载归档、不 clone、不运行安装脚本。遇到限制交付缺口，不改用 curl/wget、其他目录站或整仓库下载绕过入口。

`method_source.py <返回的method_file>` 获取章节 ID。只选影响适配的章节，解释本任务的用途、输入条件与限制。通用库可用性、排名和星数不能代替方法证据；维护、热度与样例必须来自实际观察。

## 方案中的安装提案

业务草案 skills 填 origin="external" 和 proposal 路径。程序将提案嵌入 plan.json，HTML 详情展示：

- 准确技能名、Claude SkillHub 或元景市场真实详情链接、固定版本。
- 为什么选择、实际方法优势、解决的具体问题与未覆盖部分。
- 下载字节数、文件数量和技能目录；运行依赖的额外下载、权限另列。
- 安装范围及待用户确认状态。大小、许可或必要依赖未核实时，先补齐再安装。

聊天简短提出具体请求，例如：“建议安装 X 来做条款交叉核对，技能文件共 86 KB，来源和理由已放在方案里。是否同意安装 X？”用户无需填写协议。普通“按方案执行”、保存方案、泛泛同意使用专业能力均不代表接受新安装。已有针对同一版本和范围的明确授权时可沿用，不重复询问。

用户拒绝时保留方案，寻找当前权限内的已安装能力，或等待用户调整；不自动降级。

## 获准后安装

```sh
python <skill>/scripts/acquire.py install <proposal.json> --task-dir <任务目录> --proposal-hash <返回值> --evidence '用户针对该技能的实际安装授权原话'
```

只下载批准的文件清单，逐文件核对大小与 Git blob 版本；总上限 10 MiB、100 文件、120 秒。依赖单独核对授权，不执行远程脚本。失败清理临时目录；内容或版本变化须重新提案。安装到任务的 .sos-installed/。读取方法和必要配套资源后用 execute.py ready 核验，不手工修改 readiness。

## 元景市场

由宿主市场工具取得真实详情、版本、大小及依赖，将结果整理为 metadata.json：schema="sos-market-proposal-v1"，name、skill_id、version、catalog_url、download_bytes（已核实的字节整数；未提供填 null）、reason、solves、dependencies、license、metadata_evidence（实际工具结果引用）。运行 `acquire.py market --metadata metadata.json --out proposal.json`，在方案中展示。市场不提供大小时仍可生成提案，页面显示待核实，执行保持等待；从实际包元数据核实后更新提案，再申请具体安装授权，不能用 0 代替未知。

获准后调用宿主市场安装工具，保存实际结果为 installation.log，再登记：

```sh
python <skill>/scripts/acquire.py record-market <proposal.json> --task-dir <任务目录> --proposal-hash <值> --evidence '用户具体授权原话' --method-file <实际已安装SKILL.md> --record <installation.log>
```

优先使用宿主实际暴露的市场工具；客户端 HTTP 接口是否能从当前沙箱访问需现场核对，不写死端口或猜测 API。SoS 保存宿主工具结果作为追溯依据。

## 用户改变任务后的新一轮

用户明确改变范围且需要重新选型时，保留当前方案、授权和成果，在新的修订任务目录启动一次规划。新目录记录原方案路径、版本和用户变更依据；安装提案重新展示。单纯检索失败或超时不能重命名目录续搜。

## 执行边界

脚本约束经过其入口的获取和安装。Skill 无权拦截宿主直接发起的网络命令，也不能认证宿主转述的用户身份。真实验收需核查工具轨迹；绕过入口、无授权安装或来源错标均判本次失败。
