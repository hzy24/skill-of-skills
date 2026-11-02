# 专业 Skill 的原生验证

适用 Skill 提供测试、审计、重算或检查脚本时读取。先阅读命令说明，确认适用条件、实际覆盖范围和任务授权。宿主显式运行该命令；计划校验、HTML 保存和 finish 均不执行计划中的命令。Skill of Skills 使用标准库捕获结果，不预设行业验证器。

在负责节点的 checks 中加入：

```json
{
  "kind": "native",
  "id": "repair-regression",
  "artifact": "fixed_source",
  "criteria": "空输入返回空列表，原有整数和负数解析保持一致，三个测试实际执行并通过",
  "source": "所选 Skill 的准确版本与测试说明位置",
  "cwd": "/absolute/task",
  "argv": ["python3", "check_parser.py", "fixed_parser.py"],
  "evidence": "regression_receipt"
}
```

artifact 与 evidence 是本节点不同的输出 ID。为 evidence 配置 file 检查，把这条 native 检查同步纳入绑定 contract.required_checks。cwd 指定已核对的实际工作目录，argv 使用参数数组，不经 shell；命令及工作目录改变后更新方案并复核受影响范围。解释器和脚本路径以当前宿主为准。

实际完成修改后，在任务目录执行：

```
python <skill>/scripts/capture_check.py --artifact /absolute/task/fixed_parser.py --check-id repair-regression --source '所选 Skill 的准确版本与测试说明位置' --cwd /absolute/task --out /absolute/task/regression.json -- python3 check_parser.py fixed_parser.py
```

命令参数须与当前方案一致。--artifact 与 --out 相对路径基于调用本脚本的目录；建议传绝对路径。--cwd 只指定验证子进程目录。验证器及依赖输入保留可追溯版本，作为节点材料记录；从外部页面取得的命令先阅读核对。

脚本将退出码、stdout、stderr、命令、目录、开始时间与目标文件前后 SHA256 写入 JSON。超时、非零退出、无法执行或验证期间目标被修改均不通过。会重算或改写成果的工具先运行，稳定后再检查最终版本。

execute.py open 生成的 receipt.outputs 同时登记实际目标与验证记录路径。capture 核对检查 ID、来源标识、命令、目录和目标版本；audit 对两份输出继续校验哈希。多份文件可逐项检查，或先形成固定归档并以归档为目标验证；本机制不对未登记目录树自动提供版本保证。

仍需读取日志确认实际检查的对象、数量和范围。退出码为 0、空测试集或一句“通过”均不足以说明用户需求满足；通过 review 记录与本任务相符的行为、专业判断及证据。记录来自宿主执行，不提供独立签名或身份认证。没有可执行验证器时直接采用明确的 review 标准，无需制造占位命令。
