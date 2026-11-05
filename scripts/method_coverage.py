"""Bounded adoption of transferable methods, with source and scope provenance.

These checks establish a reviewable delegation, not the semantic truth of the
host's fit judgment. Stages and domain conclusions still require actual review.
"""
import copy

def gate(state,chosen=None):
    searches=[x for x in state.get('search_history',[]) if x.get('level') in ('task','domain') and x.get('success')]
    if not searches:return '先完成本任务的业务或领域检索，再比较可迁移的方法；网络故障不代表已完成比较。'
    peers={k:v for k,v in state.get('candidates',{}).items() if k!=chosen and v.get('registration_role','core')=='core'}
    if any(not c.get('assessment') for c in peers.values()):return '先记录已核读业务候选的取舍，再比较通用方法。'
    recalled={slug for x in searches for slug in x.get('slugs',[])}
    if recalled and not peers:return '业务检索已有候选，先核读最相关候选并说明实际方法覆盖；无需为数量额外陪选。'
    return None

def evidence(state,chosen):
    return dict(specific_searches=copy.deepcopy([x for x in state.get('search_history',[]) if x.get('level') in ('task','domain') and x.get('success')]),
        compared_candidates=[dict(candidate=k,name=c['name'],fit=c['assessment']['fit'],reason=c['assessment']['reason'])
            for k,c in state.get('candidates',{}).items() if k!=chosen and c.get('registration_role','core')=='core' and c.get('assessment')])

def issue(profile,assessment):
    if profile.get('kind')=='artifact_tool':return '文件制作或纯制图技能保留制作职责；选择提供实际分析方法的 Skill。'
    if profile.get('functions')==['interface']:return '接口操作本身未提供分析方法；核读实际方法能力。'
    if not isinstance(assessment,dict) or assessment.get('coverage')!='method':return '通用方法承担核心工作时使用 --coverage method，登记负责范围与判断边界。'
    if not isinstance(assessment.get('scope'),str) or not assessment['scope'].strip():return '用 --scope 说明该方法实际负责的问题与结果。'
    if not assessment.get('methods'):return '用 --method 选择实际承担任务的方法章节。'
    limits=assessment.get('limits')
    if not isinstance(limits,list) or not limits or any(not isinstance(v,str) or not v.strip() for v in limits):return '用 --limit 说明未覆盖的业务判断及处理方式；无需额外判断时说明适用范围。'
    return None

def disclosure(name,assessment):
    return '方法选型（'+name+'）：'+assessment['scope']+'；选择依据：'+assessment['reason']+'；判断边界与处理：'+'；'.join(assessment['limits'])

def plan_issues(plan):
    if plan.get('method_coverage_version')!=1:return []
    result=[]
    for c in plan.get('capability_candidates',[]):
        a=c.get('selection_assessment',{})
        if a.get('coverage')!='method':continue
        reason=issue(c.get('source_profile',{}),a)
        if not reason:
            searches=a.get('specific_searches',[])
            if not searches or any(not x.get('success') for x in searches):reason='方法选型缺少本任务的成功检索记录。'
            elif any(x.get('slugs') for x in searches) and not a.get('compared_candidates'):reason='方法选型缺少已核读业务候选的比较依据。'
            elif disclosure(c['name'],a) not in plan.get('constraints',[]):reason='方案需保留方法选择、负责范围和判断边界。'
        if reason:result.append(dict(need=c['id'],reason=reason))
    return result
