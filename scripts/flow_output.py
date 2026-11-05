"""Bounded planning responses and read-only access to their complete saved content."""
import copy,json,re,shlex,sys
from pathlib import Path

def view_command(root,ident,page=1,field=None):
    parts=[sys.executable,str(Path(__file__).with_name('flow.py')),str(root),'view',ident,'--page',str(page)]
    if field:parts+=['--field',field]
    return shlex.join(parts)

def response(value,root,action,phase):
    """Place control fields first. Status never repeats a discovery operation."""
    out=dict(schema='sos-flow-result-v1',action=action,phase=phase,status=value.get('status',action+'_complete'))
    out.update(value)
    if phase=='authoring':out['recovery_command']=shlex.join([sys.executable,str(Path(__file__).with_name('flow.py')),str(root),'status'])
    if action=='status' and phase=='authoring' and (root/'.sos-last-result.json').is_file():
        last=json.loads((root/'.sos-last-result.json').read_text())
        out['last_result_command']=view_command(root,last['result_id'])
    return out

def render(value,details):
    """Bound stdout without silently dropping a candidate list or a method tail."""
    if value.get('reply_contract'):return value['reply_contract']
    if value.get('status')=='result_page':return value
    details=Path(details);small=compact_for_host(value,details)
    priority=('schema','action','phase','status','terminal','dispatch','task_dir','next','next_command','next_tool',
              'recovery_command','last_result_command','receipt_command','review_command','context_file','review_file',
              'route_command','route_file','assessment_command','inspect_command','methods_command','resource_command')
    out={k:value[k] for k in priority if k in value}
    for k,v in small.items():
        if k not in out and len(json.dumps(dict(out,**{k:v}),ensure_ascii=False).encode())<=9000:out[k]=v
    paged=[k for k in value if k not in out or out[k]!=value[k]]
    # Truncation flags are preserved; every changed/omitted field has a safe reader.
    if paged:
        out['paged_fields']=paged
        out['view_command']=view_command(details.parent.parent,details.stem)
        out['read_more']='view_command 可加 --field 字段名；仅读取已保存结果，不重新检索。'
    return out

def read_page(root,ident,page=1,field=None):
    if not re.fullmatch(r'[0-9]{1,30}',ident):raise ValueError('view 使用工具返回的结果编号')
    path=root/'.sos-flow-results'/(ident+'.json')
    if path.is_symlink() or not path.is_file():raise ValueError('结果不在当前任务记录中；运行 status 获取当前结果')
    value=json.loads(path.read_text())
    if field is not None and field not in value:raise ValueError('可读字段：'+', '.join(value))
    content=value[field] if field else value
    text=content if isinstance(content,str) else json.dumps(content,ensure_ascii=False,indent=2)
    pages=max(1,(len(text)+1599)//1600)
    if not 1<=page<=pages:raise ValueError('page 范围为 1–'+str(pages))
    result=dict(phase='authoring',status='result_page',result_id=ident,source_status=value.get('status'),
                field=field,page=page,pages=pages,text=text[(page-1)*1600:page*1600])
    if page<pages:result['next_page_command']=view_command(root,ident,page+1,field)
    else:result['next']='本字段已读完；继续原结果给出的动作。'
    return result

def compact_for_host(value,details):
    """Keep host tool truncation from hiding the next action or method index."""
    out=copy.deepcopy(value)
    if not isinstance(out,dict):return out
    # Terminal results have no diagnostics, draft commands or recovery menus.
    if out.get('reply_contract'):return out['reply_contract']
    out['details_file']=str(details)
    if out.get('context_file') and isinstance(out.get('review'),dict):
        # Evidence is read once from context_file, never copied into host input.
        out['review']={'items':[{k:r[k] for k in ('need','stage','skill','verdict') if k in r}
                               for r in out['review'].get('items',[])]}
    if out.get('phase')=='awaiting_delivery' and out.get('next_tool'):
        # The only host actions at this point; no plan/method dump before finish.
        return {k:out[k] for k in ('phase','next_tool','receipt_command','completion_required','next','details_file','final_reply_template') if k in out}
    def size():return len(json.dumps(out,ensure_ascii=False).encode('utf-8'))
    for key in ('method','text'):
        if key in out and len(out[key].encode('utf-8'))>6000:
            out[key]=out[key].encode('utf-8')[:6000].decode('utf-8',errors='ignore');out[key+'_truncated']=True
            if key=='text':out['truncated']=True
    for key in ('sections','reference_files','method_index'):
        if len(out.get(key,[]))>30:out[key]=out[key][:30];out[key+'_truncated']=True
    if size()>12000:
        for key in ('method','text'):
            if key in out:
                out[key]=out[key][:800];out[key+'_truncated']=True
                if key=='text':out['truncated']=True
    if size()>12000 and 'input_profile' in out:
        out['input_profile']=[{k:v for k,v in x.items() if k not in ('sample_rows','excerpt')} for x in out['input_profile']]
        out['profile_truncated']=True
    if size()>12000 and out.get('candidates'):
        # Preserve enough alternatives for semantic selection instead of losing
        # the shortlist to generic output truncation after broad API recall.
        for candidate in out['candidates']:
            for key,limit in (('name',60),('description',120)):
                if isinstance(candidate.get(key),str):candidate[key]=candidate[key][:limit]
            candidate.pop('matched_task_terms',None)
        while size()>12000 and len(out['candidates'])>6:
            out['candidates'].pop();out['candidates_truncated']=True
    if size()>12000:
        if 'source_profile' in out:
            out['source_profile']['identity']=out['source_profile'].get('identity','')[:600]
        if 'method_index' in out:out['method_index']=out['method_index'][:20];out['method_index_truncated']=True
        if 'scope_notes' in out:out['scope_notes']=[x[:200] for x in out['scope_notes'][:6]]
    if size()>12000:
        for key in ('input_profile','sections','reference_files'):
            if key in out:out[key]=out[key][:3];out[key+'_truncated']=True
    if size()>12000:
        keep={'phase','status','next','next_tool','receipt_file','receipt_command','build_command','submit_command','assign_command','publish_command','allowed_actions','terminal','status_command','next_command','candidate','name','source','source_profile','download_bytes','installation','details_file','user_message','readiness','plan_revision','plan_hash','method_index','scope_notes','assessment_command','methods_command','reply_review','final_reply','final_reply_template','route_template_command','route_file','route_command','review_file','context_file','review_command','diagnostics','reason','search_command','method_comparison_available'}
        out={k:v for k,v in out.items() if k in keep};out['details_truncated']=True
    return out

