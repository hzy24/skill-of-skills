"""Place cross-delivery reviews after their inputs exist, without a new run protocol."""

def route(p,final_checks):
    if not isinstance(final_checks,list):raise ValueError('final_checks 需要列表')
    nodes=p['nodes'];deliveries=p['deliverables'];owners={o:n['id'] for n in nodes for o in n['outputs']}
    titles={d['title']:d['id'] for d in deliveries};byid={n['id']:n for n in nodes}
    deps={n['id']:{owners[i] for i in n['inputs'] if i in owners and owners[i]!=n['id']} for n in nodes}
    ordered=[]
    while len(ordered)<len(nodes):
        ready=[n['id'] for n in nodes if n['id'] not in ordered and deps[n['id']]<=set(ordered)]
        if not ready:raise ValueError('业务输入形成循环依赖，先调整交接关系')
        ordered.extend(ready)
    rank={nid:i for i,nid in enumerate(ordered)};pending=[]
    for item in final_checks:
        if not isinstance(item,dict) or set(item)-{'artifacts','criteria'}:raise ValueError('final_checks 每项需要 artifacts（成果名称列表）和 criteria（标准文本）')
        refs=item.get('artifacts');criterion=item.get('criteria')
        if not isinstance(refs,list) or not refs or any(not isinstance(r,str) or r not in titles for r in refs):raise ValueError('final_checks.artifacts 需引用实际成果名称')
        if not isinstance(criterion,str) or not criterion.strip():raise ValueError('final_checks.criteria 需要具体标准文本')
        pending.append((criterion,list(dict.fromkeys(titles[r] for r in refs)),'explicit'))
    # Local checks remain local. Language such as "consistency" says nothing
    # about which artifacts are needed; only explicit artifact references route.
    if not pending:return
    seen=set();moved=[]
    for criterion,refs,origin in pending:
        key=(criterion,tuple(sorted(refs)))
        if key in seen:continue
        seen.add(key)
        target=byid[max((owners[ref] for ref in refs),key=rank.get)]
        for ref in refs:
            if ref not in target['outputs'] and ref not in target['inputs']:target['inputs'].append(ref)
        names='、'.join(d['title'] for d in deliveries if d['id'] in refs)
        artifact=next(ref for ref in refs if owners[ref]==target['id'])
        target['checks'].append(dict(id=target['id']+'-cross-'+str(len(seen)),kind='review',artifact=artifact,
                                    criteria='交付前对照 '+names+'：'+criterion,review_inputs=refs))
        moved.append(dict(from_node=origin,to_node=target['id'],criteria=criterion,artifacts=refs))
    # The editable route now shows local versus delivery-wide acceptance where
    # it is actually performed. prepare() derives the added dependencies.
    for n in nodes:
        for o in p['content_outline']:
            if o['id'] in n['outline_ids']:o['acceptance']=[c['criteria'] for c in n['checks'] if c['kind']=='review']
    p['review_handoffs']=moved
