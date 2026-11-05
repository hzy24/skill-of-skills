"""Source-backed role boundaries. Evidence anchors do not prove semantic fitness."""
import re
from method_source import entry

ARTIFACT_NAMES={'xlsx','pptx','docx','pdf','spreadsheets','presentations','documents',
                'create-ppt','spreadsheet','powerpoint','excel','word'}
GENERAL_NAMES={'analyze','validate-data','data-analysis','data-analysis-report','data-analyst',
               'data-analysis-coordinator','数据分析','数据分析大师','数据分析报告助手.skill'}

def identity(raw):
    """Only identity/purpose text, never a random example buried in a manual."""
    name,body=entry(raw)
    front=re.match(r'\s*---\s*\n(.*?)\n---',raw,re.S)
    description=''
    if front:
        found=re.search(r'^description:\s*(.*?)(?=\n[^ \t\n][^\n]*:|\Z)',front.group(1),re.M|re.S)
        if found:description=found.group(1).strip()
    return '\n'.join([name or '',description[:3000],body.split('\n## ')[0][:1600]])

PROFESSIONS=r'财务|会计|报销|审计|税务|采购|供应链|库存|人力|招聘|薪酬|绩效|组织设计|管理幅度|客服|客户服务|工单|服务运营|设备|工业|制造|保修|维修|工程|法律|合同|诉讼|医疗|临床|药物|教育|教学|应急|消防|安全生产|金融|信贷|经济|营销|销售|客户成功|金融|finance|financial|accounting|expense|audit|tax|procurement|supply.chain|inventory|human.resources|recruit|payroll|workforce|hr\b|customer.service|customer.support|support.ticket|service.operation|equipment|manufactur|warranty|maintenance|engineering|legal|contract|litigation|medical|clinical|pharmac|education|teaching|emergency|fire.safety|credit|econometric|economic|marketing|sales|customer.success|软件|编程|解析器|科学|科研|研究|software|coding|parser|research|biolog|chemistr'
FUNCTIONS={
 'visualization':r'可视化|图表|仪表板|绘图|visuali[sz]|chart|dashboard|plotting',
 'statistics':r'通用(?:数据|统计|分析)|全域数据|跨领域|任意数据|general.purpose.data|any.dataset|general.data.analysis',
 'file_production':r'文档(?:格式|排版|转换)|格式转换|幻灯片制作|文件转换|document.format|file.conver|slide.design',
 'interface':r'API.connector|API.wrapper|接口封装|API.操作|API.调用工具',
}

def classify(raw,version=1):
    name,_=entry(raw);label=(name or '').split(':')[-1].lower();ident=identity(raw)
    # Namespaces and source descriptions, not installation origin or assigned role.
    artifact=label in ARTIFACT_NAMES or bool(re.fullmatch(r'(?:(?:create|edit|convert|render)-)?(?:xlsx|pptx|docx|pdf)(?:-(?:editor|creator|converter|tools?))?',label))
    general=label in GENERAL_NAMES
    if version==1:return dict(kind='artifact_tool' if artifact else 'general_analysis' if general else 'specialty_candidate',identity=ident)
    # Only stated purpose is evidence for a role; example datasets and method
    # implementation code cannot promote a charting tool to a profession.
    purpose=re.split(r'例如|比如|示例|examples?\s*[:：]|e\.g\.',ident.split('\n',1)[-1],flags=re.I)[0]
    domains=list(dict.fromkeys(m.group(0) for m in re.finditer(PROFESSIONS,purpose,re.I)))
    functions=[k for k,pattern in FUNCTIONS.items() if re.search(pattern,purpose,re.I)]
    if version>=3 and re.search(r'统计|回归|相关性|时间序列|运筹|优化求解|statistic|regression|correlation|time.series|operations.research|optimization',purpose,re.I) and 'statistics' not in functions:
        functions.append('statistics')
    broad=bool(re.search(r'全域数据|通用(?:数据|可视化|统计)|跨领域|general.purpose|arbitrary.data|any.dataset',purpose,re.I))
    kind='artifact_tool' if artifact or 'visualization' in functions and (broad or not domains) or 'file_production' in functions and not domains else 'general_analysis' if general or functions and (broad or not domains) else 'specialty_candidate' if domains else 'unclassified'
    if version>=3 and not artifact and 'statistics' in functions and (not domains or broad or kind=='artifact_tool'):kind='general_analysis'
    options=list(dict.fromkeys(v.strip()[:240] for v in re.split(r'\n|(?<=[。；.!])\s+',purpose) if len(v.strip())>=4 and not v.strip().startswith('#')))[:12]
    return dict(kind=kind,identity=ident,profile_version=3 if version>=3 else 2,professional_signals=domains,
                functions=functions,purpose_basis=purpose,purpose_options=[dict(number=i,text=v) for i,v in enumerate(options,1)])

