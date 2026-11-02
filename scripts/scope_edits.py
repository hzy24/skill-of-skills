"""Cancel explicitly deleted modules and their exclusively owned plan objects."""
def cancel_removed_scope(before,after):
    live={n['id'] for n in after['nodes']}
    removed=[n for n in before['nodes'] if n['id'] not in live]
    if not removed:return
    if not live:raise ValueError('请至少保留一个任务模块')
    gone={n['id'] for n in removed};outputs={o for n in removed for o in n['outputs']}-{o for n in after['nodes'] for o in n['outputs']}
    blockers=[n['title']+'（'+n['id']+'）' for n in after['nodes'] if gone.intersection(n['depends_on']) or outputs.intersection(n['inputs'])]
    if blockers:raise ValueError('这些模块仍依赖待删除模块或其产物：'+'、'.join(blockers)+'。请先调整它们的依赖和输入，或一并删除。')
    deliveries=[d for d in after['deliverables'] if d['id'] in outputs]
    after['deliverables']=[d for d in after['deliverables'] if d['id'] not in outputs]
    if not after['deliverables']:raise ValueError('删除后没有交付物，请保留或设置一项需要的交付')
    reqs={r for n in removed for r in n['requirements']}-{r for n in after['nodes'] for r in n['requirements']}
    canceled_requirements=[r for r in after['requirements'] if r['id'] in reqs]
    after['requirements']=[r for r in after['requirements'] if r['id'] not in reqs]
    needs={i for n in removed for i in n.get('capability_need_ids',[])}-{i for n in after['nodes'] for i in n.get('capability_need_ids',[])}
    if 'capability_needs' in after:
        after['capability_needs']=[x for x in after['capability_needs'] if x['id'] not in needs]
        for x in after['capability_needs']:x['requirement_ids']=[r for r in x['requirement_ids'] if r not in reqs]
    for role in after.get('role_tasks',[]):role['capability_need_ids']=[i for i in role.get('capability_need_ids',[]) if i not in needs]
    possible={o for n in removed for o in n.get('outline_ids',[])}|{o for d in deliveries for o in d.get('outline_ids',[])}
    retained={o for x in after['nodes']+after['deliverables']+after.get('capability_needs',[]) for o in x.get('outline_ids',[])}
    if 'content_outline' in after:after['content_outline']=[o for o in after['content_outline'] if o['id'] not in possible-retained]
    after.setdefault('scope_changes',[]).append({'action':'cancel_modules','from_revision':before['revision'],'nodes':[n['id'] for n in removed],'deliverables':deliveries,'requirements':canceled_requirements,'capability_need_ids':sorted(needs)})
    # Remaining narrative may mention the canceled delivery; host reviews it on execution.
    if after.get('selection_contract_version')==1:
        after['selection_review_nodes']=sorted(live);after['selection_needs_review']=True
