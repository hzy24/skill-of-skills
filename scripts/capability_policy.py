"""Skills-first evidence requirements; records do not certify method quality."""
def text(x):return isinstance(x,str) and bool(x.strip())

def specialist_errors(p, node=None):
    """A missing specialist stays visible; installation permission is not fallback consent."""
    errors=[]
    candidates={c['id']:c for c in p.get('capability_candidates',[])}
    materials={m['id']:m for m in p.get('materials',[])}
    for need in p.get('capability_needs',[]):
        if need.get('task_kind')!='professional' and not (p.get('capability_policy_version')==3 and
            (need.get('task_kind')=='production' or need.get('decision',{}).get('kind')=='skill')):continue
        if node and need['id'] not in node.get('capability_need_ids',[]):continue
        d=need.get('decision',{});label=need['id']
        if d.get('kind')=='direct':
            errors.append(label+' 专业模块必须采用 Skill；未选到时保留 deferred。fallback_authorization 不再允许专业原生降级')
        elif d.get('kind') in ('skill','reference') and d.get('fit')=='supported':
            c=candidates.get(d.get('candidate_id'),{});support=c.get('method_support',{})
            if not isinstance(support,dict):support={}
            source=materials.get(support.get('material_id'))
            if not source or not all(text(support.get(k)) for k in ('workflow','checks')):
                errors.append(label+' 专业适配需要 method_support：material_id 指向已读取的技能/方法原文，workflow 与 checks 写明实际流程和检查；榜单摘要、库可用性和文件制作能力不足以支持选择')
            elif node and support['material_id'] not in node.get('inputs',[]):
                errors.append(node['id']+' 缺少专业方法原文输入：'+support['material_id'])
            if p.get('method_evidence_version')==1 and need.get('role')=='core':
                ev=need.get('method_evidence',{})
                if not isinstance(ev,dict) or not text(ev.get('excerpt')) or ev.get('material_id')!=support.get('material_id') or not ev.get('source_sha256') or ev.get('source_sha256')!=support.get('sha256'):
                    errors.append(label+' 核心方法需要关联原文片段及来源版本；仅文件制作、依赖可用或自述适配不足以通过')
    return errors

def core_needs(p):
    return [n for n in p.get('capability_needs',[]) if n.get('role')=='core' or
            ('role' not in n and n.get('task_kind')=='professional')]

def require_core_skill(p):
    """Whole-plan gate: a file-production skill cannot cover an unresolved core."""
    if p.get('capability_policy_version')!=3:return
    core=core_needs(p)
    if not core or not any(n.get('decision',{}).get('kind')=='skill' and n['decision'].get('fit')=='supported' for n in core):
        raise ValueError('核心业务尚无已选定的专业 Skill；先解决能力缺口，再执行方案')
    if any(n.get('decision',{}).get('kind')!='skill' or n['decision'].get('fit')!='supported' for n in core):
        raise ValueError('仍有核心业务能力缺口；文件制作技能不能替代核心任务的专业方法')

def validate_policy(p):
    policy=p.get('capability_policy')
    if policy is None:return [],['旧方案尚未采用专业能力优先规则；执行前复核选型'] if p.get('selection_contract_version') else []
    if policy!='skills_first':return ['capability_policy 需要为 skills_first'],[]
    raw=p.get('capability_candidates',[])
    if not isinstance(raw,list):return ['capability_candidates 需要列表'],[]
    errors=[];candidates={c['id'] for c in raw if isinstance(c,dict) and isinstance(c.get('id'),str)}
    if 'method_evidence_version' in p and (type(p['method_evidence_version']) is not int or p['method_evidence_version']!=1):errors.append('method_evidence_version 需要整数 1')
    needs=p.get('capability_needs',[])
    if not isinstance(needs,list):return ['capability_needs 需要列表'],[]
    for need in needs:
        if not isinstance(need,dict):continue
        kind=need.get('task_kind');label=str(need.get('id','能力需求'))
        if kind not in ('basic','professional','production'):errors.append(label+' 需要 task_kind：basic / professional / production');continue
        d=need.get('decision',{})
        if not isinstance(d,dict):continue
        if kind!='basic' and d.get('kind')=='direct' and p.get('capability_policy_version')!=3:
            basis=d.get('direct_basis',{})
            if not isinstance(basis,dict):basis={}
            if any(not text(basis.get(k)) for k in ('reason','coverage','limitations')):errors.append(label+' 专业原生处理需要 direct_basis 的 reason、coverage、limitations')
            refs=basis.get('candidate_ids')
            if not isinstance(refs,list) or any(not isinstance(x,str) or x not in candidates for x in refs):errors.append(label+' direct_basis.candidate_ids 需要引用实际评估候选')
            if not refs:
                discovery=need.get('discovery',{})
                if not isinstance(discovery,dict) or discovery.get('status') not in ('searched','unavailable','not_authorized') or not text(discovery.get('evidence')):errors.append(label+' 无候选时需要检索结果或实际访问限制')
        if kind!='basic':
            for n in p.get('nodes',[]):
                if label not in n.get('capability_need_ids',[]):continue
                checked={c.get('artifact') for c in n.get('checks',[]) if isinstance(c,dict) and c.get('kind') in ('review','native') and text(c.get('criteria'))}
                receipts={c.get('evidence') for c in n.get('checks',[]) if isinstance(c,dict) and c.get('kind')=='native' and c.get('artifact') in checked}
                if set(n.get('outputs',[]))-checked-receipts:errors.append(n['id']+' 专业或成品任务的每项输出需要 review 或 native 实质验收')
    version=p.get('capability_policy_version')
    if version is not None and (type(version) is not int or version not in (2,3)):errors.append('capability_policy_version 需要为 2 或 3；新方案采用 3')
    if version==3:
        for need in needs:
            d=need.get('decision',{})
            if 'fallback_authorization' in d:errors.append(need['id']+' 不接受 fallback_authorization；采用 Skill 或保留能力缺口')
            if need.get('task_kind')!='basic' and d.get('kind') in ('direct','reference'):
                errors.append(need['id']+' 专业与成果模块需要实际采用 Skill，未落实时使用 deferred')
        if not core_needs(p):
            return errors,['当前方案缺少核心专业委托，执行将被阻止']
    if not errors and version in (2,3):
        errors.extend(specialist_errors(p))
        for node in p.get('nodes',[]):
            errors.extend(e for e in specialist_errors(p,node) if e not in errors)
    return errors,[]

def validate_depth(p):
    """New-plan minimum: professional scope must expose editable work content.

    Specificity and source truth still need substantive review by the host.
    Legacy saved plans remain readable through normal validate.
    """
    errors=[]
    for need in p.get('capability_needs',[]):
        if need.get('task_kind') in ('professional','production') and not need.get('outline_ids'):
            errors.append(need['id']+' 专业任务需要至少一个具体内容项：问题、章节、功能或页面，并填写 outline_ids')
    return errors
