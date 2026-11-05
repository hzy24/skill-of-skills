"""Persist the host's semantic selection separately from source verification.

Python verifies identity, ownership and provenance. The host judges applicability
from the request and source; neither keywords nor a source hash prove that fit.
"""
import hashlib,re
from pathlib import Path
from method_source import entry,sections

def domain_gate(state,chosen=None):
    """A broader domain method is a reviewed choice, never a budget fallback."""
    searches=[x for x in state.get('search_history',[]) if x.get('level')=='task' and x.get('success')]
    if not searches:return '先完成针对具体业务问题的成功检索'
    peers=[v for k,v in state.get('candidates',{}).items() if k!=chosen and v.get('registration_role','core')=='core']
    if any(v.get('assessment',{}).get('fit')=='suitable' and v['assessment'].get('coverage','task')=='task' for v in peers):
        return '已有直接契合的任务方法，优先保留该方法；领域通用技能不能替换它'
    if any(not v.get('assessment') for v in peers):return '先记录已核读任务候选的适配判断'
    rejected=[v for v in peers if v.get('assessment',{}).get('fit')=='unsuitable']
    recalled={slug for x in searches for slug in x.get('slugs',[])}
    required=min(2,len(recalled))
    if not rejected and recalled:
        return '具体任务检索有候选，先核读并比较；下载失败和预算耗尽不等于方法不适合'
    if len(rejected)<required:
        return '仍有具体任务候选可比较；采用领域通用方法前至少完成 '+str(required)+' 项实际方法取舍'
    return None

def catalog(candidate):
    paths=[('',candidate['method_file'],candidate['sha256'])]
    paths.extend((name+'::',r['file'],r['sha256']) for name,r in candidate.get('resources',{}).items())
    result=[]
    for prefix,path,digest in paths:
        raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('已核读的方法来源发生变化')
        body=raw.decode('utf-8') if prefix else entry(raw.decode('utf-8'))[1]
        result.extend(dict(ref=prefix+s['id'],title=prefix+s['title'],text=s['text']) for s in sections(body))
    return result

class MethodChoiceError(ValueError):
    def __init__(self,message,choices):
        super().__init__(message);self.choices=choices

def method_choices(candidate):
    return [dict(number=i,ref=r['ref'],title=r['title'],preview=r['text'][:160])
            for i,r in enumerate(catalog(candidate),1)]

def resolve_methods(rows,methods):
    """Resolve only exact, unambiguous references, including joined title lists."""
    selected=[]
    def find(ref):
        exact=[r for r in rows if ref in (r['ref'],r['title'])]
        if len(exact)==1:return exact[0]['ref']
        if not exact and ref.isdecimal() and 1<=int(ref)<=len(rows):return rows[int(ref)-1]['ref']
    for ref in methods:
        ref=str(ref).strip();found=find(ref)
        if found:selected.append(found);continue
        parts=re.split(r'\s*[,，、;；\n]\s*|\s+/\s+|\s*\|\s*',ref)
        resolved=[find(x.strip()) for x in parts]
        if len(parts)>1 and all(resolved):selected.extend(resolved);continue
        raise MethodChoiceError('未能唯一定位方法：'+ref,
            [dict(number=i,ref=r['ref'],title=r['title']) for i,r in enumerate(rows,1)])
    return list(dict.fromkeys(selected))

