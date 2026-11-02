"""Evidence-based selection contract. Validates records, never certifies skill quality."""
def text(v): return isinstance(v, str) and bool(v.strip())
def validate_selection(p):
    if 'selection_contract_version' not in p: return [], []
    if type(p['selection_contract_version']) is not int or p['selection_contract_version'] != 1:
        return ['selection_contract_version 需要为 1'], []
    errors, warnings = [], []
    needs, candidates = p.get('capability_needs'), p.get('capability_candidates', [])
    if not isinstance(needs, list) or not needs or any(not isinstance(x, dict) for x in needs):
        return ['capability_needs 需要非空对象列表'], []
    if not isinstance(candidates, list) or any(not isinstance(x, dict) for x in candidates):
        return ['capability_candidates 需要对象列表'], []
    for values, label in ((needs, '能力需求'), (candidates, '候选')):
        ids = [x.get('id') for x in values]
        if any(not text(i) for i in ids) or len(set(i for i in ids if isinstance(i,str))) != len(ids):
            errors.append(label + ' id 必须唯一且非空')
    if errors: return errors, warnings
    byid = {c['id']: c for c in candidates}
    known = {n['id'] for n in needs}
    outlines = {x['id'] for x in p.get('content_outline', [])}
    requirements = {x['id'] for x in p.get('requirements', [])}
    pending = p.get('selection_needs_review') is True
    if pending and 'selection_review_nodes' in p:
        refs=p['selection_review_nodes'];known_nodes={n['id'] for n in p['nodes']}
        if not refs or any(x not in known_nodes for x in refs):errors.append('待复核选择需要有效的 selection_review_nodes')
    for c in candidates:
        label = '候选 ' + c['id']
        for k in ('name', 'source', 'version', 'license'):
            if not text(c.get(k)): errors.append(label + ' 缺少 ' + k)
        ev = c.get('evidence')
        if not isinstance(ev,list) or not ev or any(not isinstance(e,dict) or e.get('kind') not in ('method','sample','trial') or not all(text(e.get(k)) for k in ('locator','finding')) for e in ev):
            errors.append(label + ' 需要实际方法、样例或试用证据；热度不构成质量证据')
        setup = c.get('setup', {})
        if not isinstance(setup,dict) or setup.get('status') not in ('available','approval_needed','approved','blocked'):
            errors.append(label + '.setup.status 安装状态无效；合法值：available / approval_needed / approved / blocked；未知环境用 blocked，绑定 readiness 用 unknown'); continue
        for k in ('dependencies','permissions','verification'):
            if not isinstance(setup.get(k),str): errors.append(label + '.setup.' + k + ' 需要字符串，例如尚未核验；不要填写数组')
        if setup['status'] == 'available' and not text(setup.get('verification')): errors.append(label + ' 可用状态需要宿主验证')
        if setup['status'] in ('approval_needed','approved'):
            for k in ('request_reason','installation','fallback'):
                if not text(setup.get(k)): errors.append(label + ' 安装建议需要 ' + k)
        if setup['status'] == 'approved' and not text(setup.get('authorization')): errors.append(label + ' 需要安装授权依据')
        if c.get('origin')=='external':
            try:
                from acquire import validate,digest
                validate(c['acquisition'])
                if c.get('proposal_hash')!=digest(c['acquisition']):raise ValueError('提案版本不一致')
            except (ValueError,KeyError,TypeError) as e:errors.append(label+' 安装提案无效：'+str(e))
    for need in needs:
        label = '能力需求 ' + need['id']
        for k in ('standard','existing_assessment'):
            if not text(need.get(k)): errors.append(label + ' 缺少 ' + k)
        refs = need.get('requirement_ids')
        if not isinstance(refs,list) or not refs or any(not isinstance(r,str) or r not in requirements for r in refs): errors.append(label + ' 需要引用真实用户需求')
        d = need.get('decision', {})
        if not isinstance(d,dict) or d.get('kind') not in ('direct','skill','reference','deferred'):
            errors.append(label + ' 选择方式无效'); continue
        for k in ('reason','application'):
            if not text(d.get(k)): errors.append(label + ' 缺少选择依据或具体规划影响')
        ids = need.get('outline_ids', [])
        if not isinstance(ids,list) or any(not isinstance(i,str) or i not in outlines for i in ids): errors.append(label + ' 引用未知内容项')
        if need.get('gap'):
            discovery = need.get('discovery', {})
            if not isinstance(discovery,dict) or discovery.get('status') not in ('searched','unavailable','not_authorized') or not text(discovery.get('evidence')):
                errors.append(label + ' 存在缺口，需要检索结果或实际限制')
        if need.get('gap') and d['kind'] == 'direct':
            if not text(d.get('fallback_limit')): errors.append(label + ' 降级直接处理须说明未覆盖的质量要求')
            else: warnings.append(label + ' 按已声明范围降级处理：' + d['fallback_limit'])
        if d['kind'] in ('skill','reference'):
            c = byid.get(d.get('candidate_id'))
            if not c: errors.append(label + ' 选择了未知候选'); continue
            if d.get('fit') not in ('supported','unverified','insufficient'): errors.append(label + ' 需要质量适配状态')
            if d.get('fit') != 'supported': warnings.append(label + ' 适配仍待验证，执行前须补齐或调整范围')
            if not ids and outlines and not pending: errors.append(label + ' 选定方法须关联具体内容项')
        if d['kind'] == 'deferred': warnings.append(label + ' 当前能力缺口未解决')
    if errors: return errors, warnings
    assessed = {r for need in needs for r in need['requirement_ids']}
    if requirements-assessed and not pending: errors.append('需求未纳入能力评估：'+', '.join(sorted(requirements-assessed)))
    covered = set()
    for n in p['nodes']:
        refs = n.get('capability_need_ids', [])
        if not isinstance(refs,list) or any(not isinstance(i,str) or i not in known for i in refs): errors.append(n['id'] + ' 能力需求引用无效'); continue
        covered.update(refs)
        for need in needs:
            relevant = bool(set(need['requirement_ids']) & set(n['requirements']) or set(need.get('outline_ids',[])) & set(n.get('outline_ids',[])))
            if need['id'] in refs and not relevant and not pending: errors.append(n['id']+' 能力未关联负责需求或内容')
        owned = {r for need in needs if need['id'] in refs for r in need['requirement_ids']}
        if set(n['requirements'])-owned and not pending: errors.append(n['id']+' 负责需求缺少能力评估')
        for b in n['bindings']:
            c = byid.get(b.get('candidate_id'))
            if not c:
                if not pending: errors.append(n['id'] + ' 技能绑定需要有效 candidate_id')
                continue
            decisions = [x['decision'] for x in needs if x['id'] in refs and x.get('decision',{}).get('candidate_id') == c['id']]
            if not pending and not any(d.get('kind') == 'skill' for d in decisions): errors.append(n['id'] + ' 绑定与能力选择不一致')
            if b.get('readiness') == 'ready' and not pending:
                if c['name'] != b.get('skill') or c.get('setup',{}).get('status') != 'available' or any(d.get('fit') != 'supported' for d in decisions):
                    errors.append(n['id'] + ' 安装可用、质量适配和绑定名称尚未全部核验')
    if known-covered and not pending: errors.append('能力需求缺少负责节点：'+', '.join(sorted(known-covered)))
    if pending: warnings.append('方案已编辑，执行前需要重新评估能力选择')
    return errors, warnings


