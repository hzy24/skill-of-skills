"""Bind upstream-style claim and process review to actual submitted files."""
from pathlib import Path
import copy

ROOT=Path(__file__).resolve().parents[1]

def template(p,n,paths,records):
    return dict(result='unverified',observed_skills=[],bound_skill_names=[b['skill'] for b in n['bindings']],findings=[],
                review_guide=str(ROOT/'references/composed-methods.md'),
                output_files=paths,execution_records=[r['record_path'] for r in records],
                instruction='核对执行记录中的实际技能与 plan 绑定是否一致；在同一审阅表的 items 中逐项检查成果是否满足 plan 标准。填写 observed_skills、未解决的计划偏差 findings 和 result。专业检查由约定技能完成，SoS 核对其交付及检查记录。无需另写主张分析、因果审查或扩展验收标准。')

def validate(p,n,data,paths):
    if not isinstance(data,dict):raise ValueError('缺少计划履约核对 quality；按执行记录填写 capture 返回的核对表')
    if data.get('result') not in ('pass','fail','unverified'):raise ValueError('quality.result 使用 pass/fail/unverified')
    skills=data.get('observed_skills')
    if not isinstance(skills,list) or any(not isinstance(x,str) for x in skills) or len(skills)!=len(set(skills)):raise ValueError('observed_skills 需要实际采用的唯一技能名列表')
    bound={b['skill'] for b in n['bindings']}
    extra=set(skills)-bound
    annotated={x for x in extra if any(x.startswith(name+' (') or x.startswith(name+'（') or x.startswith(name+'：') for name in bound)}
    if annotated:raise ValueError('observed_skills 名称附带说明：'+', '.join(sorted(annotated))+'。这里只填写准确名称 '+', '.join(sorted(bound))+'；说明写入执行日志。无需换绑已在本模块中的技能；实际新增技能另行登记。')
    if extra:raise ValueError('实际采用了计划外技能：'+', '.join(sorted(extra))+'；用 rebind.py --add-support 或换用能力同步方案，再提交成果')
    findings=data.get('findings')
    if not isinstance(findings,list) or any(not isinstance(x,str) or not x.strip() for x in findings):raise ValueError('findings 记录未解决问题，无问题用空列表')
    passed=(data['result']=='pass' and not findings and set(skills)==bound and set(paths)==set(n['outputs']))
    if data['result']=='pass' and not passed:raise ValueError('计划履约存在未解决偏差、缺失成果或技能调用不一致，不能登记通过')
    return dict(passed=passed,review=copy.deepcopy(data))
