"""Bind upstream-style claim and process review to actual submitted files."""
from pathlib import Path
import copy

ROOT=Path(__file__).resolve().parents[1]

def template(p,n,paths,records):
    return dict(result='unverified',observed_skills=[],bound_skill_names=[b['skill'] for b in n['bindings']],claims=[],check_coverage='',
                findings=[],grader=str(ROOT/'vendor/skill-creator/skills/skill-creator/agents/grader.md'),
                verification_guide=str(ROOT/'vendor/superpowers/skills/verification-before-completion/SKILL.md'),
                source_files=[m['path'] for m in p['materials'] if m['id'] in n['inputs']],
                output_files=paths,execution_records=[r['record_path'] for r in records],
                instruction='按 grader 的事实、过程、质量主张审阅方法检查实际文件。逐个成果记录关键主张及证据；对影响结论的原因解释、推断和建议逐条核对。检查原有标准是否遗漏核心结果。填写 observed_skills（只填准确技能名，已绑定名称见 bound_skill_names；方法应用说明写在 claims 的 process 项，名称中不附加说明；临时增加的技能也填准确名称）、claims、check_coverage、findings 和 result；不要仅复述执行者的完成声明。',
                claim_example=dict(artifact='输出ID',claim='成果中的具体主张',kind='fact / inference / cause / recommendation / process / quality',
                                   locator='成果位置',evidence='来源位置与核对结果；推断说明边界及替代解释',result='pass / fail / unverified'))

def validate(p,n,data,paths):
    if not isinstance(data,dict):raise ValueError('缺少实质审阅 quality；读取实际文件后填写 capture 返回的审阅表')
    if data.get('result') not in ('pass','fail','unverified'):raise ValueError('quality.result 使用 pass/fail/unverified')
    skills=data.get('observed_skills')
    if not isinstance(skills,list) or any(not isinstance(x,str) for x in skills) or len(skills)!=len(set(skills)):raise ValueError('observed_skills 需要实际采用的唯一技能名列表')
    bound={b['skill'] for b in n['bindings']}
    extra=set(skills)-bound
    annotated={x for x in extra if any(x.startswith(name+' (') or x.startswith(name+'（') or x.startswith(name+'：') for name in bound)}
    if annotated:raise ValueError('observed_skills 名称附带说明：'+', '.join(sorted(annotated))+'。这里只填写准确名称 '+', '.join(sorted(bound))+'；说明移入 claims 的 process 项。无需换绑已在本模块中的技能；实际新增技能另行登记。')
    if extra:raise ValueError('实际采用了计划外技能：'+', '.join(sorted(extra))+'；用 rebind.py --add-support 或换用能力同步方案，再提交成果')
    claims=data.get('claims')
    if not isinstance(claims,list) or any(not isinstance(c,dict) for c in claims):raise ValueError('claims 需要逐项主张及证据')
    for c in claims:
        if c.get('artifact') not in paths or c.get('kind') not in ('fact','inference','cause','recommendation','process','quality'):raise ValueError('主张引用未知成果或类型')
        if c.get('result') not in ('pass','fail','unverified') or any(not isinstance(c.get(k),str) or not c[k].strip() for k in ('claim','locator','evidence')):raise ValueError('主张需要具体内容、定位、证据和判定')
    if not isinstance(data.get('check_coverage'),str) or not data['check_coverage'].strip():raise ValueError('check_coverage 记录验收标准是否覆盖用户目标及发现的遗漏')
    findings=data.get('findings')
    if not isinstance(findings,list) or any(not isinstance(x,str) or not x.strip() for x in findings):raise ValueError('findings 记录未解决问题，无问题用空列表')
    passed=(data['result']=='pass' and not findings and set(skills)==bound and
            {c['artifact'] for c in claims}==set(paths) and all(c['result']=='pass' for c in claims))
    if data['result']=='pass' and not passed:raise ValueError('实质审阅存在未解决主张、未覆盖成果或技能使用证据，不能登记通过')
    return dict(passed=passed,review=copy.deepcopy(data))