def require_selection(p, node):
    from capability_policy import require_core_skill
    require_core_skill(p)
    if p.get('open_questions'):raise ValueError('方案仍有待确认事项；先取得决定并更新最新方案，不能把未确认假设当成事实执行')
    if p.get('selection_contract_version') != 1: return
    from capability_policy import specialist_errors
    errors=specialist_errors(p,node)
    if errors:raise ValueError('；'.join(errors))
    if p.get('selection_needs_review') and node['id'] in p.get('selection_review_nodes',[x['id'] for x in p['nodes']]): raise ValueError('方案已修改，需要重新评估能力选择')
    for need in p['capability_needs']:
        if need['id'] not in node.get('capability_need_ids',[]): continue
        d = need['decision']
        if d['kind'] == 'deferred' or (d['kind'] in ('skill','reference') and d.get('fit') != 'supported'):
            raise ValueError('能力适配未验证：'+need['id'])
        if d['kind'] == 'skill':
            c = next(x for x in p['capability_candidates'] if x['id'] == d['candidate_id'])
            if c['setup']['status'] != 'available': raise ValueError('能力安装或宿主验证尚未完成：'+c['name'])
            if c.get('origin')=='external':
                from acquire import verify_install
                if not c.get('installation_directory'):raise ValueError('外部技能缺少具体提案的安装授权与文件核验')
                verify_install(c['acquisition'],c['installation_directory'])
            if not any(b.get('candidate_id') == c['id'] for b in node['bindings']): raise ValueError('选定调用能力缺少绑定')