def assess(candidate,goal,fit,reason,methods=(),limits=(),whole_default=False):
    if fit not in ('suitable','unsuitable'):raise ValueError('fit 使用 suitable 或 unsuitable')
    if not isinstance(reason,str) or not reason.strip():raise ValueError('说明专业方法与原始需求的关系')
    old=candidate.get('assessment',{})
    if old.get('fit')=='unsuitable' and fit=='suitable':
        raise ValueError('已淘汰的候选本轮不能重新入选；继续选择其他专业方法')
    rows=catalog(candidate);selected=[]
    mode='selected_sections'
    if whole_default and fit=='unsuitable':
        # Rejecting a candidate does not need a method locator.
        selected=[];mode='rejected'
    elif whole_default and not methods:
        from assignment import source_refs
        selected=source_refs(candidate,[goal]);mode='full_workflow'
        if not selected:raise ValueError('原文没有可引用的方法内容')
    elif whole_default:
        selected=resolve_methods(rows,methods)
        if len(selected)>3:raise MethodChoiceError('局部委托最多选三个章节；完整委托省略 --method',method_choices(candidate))
    else:
        if len(set(methods))>3:raise ValueError('选型依据最多三个实际方法章节；细节由专业 Skill 执行')
        for ref in dict.fromkeys(methods):
            found=[r for r in rows if ref in (r['ref'],r['title'])]
            if len(found)!=1:raise ValueError('方法使用核读结果中的章节编号或唯一标题：'+str(ref))
            selected.append(found[0]['ref'])
    if fit=='suitable' and not selected:raise ValueError('选择实际承担原始需求的方法；完整委托省略章节参数')
    return dict(fit=fit,reason=reason.strip(),request=goal,methods=selected,limits=list(limits),
                method_selection=mode,source_sha256=candidate['sha256'],judged_by='host',verification='source_and_ownership_only')

def plan_issues(plan):
    if plan.get('selection_review_version')!=1:return []
    issues=[]
    primary=plan.get('primary_assignment',{})
    nodes={n['id']:n for n in plan.get('nodes',[])}
    owner=nodes.get(primary.get('node'))
    needs={n['id']:n for n in plan.get('capability_needs',[])}
    if not owner or not primary.get('request') or not any(needs.get(i,{}).get('role')=='core' for i in owner.get('capability_need_ids',[])):
        issues.append(dict(need='primary',reason='原始需求必须保留一个专业核心负责模块'))
    candidates={c['id']:c for c in plan.get('capability_candidates',[])}
    for need in needs.values():
        c=candidates.get(need.get('decision',{}).get('candidate_id'),{})
        if need.get('role')=='core':
            a=c.get('selection_assessment',{})
            if a.get('fit')!='suitable' or a.get('judged_by')!='host' or a.get('request') not in (plan.get('goal'),primary.get('request')) or not a.get('methods') or a.get('source_sha256')!=c.get('method_support',{}).get('sha256'):
                issues.append(dict(need=need['id'],reason='核心候选需要针对原始需求的选型判断和实际方法来源'))
            if plan.get('selection_policy_version')==2:
                allowed=('task','domain','method') if plan.get('method_coverage_version')==1 else ('task','domain')
                if a.get('coverage') not in allowed:
                    issues.append(dict(need=need['id'],reason='核心选型需声明任务专用或领域方法覆盖'))
                elif a['coverage']=='domain':
                    searches=a.get('specific_searches',[])
                    required=min(2,len({slug for x in searches for slug in x.get('slugs',[])}))
                    if not searches or len(a.get('compared_candidates',[]))<required:
                        issues.append(dict(need=need['id'],reason='领域方法需要保留具体任务检索与候选比较证据'))
        elif need.get('role')=='support':
            node=next((n for n in nodes.values() if need['id'] in n.get('capability_need_ids',[])),{})
            upstream=[n for n in nodes.values() if set(n.get('outputs',[]))&set(node.get('inputs',[]))]
            binding=next((b for b in node.get('bindings',[]) if b.get('candidate_id')==c.get('id')),{})
            internal=binding.get('contract',{}).get('production_from_need')
            internal_core=bool(internal in node.get('capability_need_ids',[]) and needs.get(internal,{}).get('role')=='core')
            if c.get('source_profile',{}).get('kind')!='artifact_tool' or not (upstream or internal_core):
                issues.append(dict(need=need['id'],reason='制作配套使用真实制作技能，并接收上游专业成果'))
            raw={m['id'] for m in plan.get('materials',[]) if m['id'].startswith('M') and not m['id'].startswith('MR')}
            production_inputs=binding.get('contract',{}).get('inputs',[]) if internal_core else node.get('inputs',[])
            if raw&set(production_inputs):
                issues.append(dict(need=need['id'],reason='制作配套应使用上游成果；原始业务材料由专业模块负责'))
    return issues
