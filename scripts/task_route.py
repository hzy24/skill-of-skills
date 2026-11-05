"""Business stages are independent of the number of selected skills.

The host authors stage boundaries using the selected methods. This module checks
ownership and dependencies; it does not invent professional phases or answers.
"""
import copy
import re
from pathlib import Path


def filename(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('每个 output 填写一个独立文件名')
    value = value.strip()
    suffix = Path(value).suffix.lstrip('.').lower()
    if ('/' in value or '\\' in value or '\n' in value or
            not re.fullmatch(r'[a-z0-9]{1,12}', suffix) or
            re.search(r'\.[a-zA-Z0-9]{1,12}\s*(?:\+|、|；|;|\band\b)\s*\S+\.', value)):
        raise ValueError('每个 output 只登记一个带扩展名的文件；说明写在 question/check 中：'+value)
    return value


class RouteValidationError(ValueError):
    def __init__(self, errors):
        self.errors=errors
        super().__init__('\n'.join(e['path']+'：'+e['message'] for e in errors))


def template(state):
    """The same authoring shape as normalize, with actual candidate identifiers."""
    choices=[dict(candidate=k,name=c['name'],role='production' if c.get('registration_role')=='support' else 'core',
                  coverage=c.get('assessment',{}).get('coverage'),scope=c.get('assessment',{}).get('scope'),limits=c.get('assessment',{}).get('limits',[]),
                  purpose=c.get('assessment',{}).get('professional_purpose',c.get('source_profile',{}).get('identity','')))
             for k,c in state['candidates'].items()
             if c.get('assessment',{}).get('fit')=='suitable' or c.get('registration_role')=='support']
    core=next((c['candidate'] for c in choices if c['role']=='core'),'')
    return dict(reason='',deliver=[],stages=[dict(title='',candidate=core,question='',method='',outputs=[],checks=[],after=[])]),choices


def undeclared_files(texts,known):
    """Find explicit output filenames outside the registered files, not prose semantics."""
    pattern=r'[\w\u4e00-\u9fff][\w\u4e00-\u9fff .-]*\.(?:xlsx|xls|csv|tsv|pptx|docx|pdf|md|html|json|txt)\b'
    return sorted({m.group().strip() for value in texts for m in re.finditer(pattern,value,re.I)
                   if not any(m.group().strip().endswith(name) for name in known)})


def normalize(document, state):
    """Collect independent input errors before the atomic compiler is touched."""
    errors=[]
    def err(path,message):errors.append(dict(path=path,message=message))
    if not isinstance(document,dict):raise RouteValidationError([dict(path='route',message='需要 {reason, deliver, stages} 对象')])
    extra=set(document)-{'reason','deliver','stages'}
    if extra:err('route','删除未知字段 '+', '.join(sorted(extra))+'；使用 reason/deliver/stages')
    if not isinstance(document.get('reason'),str) or not document['reason'].strip():err('reason','说明阶段划分依据')
    rows=document.get('stages');valid_rows=[];titles=[];owners={}
    if not isinstance(rows,list) or not rows:err('stages','需要非空阶段列表');rows=[]
    for i,raw in enumerate(rows):
        path='stages['+str(i)+']'
        if not isinstance(raw,dict):err(path,'需要阶段对象');continue
        row=copy.deepcopy(raw);valid_rows.append(row)
        extra=set(row)-{'title','candidate','question','method','outputs','checks','after','role'}
        if extra:err(path,'删除未知字段 '+', '.join(sorted(extra))+'；阶段字段 title/candidate/question/method/outputs/checks/after，可选 role')
        for key in ('title','candidate','question','method'):
            if not isinstance(row.get(key),str) or not row[key].strip():err(path+'.'+key,'填写非空文本')
            else:row[key]=row[key].strip()
        title=row.get('title')
        if isinstance(title,str) and title:
            if title in titles:err(path+'.title','阶段标题重复：'+title)
            titles.append(title)
        candidate=row.get('candidate');c=state['candidates'].get(candidate,{}) if isinstance(candidate,str) else {}
        if not c:err(path+'.candidate','使用已核读候选编号：'+', '.join(state['candidates']))
        elif row.setdefault('role', 'production' if c.get('registration_role')=='support' else 'core')!='production' and c.get('assessment',{}).get('fit')!='suitable':err(path+'.candidate','该候选尚未 assess suitable')
        for key in ('outputs','checks'):
            value=row.get(key)
            # A single explicit text has exactly one meaning; no splitting or guessing.
            if isinstance(value,str) and value.strip():row[key]=value=[value.strip()]
            if not isinstance(value,list) or not value or any(not isinstance(v,str) or not v.strip() for v in value):
                err(path+'.'+key,'使用非空文本列表');continue
            row[key]=[v.strip() for v in value]
            if key=='outputs':
                for j,v in enumerate(row[key]):
                    try:filename(v)
                    except ValueError as e:err(path+'.outputs['+str(j)+']',str(e))
                    if v in owners:err(path+'.outputs','每个成果文件只由一个阶段负责：'+v)
                    owners[v]=i
        after=row.setdefault('after',[])
        if not isinstance(after,list) or any(not isinstance(v,str) for v in after):err(path+'.after','使用上游阶段标题列表；独立阶段用 []')
        elif len(set(after))!=len(after):err(path+'.after','上游阶段重复')
        role=row.setdefault('role','core')
        if role not in ('core','production'):err(path+'.role','使用 core 或 production')
        if role=='production' and (not after or c.get('registration_role')!='support' or c.get('source_profile',{}).get('kind')!='artifact_tool' or c.get('assessment',{}).get('fit')=='unsuitable'):
            err(path+'.role','制作阶段需要上游成果及 local --role support 登记的制作能力')
        if role=='core' and c.get('assessment',{}).get('fit')=='suitable':
            from capability_profile import core_issue
            a=c['assessment'];profile=c['source_profile']
            problem=core_issue(state['goal'],profile,dict(request=state['goal'],specialty=a.get('professional_purpose',profile['identity']),reason=a['reason']),
                               a if a.get('coverage')=='method' else None)
            if problem:err(path+'.candidate',problem)
    for i,raw in enumerate(rows):
        if not isinstance(raw,dict):continue
        after=raw.get('after',[])
        if isinstance(after,list) and all(isinstance(v,str) for v in after):
            for title in after:
                if title not in titles or title==raw.get('title'):err('stages['+str(i)+'].after','引用其他真实阶段标题；可选：'+', '.join(titles))
    deliver=document.get('deliver')
    if not isinstance(deliver,list) or not deliver or any(not isinstance(v,str) or v not in owners for v in deliver):err('deliver','列出最终交付文件名，引用阶段 outputs：'+', '.join(owners))
    if state.get('authoring_contract',0)>=11:
        known=list(owners)+[Path(m['path']).name for m in state.get('inputs',[])]+['SKILL.md']
        for i,row in enumerate(valid_rows):
            mentions=[row[k] for k in ('question','method') if isinstance(row.get(k),str)]
            mentions+=row.get('checks',[]) if isinstance(row.get('checks'),list) and all(isinstance(x,str) for x in row['checks']) else []
            for name in undeclared_files(mentions,known):err('stages['+str(i)+']','说明引用未登记文件 '+name+'；将实际成果列入 outputs，或与登记文件名保持一致')
    if errors:raise RouteValidationError(errors)
    normalized=copy.deepcopy(document);normalized['stages']=valid_rows
    try:return _normalize_valid(normalized,state)
    except ValueError as e:raise RouteValidationError([dict(path='stages',message=str(e))]) from e


def _normalize_valid(document, state):
    """Order validated stages and check graph-wide invariants once."""
    rows=document['stages']
    if not any(r['role']=='core' for r in rows):raise ValueError('路线至少包含一个专业核心阶段')
    scopes=[(r['candidate'],r['question'],r['method'],tuple(sorted(r['after']))) for r in rows]
    if len(set(scopes))!=len(scopes):raise ValueError('阶段的问题、方法和前置完全相同；合并成果或说明各自范围')
    deliver=document['deliver']
    ordered=[];remaining=list(rows)
    while remaining:
        ready=[r for r in remaining if set(r['after'])<={v['title'] for v in ordered}]
        if not ready:raise ValueError('阶段依赖形成循环；保留原草案，修正 after')
        ordered.extend(ready)
        remaining=[r for r in remaining if r not in ready]
    return dict(reason=document['reason'].strip(),deliver=list(dict.fromkeys(deliver)),stages=ordered)


def apply(plan, route):
    """Attach the authored method scope; reuse each skill's existing candidate."""
    plan['task_route_version']=1
    plan['task_route']=dict(reason=route['reason'],verification='host_authored_boundaries')
    by_title={r['title']:r for r in route['stages']}
    for node in plan['nodes']:
        row=by_title.get(node['title'])
        if row:
            node['stage_method']=row['method']
            for oid in node.get('outline_ids',[]):
                outline=next(x for x in plan['content_outline'] if x['id']==oid)
                outline['visual']=row['method']
        else:
            node['stage_method']=node['reason']  # produce --takeover appended after route
    extra_outputs={o for n in plan['nodes'] if n['title'] not in by_title for o in n['outputs']}
    for d in plan['deliverables']:
        d['delivery_role']='final' if d['title'] in route['deliver'] or d['id'] in extra_outputs else 'intermediate'
    sync(plan)


PRODUCTION_SCOPE='将本模块专业技能的已完成结果制作成约定文件，沿用其判断、数字与依据。'


def binding_scope(plan,node,binding):
    """One source of truth for full-stage work and in-stage file production."""
    contract=binding.get('contract',{})
    if contract.get('production_from_need'):
        c=next((c for c in plan['capability_candidates'] if c['id']==binding['candidate_id']),{})
        outputs=contract.get('outputs',[])
        return dict(scope=PRODUCTION_SCOPE,inputs=[c.get('method_support',{}).get('material_id')],outputs=outputs,
                    required_checks=[copy.deepcopy(x) for x in node['checks'] if x.get('artifact') in outputs])
    return dict(scope=node['description'],inputs=list(node['inputs']),outputs=list(node['outputs']),required_checks=copy.deepcopy(node['checks']))


def sync(plan):
    """Rebuild stage contracts from the edited nodes, never a stale route copy."""
    if plan.get('task_route_version')!=1:return
    for node in plan['nodes']:
        for binding in node['bindings']:
            contract=binding.get('contract')
            if not contract:continue
            fields=binding_scope(plan,node,binding);binding['scope']=fields.pop('scope')
            contract.update(fields)
            contract['invocation']='使用 '+binding['skill']+'：'+binding['scope']
            if not contract.get('production_from_need'):contract['invocation']+='。方法应用：'+node.get('stage_method','')
            contract['invocation']+='。沿用已核验的原文和上游结果，按本阶段范围产出并检查；后续阶段按依赖推进。'
            candidate=next((c for c in plan['capability_candidates'] if c['id']==binding['candidate_id']),{})
            assessment=candidate.get('selection_assessment',{})
            if plan.get('method_coverage_version')==1 and assessment.get('coverage')=='method':
                from method_coverage import disclosure
                contract['invocation']+=' '+disclosure(candidate['name'],assessment)
    primary=plan.get('primary_assignment')
    if primary and primary.get('node') not in {n['id'] for n in plan['nodes']}:
        core={n['id'] for n in plan.get('capability_needs',[]) if n.get('role')=='core'}
        primary['node']=next((n['id'] for n in plan['nodes'] if core.intersection(n.get('capability_need_ids',[]))),None)


def reconcile_edits(before, after):
    """One editable stage scope drives requirements, handoffs and execution."""
    if after.get('stage_review_version')==1:
        old_outputs={d['id']:d for d in before['deliverables']}
        renames={old_outputs[d['id']]['title']:d['title'] for d in after['deliverables']
                 if d['id'] in old_outputs and d['title']!=old_outputs[d['id']]['title']}
        input_names={Path(m['path']).name for m in before['materials']}
        renames={k:v for k,v in renames.items() if k not in input_names}
        if renames:
            # Match registered names longest-first; do not rewrite source quotations.
            names={d['title'] for d in before['deliverables']}|{Path(m['path']).name for m in before['materials']}
            pattern=re.compile('|'.join(re.escape(v) for v in sorted(names,key=len,reverse=True)))
            def renamed(v):return pattern.sub(lambda m:renames.get(m.group(),m.group()),v)
            for n in after['nodes']:
                for key in ('description','reason','stage_method'):
                    if key in n:n[key]=renamed(n[key])
                n['done_when']=[renamed(v) for v in n['done_when']]
                for binding in n['bindings']:
                    if 'reason' in binding:binding['reason']=renamed(binding['reason'])
                for check in n['checks']:
                    if 'criteria' in check:check['criteria']=renamed(check['criteria'])
            for d in after['deliverables']:
                prior=old_outputs.get(d['id'])
                if prior and d['title']!=prior['title'] and d['format']==prior['format']:d['format']=Path(d['title']).suffix.lstrip('.').lower()
    prior={n['id']:n for n in before['nodes']}
    producers={o:n['id'] for n in before['nodes']+after['nodes'] for o in n['outputs']}
    for node in after['nodes']:
        old=prior.get(node['id'],{})
        if not old:
            # The editor may reuse an existing selection, not author new evidence.
            bindings=node.get('bindings',[]);ids=node.get('capability_need_ids',[])
            if len(bindings)!=1 or len(ids)!=1 or any(x['id']==ids[0] for x in after['capability_needs']):
                raise ValueError('新增阶段需复用一个已选技能，并使用独立的能力分工编号')
            binding=bindings[0]
            source=next((n for n in before['nodes'] if any(
                b.get('candidate_id')==binding.get('candidate_id') and b['skill']==binding['skill']
                for b in n['bindings'])),None)
            need=next((x for x in before['capability_needs'] if source and
                x['id'] in source.get('capability_need_ids',[]) and
                x.get('decision',{}).get('candidate_id')==binding.get('candidate_id')),None)
            if not need:raise ValueError('新增阶段需复用方案中已选定的技能；新的技能请在对话中选型')
            need=copy.deepcopy(need)
            need.update(id=ids[0],requirement_ids=list(node['requirements']),outline_ids=list(node.get('outline_ids',[])))
            after['capability_needs'].append(need)
            binding=copy.deepcopy(next(b for b in source['bindings'] if b.get('candidate_id')==binding.get('candidate_id') and b['skill']==binding['skill']))
            node['bindings']=[binding]
            binding['readiness']='unknown'
            if binding.get('contract'):binding['contract'].pop('verification',None)
        # Changing prerequisite checkboxes also changes upstream input references.
        if old and node['depends_on']!=old['depends_on']:
            upstream=[o for n in after['nodes'] if n['id'] in node['depends_on'] for o in n['outputs']]
            node['inputs']=list(dict.fromkeys([i for i in node['inputs'] if i not in producers]+upstream))
        outlines=[o for o in after.get('content_outline',[]) if o['id'] in node.get('outline_ids',[])]
        if len(outlines)==1:
            outline=outlines[0];prev=next((o for o in before.get('content_outline',[]) if o['id']==outline['id']),{})
            if old and node['description']==old['description'] and outline.get('claim')!=prev.get('claim'):
                node['description']=outline['claim']
            outline.update(title=node['title'],claim=node['description'],points=[node['description']],
                           visual=node.get('stage_method',''),sources=list(node['inputs']),acceptance=list(node['done_when']))
        if node['done_when']!=old.get('done_when'):
            for check in node['checks']:
                if check['kind']=='review':check['criteria']='；'.join(node['done_when'])
        for requirement in after['requirements']:
            if requirement['id'] in node['requirements']:requirement['text']=node['description']
        for d in after['deliverables']:
            if d['id'] in node['outputs']:d['description']=node['description']
        for need in after.get('capability_needs',[]):
            if need['id'] in node.get('capability_need_ids',[]):
                internal=any(b.get('contract',{}).get('production_from_need') and b['candidate_id']==need.get('decision',{}).get('candidate_id') for b in node['bindings'])
                scope=PRODUCTION_SCOPE if internal else node['description']
                need['standard']=scope;need['decision']['application']=scope


def issues(plan):
    if plan.get('task_route_version')!=1:return []
    errors=[]
    if plan.get('stage_review_version')==1:
        known=[d['title'] for d in plan['deliverables']]+[Path(m['path']).name for m in plan['materials']]
        for n in plan['nodes']:
            for name in undeclared_files([n.get('description',''),n.get('stage_method','')]+n.get('done_when',[]),known):errors.append(n['id']+' 引用未登记文件：'+name)
    if not isinstance(plan.get('task_route',{}).get('reason'),str) or not plan['task_route']['reason'].strip():errors.append('任务路线缺少划分依据')
    for node in plan['nodes']:
        if not isinstance(node.get('stage_method'),str) or not node['stage_method'].strip():errors.append(node['id']+' 缺少阶段方法应用')
        for b in node['bindings']:
            expected=binding_scope(plan,node,b)
            if b.get('scope')!=expected['scope']:errors.append(node['id']+' 阶段与技能委托范围不一致')
            c=b.get('contract')
            if c and any(c.get(k)!=expected[k] for k in ('inputs','outputs','required_checks')):
                errors.append(node['id']+' 阶段交接与执行约定不一致')
            if c and c.get('production_from_need') and (not c.get('outputs') or not set(c['outputs'])<=set(node['outputs'])):
                errors.append(node['id']+' 辅助制作需负责本阶段的实际成果')
    scopes=[(tuple(b.get('candidate_id') for b in n['bindings']),n['description'],n.get('stage_method'),tuple(sorted(n['depends_on']))) for n in plan['nodes']]
    if len(set(scopes))!=len(scopes):errors.append('阶段的问题、方法和前置完全相同；合并成果或说明各自范围')
    if not any(d.get('delivery_role')=='final' for d in plan['deliverables']):errors.append('请保留至少一个最终交付文件')
    titles=[d['title'] for d in plan['deliverables']]
    if len(set(titles))!=len(titles):errors.append('不同阶段不能覆盖同名成果文件')
    for d in plan['deliverables']:
        if d.get('delivery_role') not in ('intermediate','final'):errors.append('成果需声明阶段结果或最终交付')
        try:filename(d['title'])
        except ValueError as e:errors.append(str(e))
    return errors
