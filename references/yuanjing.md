# 元景保存与交付

HTML 是 plan.json 的阅读器和编辑器。将唯一 plan.json 保存在当前沙箱可交付的独立任务目录；HTML 和服务状态文件同目录。

## 启动一次保存服务

通过宿主 Bash 的 run_in_background 启动：

```sh
python <skill>/scripts/plan_server.py --plan <绝对任务目录>/plan.json --html <绝对任务目录>/plan.html --meta <绝对任务目录>/.plan-server.json
```

再运行一次检查：

```sh
python <skill>/scripts/service_status.py <绝对任务目录>/.plan-server.json
```

服务持续运行，无需等待它退出。状态文件暂未出现时查看后台报错；同一计划复用已有服务，避免重复启动。检查失败只针对实际错误修复；部署、端口或浏览器连接问题查[部署与恢复](yuanjing-deployment.md)。

## 交付与准确说明状态

ready=true 表示沙箱内保存服务已就绪。plan_readiness 表示方案条件：ready_for_confirmation 可邀请确认；needs_capability 明确说明能力缺口；needs_decision 处理待定取舍；needs_review 在执行前复核最新编辑。保存服务就绪不证明专业能力或浏览器通路已经验证。

用 PresentToUser 同时交付 delivery_files 中的 plan.html 和 plan.json，核对成功回执包含两个文件。按实际 plan_readiness 向用户说明状态。HTML 默认在宿主支持的侧栏展示；实际展示和保存通路须在元景观察验证。

## 保存后使用最新方案

用户在页面点击顶部“保存修改”，服务校验版本、原子写入 JSON 并读回，成功后显示版本。失败保留页面草稿；不得宣称保存成功。用户说“按方案执行”时，重新读取 execution_plan 指向的原文件，复核变更和能力准备，再按执行协议推进。执行授权沿用真实会话；页面保存本身不启动工作。

保持 plan.json 的唯一执行入口，不另复制成其他版本；不要用普通 render 覆盖已连接的 HTML。页面删除模块会取消其独占成果和检查；仍有下游依赖时先调整关联。正常操作无需导出上传，备份用于故障恢复。状态文件含临时写入凭据，不作为附件或聊天内容交付。