def responsibility_issue(goal,profile,purpose=None):
    """Check functional eligibility. Semantic task fit still requires host review."""
    if profile.get('profile_version') not in (2,3):return None
    if profile.get('kind')=='unclassified':
        if not isinstance(purpose,str) or not 4<=len(purpose.strip())<=240 or purpose not in profile['identity']:
            return '用途尚未分类；核读 purpose_options 后用 --purpose 选择专业用途编号，在 reason 说明它负责的业务判断；程序自动提取原文。'
        if re.fullmatch(r'[\W\s]*(?:分析|数据分析|报告|analysis|data analysis|report)[\W\s]*',purpose,re.I):
            return '用途仅含通用动作；引用实际专业用途。'
    if profile.get('kind')=='general_analysis' and task_kind(goal)!='artifact':
        return '原文用途属于通用制图、统计或接口能力；可作为配套，不能承担本次业务核心判断。'
    return None

def task_kind(goal):
    """Artifact-only is a narrow exception; mixed requests keep a domain core."""
    business=re.search(r'分析|诊断|评估|审计|审核|风险|合理|建议|归因|财务|经营|采购|绩效|瓶颈|analy[sz]|assess|audit|diagnos|recommend|risk',goal,re.I)
    artifact=re.search(r'排版|转换|转成|转为|美化|制作|生成|设计|编辑|format|convert|style|create|edit',goal,re.I)
    target=re.search(r'pptx?|xlsx?|docx?|pdf|演示|幻灯|表格|文档|海报|图表|仪表板|presentation|spreadsheet|document|chart|dashboard',goal,re.I)
    return 'artifact' if artifact and target and not business else 'domain'

def core_issue(goal,profile,expertise,adoption=None):
    if adoption is not None:
        from method_coverage import issue
        return issue(profile,adoption)
    issue=responsibility_issue(goal,profile,(expertise or {}).get('specialty'))
    if issue:return issue
    kind=profile.get('kind')
    if kind in ('artifact_tool','general_analysis') and task_kind(goal)!='artifact':
        return '该候选提供文件制作或通用统计能力；保留为配套工具，核心委托需匹配本次领域方法。'
    if kind=='artifact_tool' and task_kind(goal)=='artifact':return None
    if kind=='general_analysis':return '本次核心工作需采用制作或领域专业方法。'
    if not isinstance(expertise,dict):return '补充核心画像：从用户需求取 request，从候选用途原文取 specialty，并说明二者怎样匹配。'
    request=expertise.get('request','');specialty=expertise.get('specialty','');reason=expertise.get('reason','')
    if not isinstance(request,str) or len(request.strip())<2 or request not in goal:return '核心画像 request 必须定位用户原始需求中的实际片段。'
    if not isinstance(specialty,str) or len(specialty.strip())<4 or specialty not in profile.get('identity',''):return '核心画像 specialty 必须来自候选名称、description 或用途开头，不能引用通用代码示例充当专业定位。'
    if not isinstance(reason,str) or not reason.strip():return '说明候选的专业定位怎样处理用户要解决的问题。'
    if re.fullmatch(r'[\s\W]*(?:数据分析|分析|报告|data analysis|report|analysis)[\s\W]*',specialty,re.I):return '画像只含通用分析或报告；选择能说明具体专业用途的原文。'
    return None

def issues(plan):
    """Rechecked by readiness and execution, including after UI edits/rebinding."""
    if plan.get('profile_policy_version')!=1:return []
    candidates={c['id']:c for c in plan.get('capability_candidates',[])};result=[]
    for need in plan.get('capability_needs',[]):
        if need.get('role')!='core' or need.get('decision',{}).get('kind')!='skill':continue
        candidate=candidates.get(need['decision'].get('candidate_id'),{})
        profile=candidate.get('source_profile')
        # A user edit invalidates the hashed review; keep the original selection
        # as provenance instead of demanding that its words occur in the new goal.
        reviewed_request=plan.get('primary_assignment',{}).get('request',plan['goal']) if plan.get('selection_review_version')==1 else plan['goal']
        if need.get('expertise',{}).get('request')==plan['goal']:reviewed_request=plan['goal']
        adoption=candidate.get('selection_assessment') if plan.get('method_coverage_version')==1 and candidate.get('selection_assessment',{}).get('coverage')=='method' else None
        issue=core_issue(reviewed_request,profile,need.get('expertise'),adoption) if isinstance(profile,dict) else '核心候选缺少来源画像，重新核对候选原文。'
        format_task=task_kind(plan['goal'])=='artifact' and profile and profile.get('kind')=='artifact_tool'
        if not issue and plan.get('discovery_scope') and not format_task and adoption is None:
            from discovery_scope import source_issue
            selected=need.get('domain_method_evidence',[])
            issue=source_issue(plan['discovery_scope'],profile['identity'],selected)
        if issue:result.append(dict(need=need['id'],reason=issue))
    from method_inputs import issues as input_issues
    result.extend(input_issues(plan))
    from selection_review import plan_issues
    result.extend(plan_issues(plan))
    from method_coverage import plan_issues as method_issues
    result.extend(method_issues(plan))
    return result
