#!/usr/bin/env python3
"""One planning controller. The host authors assignments; this owns protocol state."""
import argparse,copy,hashlib,json,shlex,sys,time
from pathlib import Path
import sos
from plan_io import edit_lock
from method_source import entry,sections,select_sections

STATE='.sos-flow.json'
SCRIPT=Path(__file__).resolve()

def compact_for_host(value,details):
    """Keep host tool truncation from hiding the next action or method index."""
    out=copy.deepcopy(value)
    if not isinstance(out,dict):return out
    out['details_file']=str(details)
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
        keep={'phase','status','next','next_tool','receipt_file','receipt_command','build_command','submit_command','assign_command','publish_command','allowed_actions','terminal','status_command','next_command','candidate','name','source','source_profile','download_bytes','installation','details_file','user_message','readiness','plan_revision','plan_hash','method_index','scope_notes','assessment_command','methods_command','reply_review','final_reply','final_reply_template'}
        out={k:v for k,v in out.items() if k in keep};out['details_truncated']=True
    return out

def command(root,action,*args):
    return shlex.join([sys.executable,str(SCRIPT),str(root),action,*map(str,args)])

def text(value,label):
    if not isinstance(value,str) or not value.strip():raise ValueError(label+'：填写非空文本')
    return value.strip()

def texts(value,label,allow_empty=False):
    if not isinstance(value,list) or (not value and not allow_empty):raise ValueError(label+'：填写文本列表')
    return [text(x,label) for x in value]

def keys(value,allowed,label):
    if not isinstance(value,dict):raise ValueError(label+'：需要对象')
    extra=set(value)-set(allowed)
    if extra:raise ValueError(label+'：删除非业务字段 '+', '.join(sorted(extra)))

def form(goal,inputs):
    return dict(brief_version=2,title=goal,domain='',action=goal,constraints=[],assumptions=[],questions_for_user=[],suggestions=[],
                work=[dict(title=goal,purpose='core',candidate=None,expertise='',
                           questions=[dict(question=goal,methods=[],limits=[])],input_basis='',
                           after=[],deliverables=[dict(title='分析结果',format='md',criteria=[goal])])])

class Flow:
    def __init__(self,root,inputs=()):
        from planning_session import resolve
        self.root=resolve(root,inputs);self.path=self.root/STATE
    def load(self):
        from planning_session import validate_owner
        validate_owner(self.root)
        if not self.path.exists():raise ValueError('先运行 init --goal 用户目标 --inputs 材料路径')
        return sos.read(self.path)
    def save(self,s):sos.save(self.path,s)
    def init(self,goal,inputs,contract=9,new_request=None):
        from planning_session import resolve,session_of
        self.root=resolve(self.root,inputs);self.path=self.root/STATE
        self.root.mkdir(parents=True,exist_ok=True)
        if self.path.exists():return self.status()
        if any((self.root/n).exists() for n in ('plan.json','brief.json','draft.json','.sos-planning.json')):raise ValueError('目录已有任务文件；保留现场并使用独立任务目录')
        paths=[Path(p).resolve(strict=True) for p in inputs]
        if len(paths)>10 or len(set(paths))!=len(paths):raise ValueError('最多提供 10 个不同的输入文件')
        if any(not p.is_file() or self.root==p.parent for p in paths):raise ValueError('输入材料保留在任务目录之外，避免输出覆盖')
        if contract>=7:
            from planning_session import claim
            canonical=claim(self.root,paths,goal,new_request)
            if canonical!=self.root:
                self.root=canonical;self.path=self.root/STATE
                return dict(self.status(),resumed_existing=True,task_dir=str(self.root))
        if not paths:
            request=self.root/'user-request.txt'
            if request.exists():raise ValueError('用户需求记录已存在；保留原文件，使用独立任务目录')
            request.write_text(text(goal,'goal'),encoding='utf-8');paths=[request]
        from profile_inputs import profile
        profiles=[profile(p) for p in paths]
        materials=[dict(name='输入'+str(i+1)+' '+p.name,path=str(p)) for i,p in enumerate(paths)]
        s=dict(version=2,authoring_contract=contract,phase='authoring',goal=text(goal,'goal'),started=time.time(),inputs=materials,candidates={},search_rounds=0,inspect_attempts=0,build_errors=[],delivery_errors=[],events=[])
        s['owner_session']=str(session_of(self.root)) if session_of(self.root) else None
        from assignment import form as assignment_form
        initial=assignment_form(goal) if contract>=5 else form(goal,materials);s['initial_form_hash']=sos.digest(initial)
        self.save(s);sos.save(self.root/'brief.json',initial);sos.save(self.root/'input-profile.json',profiles)
        sos.save(self.root/'.sos-planning.json',dict(started_epoch=s['started'],attempts=[]))
        return dict(self.status(),input_profile=profiles)
    def status(self):
        s=self.load();phase=s['phase']
        if phase=='authoring' and s.get('authoring_contract',0)<5 and time.time()-s['started']>=300 and not s['candidates']:
            return self.blocked(s,'检索时限已到，尚未登记可用方法；保存当前任务供恢复。')
        if phase=='delivered' and s.get('authoring_contract',0)>=4:
            from handoff import finished
            try:finished(sos.read(self.root/'plan.json'),self.root)
            except (ValueError,OSError,KeyError) as e:
                return dict(phase='delivery_blocked',completion_required=True,error=str(e),user_message='附件收尾记录需要恢复，当前不启动执行。',receipt_command=command(self.root,'finish')+' --files <实际HTML路径> <实际JSON路径>',next='交付最新两个文件后运行 finish，恢复原任务；无需重新规划。')
        next_step={'authoring':'检索并核读专业方法，用 Write 一次写完整 brief.json，再运行 submit brief.json。',
                   'awaiting_delivery':'按 next_tool 原样交付两个文件，再将工具实际返回的两个 file_path 作为 --files 参数运行 receipt_command。无需抄写回执 JSON。',
                   'delivered':'附件已登记。结束本轮，等待用户审阅后的确认。',
                   'delivery_blocked':'附件回执未登记。结束本轮并明确报告交付未完成，保留页面和草稿；不要执行。',
                   'planning_failed':'方案生成失败。保留诊断并结束本轮。'}[phase]
        result=dict(phase=phase,brief=str(self.root/'brief.json'),next=next_step,
                    submit_command=command(self.root,'submit',self.root/'brief.json'),status_command=command(self.root,'status'))
        if phase=='authoring':result.update(candidates=[dict(id=k,name=v['name'],source=v['source']) for k,v in s['candidates'].items()],search_rounds_remaining=max(0,2-s['search_rounds']),candidate_attempts_remaining=max(0,3-s['inspect_attempts']))
        if phase=='authoring' and s.get('authoring_contract',0)>=5:
            result.pop('submit_command',None);result.pop('brief',None)
            result.update(next='核读候选后用 assign 登记委托，再 publish。程序生成方法引用、输入与安装提案。',
                          assign_command=command(self.root,'assign','候选编号')+' --title 工作标题 --why 选型理由 --question 业务问题 --output 成果.md --check 交付要求',
                          publish_command=command(self.root,'publish'),
                          allowed_actions=['local --role support','assign','publish','status'] if s.get('assignment_started') or s.get('discovery_closed') else ['search','inspect','local','resource','probe','assign','status'])
            if s.get('assignment_started'):result['next']='委托已登记。可补登记本地制作工具并 assign 配套工作，或 publish 交付方案。专业检索已结束。'
        if phase=='authoring' and s.get('authoring_contract',0)>=6:
            result['original_request']=s['goal']
            result['candidate_attempts_remaining']=max(0,self.inspection_limit(s)-s['inspect_attempts'])
            result['candidates']=[dict(id=k,name=v['name'],fit=v.get('assessment',{}).get('fit','unassessed')) for k,v in s['candidates'].items()]
            result['allowed_actions']=['local --role support','produce','assign','publish','status'] if s.get('assignment_started') else ['assess','assign','status'] if s.get('discovery_closed') else ['search','inspect','local','resource','probe','assess','assign','status']
            result['next']='先 assess 记录候选对原始需求的适配判断，再 assign 完整专业委托。首个核心模块负责原始需求；制作配套使用 produce。'
            if s.get('assignment_started'):result['next']='核心委托已登记。需要额外文件制作时登记真实制作技能并 produce；否则 publish。'
        if s.get('authoring_contract',0)>=7:
            result['task_dir']=str(self.root)
            result['planning_boundary']='本轮只做输入结构识别、能力选型和委托。业务统计、判断、阈值与正文由用户确认后的专业 Skill 完成。'
            if phase=='authoring':
                result['search_rounds_remaining']=max(0,3-s['search_rounds'])
                result['next']='先核读任务专用方法并 assess；领域通用方法需通过专用候选比较。选好后 assign，交付物需制作时 produce，最后 publish。'
                if s.get('assignment_started'):
                    result['next']='委托已登记。需要转交某个已登记交付物给制作技能时 produce --takeover 文件名；否则 publish。原任务目录保持不变。'
        if phase=='awaiting_delivery':
            delivery=s.get('delivery',{})
            if 'next_tool' not in delivery:
                return dict(result,status='delivery_setup_incomplete',next_command=command(self.root,'status'),next='保存服务尚未完成准备；运行返回命令恢复，保留原始方案。')
            result.update(next_tool=delivery['next_tool'],receipt_command=command(self.root,'finish')+' --files <工具返回的HTML路径> <工具返回的JSON路径>',readiness=delivery.get('plan_readiness'))
        if (self.root/'plan.json').exists():
            from plan_message import render
            p=sos.read(self.root/'plan.json')
            result.update(render(p,phase=='delivered',s.get('blocked_reason')))
            result['plan_hash']=sos.digest(p)
        if phase=='awaiting_delivery' and s.get('authoring_contract',0)>=8 and (self.root/'plan.json').exists():
            result['final_reply_template']=render(p,True)['user_message']
            result['receipt_command']=command(self.root,'finish','--reply',result['final_reply_template'])+' --files <工具返回的HTML路径> <工具返回的JSON路径>'
            result['next']='交付两个附件后，将准备发送的回复交给 finish --reply 核对。候选登记不等于已安排执行；只承诺最终方案中的技能与成果。'
        if phase=='delivered':
            result.update(execution_plan=str(self.root/'plan.json'),next='本轮结束。最终回复直接使用 user_message；技能分工和方案状态已由最新 plan.json 生成，不追加草案中的规则、结论或执行承诺。')
            sos.save(self.root/'handoff-message.json',{k:result[k] for k in ('user_message','readiness','plan_revision','plan_hash') if k in result})
        if phase!='authoring':
            for key in ('build_command','submit_command','brief','assign_command','publish_command'):result.pop(key,None)
            result['authoring_closed']=True
            if (self.root/'brief.json').is_file() and s.get('submitted_hash'):
                result['draft_changed_after_publish']=hashlib.sha256((self.root/'brief.json').read_bytes()).hexdigest()!=s['submitted_hash']
                if result['draft_changed_after_publish']:
                    result['next']='方案已生成，后写入的 brief 未替换当前方案。先交付当前附件；用户修改通过 HTML 保存，保留最新 plan.json。'
        if phase=='planning_failed':
            result.update(user_message='方案生成失败，当前没有可执行方案。诊断已保存：'+s.get('blocked_reason','未知错误'),
                          diagnostic=str(self.root/'.sos-planning-error.json'))
            if s.get('authoring_contract',0)>=7:
                result['user_message']='本轮方案未完成，尚未开始执行。已保留材料、检索结果和问题记录，供修复后继续。'
                result['next']='原样交付 user_message 后结束。本轮保留专业 Skill 委托要求，不提出原生分析、工具技能代替或新建目录重试。'
        if phase in ('delivered','delivery_blocked','planning_failed'):
            result.pop('status_command',None);result['terminal']=True
        if phase=='awaiting_delivery' and 'next_tool' in result:
            result={'phase':phase,'next_tool':result['next_tool'],'receipt_command':result['receipt_command'],'completion_required':True,'next':'附件工具返回后立即调用 receipt_command；finish 输出前本轮尚未完成。',**{k:v for k,v in result.items() if k not in ('phase','next_tool','receipt_command','next')}}
        return result
    def writable(self,s):
        if s['phase']!='authoring':raise ValueError('本轮已生成方案；运行 status 获取交付动作，用户修改通过 HTML 保存。')
    def probe(self,input_index,column,kind,sheet=None):
        s=self.load();self.writable(s)
        if s.get('assignment_started'):return self.status()
        if not 1<=input_index<=len(s['inputs']):raise ValueError('输入编号从1开始，使用 init 已登记的材料')
        key=json.dumps([input_index,column,kind,sheet]);cache=s.setdefault('probes',{})
        if key in cache:return dict(cache[key],cached=True)
        if len(cache)>=2:return dict(status='probe_budget_used',next='复用已有结构画像；进一步计算写入专业技能的执行委托。')
        from profile_inputs import probe
        result=probe(s['inputs'][input_index-1]['path'],column,kind,sheet);cache[key]=result;self.save(s)
        return dict(result,next='仅用此结果确定时间范围或字段口径；分组指标、比较结论、归因和建议在确认后由选定 Skill 执行。')
    def search(self,queries,focus=None,category=None,level='task'):
        s=self.load();self.writable(s)
        if s.get('assignment_started'):return self.status()
        if s.get('discovery_closed') or s['search_rounds']>=(3 if s.get('authoring_contract',0)>=7 else 2) or (s.get('authoring_contract',0)<5 and time.time()-s['started']>=300):
            return self.end_discovery(s,'搜索轮次或时间预算已用完')
        if s.get('authoring_contract',0)>=7 and level=='domain':
            from selection_review import domain_gate
            issue=domain_gate(s)
            if issue:return dict(status='specific_search_required',reason=issue,next='继续比较任务专用能力；读取或网络故障先处理来源，不据此改选通用能力。')
        from search_skills import search,summary
        from discovery_scope import create,filter_results,chinese_queries,concept_scope,query_plan
        if s.get('authoring_contract',0)>=5:
            from discovery_scope import QueryConceptError
            try:queries=query_plan(queries,preserve_phrases=s.get('authoring_contract',0)>=8,atomic=s.get('authoring_contract',0)>=9)
            except QueryConceptError as e:
                return dict(status='query_concepts_required',request=s['goal'],reason=str(e),
                    network_requests=0,budget_consumed=False,next='保留原始需求；将中文业务对象与专业岗位分别作为 search 参数。无需读取或修改字段文件。')
            s['discovery_scope']=concept_scope(s['goal'],queries,s.get('discovery_scope'))
            focus=None
        if not s.get('discovery_scope') and not focus and s.get('authoring_contract',0)>=3:
            return dict(status='needs_search_focus',next='提供 --focus 用户业务对象，以及对应的中文专业概念。',request=s['goal'])
        queries=chinese_queries(queries,focus or s.get('discovery_scope',{}).get('focus'))
        if not s.get('discovery_scope'):
            if focus:s['discovery_scope']=create(s['goal'],focus,queries)
        elif focus and focus!=s['discovery_scope']['focus']:
            # Compound requests may contain several professional objects. Each
            # additional one must still be an actual phrase in the user's goal.
            additional=s['discovery_scope'].setdefault('additional',[])
            if not any(x['focus']==focus for x in additional):additional.append(create(s['goal'],focus,queries))
        elif focus:
            scoped=create(s['goal'],focus,queries)
            s['discovery_scope']['anchors']=list(dict.fromkeys(s['discovery_scope']['anchors']+scoped['anchors']))
            s['discovery_scope']['queries']=list(dict.fromkeys(s['discovery_scope']['queries']+scoped['queries']))
        s['search_rounds']+=1;self.save(s)
        r=search(self.root,queries,category=category) if category else search(self.root,queries)
        if s.get('discovery_scope'):r=filter_results(r,s['discovery_scope'])
        out=self.root/('search-'+str(s['search_rounds'])+'.json');sos.save(out,r)
        if s.get('authoring_contract',0)>=7:
            s.setdefault('search_history',[]).append(dict(level=level,queries=queries,category=category,
                success=any(x.get('status')=='searched' for x in r.get('searches',[])),
                slugs=[c['slug'] for c in r['candidates'] if c.get('current_round',True)]))
            self.save(s)
        result=summary(r,out);result.update(inspect_command=command(self.root,'inspect','搜索返回的slug'),next='结合业务目标挑选专业方法并 inspect；结果偏泛时第二轮加 --category 收窄专业分类，零命中时去分类或换词。候选原文与提案自动登记。')
        if result.get('unmatched_queries'):
            result['next']+=' 以下词没有直接用途命中：'+'、'.join(result['unmatched_queries'])+'；其他词召回的热门候选不证明覆盖这些问题，必要时换短同义词。'
        if s.get('discovery_scope'):
            result.update(focus=s['discovery_scope']['focus'],excluded_count=len(r.get('excluded',[])))
            if not r['candidates']:result['next']='当前结果没有本次专业对象。下一轮用中文领域名、同义词或上位专业概念，保持 focus；检索词无需重复用户原话。'
        return result
    def end_discovery(self,s,reason):
        s['discovery_closed']=True;s['closed_attempts']=s.get('closed_attempts',0)+1;self.save(s)
        usable=[c for c in s['candidates'].values() if c.get('registration_role','core')=='core' and c.get('source_profile',{}).get('kind') in ('specialty_candidate','unclassified')]
        from capability_profile import task_kind
        if task_kind(s['goal'])=='artifact':usable=list(s['candidates'].values())
        if s.get('authoring_contract',0)>=6:
            undecided=[c for c in usable if not c.get('assessment')]
            suitable=[c for c in usable if c.get('assessment',{}).get('fit')=='suitable']
            if suitable or undecided:
                return dict(self.status(),stop_discovery=True,reason=reason,next='核读已结束。对尚未评估的候选 assess；只将 suitable 候选登记为核心委托。已淘汰候选保持淘汰。')
            return self.authoring_error(s,'候选未覆盖原始需求；已保存淘汰理由和检索结果，不能改派给无关技能。', (self.root/'brief.json').read_bytes())
        if not usable or (s.get('authoring_contract',0)<5 and s['closed_attempts']>=2):
            return self.blocked(s,reason+'；本轮未形成可提交的专业委托。已保留检索和材料记录。')
        if s.get('authoring_contract',0)>=5:return dict(self.status(),stop_discovery=True,reason=reason,next='检索已结束。用已登记的专业候选 assign 工作，然后 publish。')
        return dict(self.status(),stop_discovery=True,reason=reason,next='检索已关闭。复用已登记候选，一次写完整 brief.json 后 submit；再次检索或登记会结束本轮。')
    def candidate(self,s,result,origin,role='core',source_terms=None):
        path=Path(result['method_file']);raw=path.read_bytes();name,body=entry(raw.decode('utf-8'))
        if not name:raise ValueError('候选入口没有可识别的 name；保留失败记录，选择其他候选。')
        if not sections(body):raise ValueError('候选入口没有可引用的方法正文；选择其他候选。')
        source=result.get('source',str(path));proposal=None
        if origin=='external':
            from acquire import validate,digest
            proposal=validate(sos.read(result['proposal']));source=proposal['catalog_url']
            if digest(proposal)!=result['proposal_hash']:raise ValueError('候选提案发生变化')
        ident='c-'+hashlib.sha256((source+hashlib.sha256(raw).hexdigest()).encode()).hexdigest()[:10]
        from capability_profile import classify
        value=dict(name=name,source=source,origin=origin,registration_role=role,method_file=str(path.resolve()),sha256=hashlib.sha256(raw).hexdigest(),sections=sections(body),source_profile=classify(raw.decode('utf-8'),2 if s.get('authoring_contract',0)>=9 else 1))
        if s.get('assignment_started') and value['source_profile']['kind']!='artifact_tool':
            return dict(status='discovery_closed',next='编排阶段只补登记本地制作工具。专业工作复用已选能力，继续 assign 或 publish。')
        if source_terms:
            from discovery_scope import terms,hits
            anchors=[t.strip().lower() for t in source_terms if isinstance(t,str) and t.strip()]
            if not 1<=len(anchors)<=4 or any(len(t)>80 or terms(t)!=[t] or not hits(body,[t]) for t in anchors):raise ValueError('source terms 使用原文中实际存在的完整专业术语，最多4项；仅用于核读，不发往检索接口')
            scope=s.setdefault('discovery_scope',{})
            scope['source_aliases']=list(dict.fromkeys(scope.get('source_aliases',[])+anchors))
            value['source_aliases']=anchors;self.save(s)
        if s.get('discovery_scope'):
            from discovery_scope import match
            method_scope=copy.deepcopy(s['discovery_scope']);method_scope['anchors']+=method_scope.get('source_aliases',[])
            value['task_match']=match(method_scope,value['source_profile']['identity']+'\n'+body)
            from capability_profile import task_kind
            format_task=task_kind(s['goal'])=='artifact' and value['source_profile']['kind']=='artifact_tool'
            if s.get('authoring_contract',0)<5 and not value['task_match']['matched'] and not format_task and role!='support':
                return dict(status='candidate_scope_mismatch',name=name,source=source,focus=s['discovery_scope']['focus'],
                            reason='实际 Skill 用途未覆盖本次专业对象；目录名称不能代替方法原文。',
                            method=body[:3000],next='原文为其他语言时，用 inspect 同一 slug --terms 完整原文专业术语核对；中文检索词保持不变。用途无关则选择其他候选。')
        if proposal:value.update(proposal=result['proposal'],proposal_hash=result['proposal_hash'])
        previous=s['candidates'].get(ident)
        if previous:
            for key in ('assessment','resources'):
                if key in previous:value[key]=copy.deepcopy(previous[key])
        s['candidates'][ident]=value;self.save(s)
        catalog=value['sections'];method=body[:16000];truncated=len(body)>16000
        if s.get('discovery_scope'):
            from discovery_scope import match
            ranked=sorted(catalog,key=lambda x:bool(match(method_scope,x['text'])['matched']),reverse=True)
            relevant=[x for x in ranked if match(method_scope,x['text'])['matched']]
            if relevant:
                method='\n\n'.join(x['text'][:1800] for x in relevant[:3]);truncated=True
            catalog=ranked
        result=dict(candidate=ident,name=name,source=source,source_profile=value['source_profile'],download_bytes=proposal.get('download_bytes') if proposal else 0,
                    method=method,method_truncated=truncated,
                    sections=[dict(id=x['id'],title=x['title']) for x in catalog],
                    reference_files=[dict(path=f['path'],bytes=f['bytes']) for f in (proposal or {}).get('files',[]) if f['path'].endswith(('.md','.json','.yaml','.yml','.txt')) and f['path']!='SKILL.md'][:30],
                    resource_command=command(self.root,'resource',ident,'文件清单中的相对路径'),
                    downloaded=['SKILL.md'],installation='尚未安装；reference_files 仅为固定版本文件清单，配套文档使用 resource 按需读取。',
                    next='在 brief.json 选择 candidate。程序绑定上述来源画像，expertise 只解释专业适配理由，无需抄写画像。只选当前问题必要的方法，避免把技能全部规则编成计划。表格核心方法填写 inputs 对照原文要求与实际字段；工具画像负责制作配套成果。必要配套规则用 resource。')
        if s.get('authoring_contract',0)>=5:
            result.pop('sections',None)
            if origin=='installed':
                result['installation']='已发现本地技能入口；执行准备时核验运行依赖。'
                result.pop('downloaded',None)
            result['next']='核对用途、方法和运行前提；适合则 assign 候选编号并说明理由。程序绑定真实原文；字段解释、阈值选择和计算由专业 Skill 执行。必要方法配套文档用 resource。'
            result['recall_match']=value.get('task_match',{})
        if s.get('authoring_contract',0)>=6:
            from selection_review import catalog
            result['method']=body[:16000]
            result['method_truncated']=len(body)>16000
            result['method_index']=[dict(ref=x['ref'],title=x['title']) for x in catalog(value)]
            result['scope_notes']=[line.strip()[:350] for line in body.splitlines() if any(t in line.lower() for t in ('不适用','不处理','不用于','不包括','不负责','out of scope','not for','does not','exclud','only for'))][:10]
            result['assessment_command']=command(self.root,'assess',ident)+' --fit suitable --method <方法章节标题或编号> --reason <为何能完成原始需求>'
            result['next']='对照原始需求、实际方法和范围限制。适合用 assess --fit suitable；不适合用 assess --fit unsuitable --reason 原因，记录后继续选型。需要方法全文用 section；完整安装仍需授权。'
        if s.get('authoring_contract',0)>=7:
            result['selection_scope']='task：方法直接解决具体业务问题。domain：采用同领域通用方法，需要先保留专用检索与取舍记录。跨领域通用统计不能替代业务专业能力。'
            result['assessment_command']+=' --coverage task'
        if s.get('authoring_contract',0)>=8:
            from selection_review import method_choices
            result['method_index']=method_choices(value)
            result['assessment_command']=command(self.root,'assess',ident)+' --fit suitable --reason <专业方法如何完成用户需求>'
            result['methods_command']=command(self.root,'methods',ident)
            result['next']='核读用途、方法及限制后判断适配性；默认委托完整工作流，省略 --method。仅取部分能力时使用目录序号或完整标题，多个 --method 可重复。编号无需抄写。'
        return result
    def inspection_limit(self,s):
        # An unavailable source may use one replacement request. Rejections
        # remain rejections; neither elapsed time nor this budget changes fit.
        failed=sum(x.get('status')=='candidate_unavailable' for x in s.get('inspections',{}).values())
        if s.get('authoring_contract',0)>=7:
            failed+=sum(x.get('status')=='candidate_unavailable' for k,x in s.get('local_attempts',{}).items() if not k.endswith(':support'))
            return min(6,3+failed)
        return 3+min(1,failed) if s.get('authoring_contract',0)>=6 else 3
    def inspect(self,slug,source_terms=None):
        s=self.load();self.writable(s)
        if s.get('assignment_started'):return self.status()
        cache=s.setdefault('inspections',{})
        cache_key=slug+('::'+json.dumps(source_terms,ensure_ascii=False) if source_terms else '')
        if cache_key in cache:
            previous=cache[cache_key]
            if 'candidate' not in previous:
                if s.get('authoring_contract',0)>=6:return dict(previous,next='该来源已失败且不会重复下载；选择其他搜索候选。')
                return self.end_discovery(s,'同一外部候选已核读失败，停止重复获取')
            reuse=s.setdefault('reuse_counts',{});reuse[slug]=reuse.get(slug,0)+1;self.save(s)
            if s.get('authoring_contract',0)<5 and reuse[slug]>=2:return self.end_discovery(s,'候选原文已重复返回，结束检索')
            if s.get('authoring_contract',0)>=6:
                c=s['candidates'][previous['candidate']]
                return dict(candidate=previous['candidate'],name=c['name'],already_registered=True,assessment=c.get('assessment'),
                            next='该候选已淘汰，选择其他专业能力。' if c.get('assessment',{}).get('fit')=='unsuitable' else '复用已读原文；完成 assess 后 assign。')
            return dict(candidate=previous['candidate'],name=previous['name'],already_registered=True,next='候选已登记。继续 assign 委托；必要配套文档用 resource。' if s.get('authoring_contract',0)>=5 else '该候选已核读并登记；复用原文，填写 brief.json。必要配套文档用 resource。')
        from search_skills import search
        records=[]
        for f in self.root.glob('search-*.json'):records+=sos.read(f)['candidates']
        if not any(c['slug']==slug for c in records):raise ValueError('inspect 只接收本任务实际搜索返回的 slug')
        if s.get('discovery_closed') or (s['inspect_attempts']>=self.inspection_limit(s) and slug not in s.get('inspection_sources',{})) or (s.get('authoring_contract',0)<5 and time.time()-s['started']>=300):return self.end_discovery(s,'候选核读预算已用完')
        if source_terms:
            used=s.setdefault('source_term_attempts',[])
            if slug in used:return self.end_discovery(s,'该候选原文术语核对已完成，停止重复调整')
            used.append(slug);self.save(s)
        saved=s.get('inspection_sources',{}).get(slug)
        if not saved:s['inspect_attempts']+=1
        self.save(s)
        try:
            from tencent_source import inspect
            r=saved or inspect(self.root,slug,'对应用户任务：'+s['goal'],s['goal'],'按原文核验运行依赖','原文许可待核实')
            s.setdefault('inspection_sources',{})[slug]=r;self.save(s)
            result=self.candidate(s,r,'external',source_terms=source_terms)
        except (ValueError,KeyError,TypeError,OSError) as e:
            result=dict(status='candidate_unavailable',slug=slug,error=str(e),next='该候选本轮不再重试；选其他已召回候选或在委托中说明未覆盖的方法。')
        s=self.load();s.setdefault('inspections',{})[cache_key]=result;self.save(s);return result
    def local(self,path,focus=None,terms=None,role='core'):
        s=self.load();self.writable(s)
        if s.get('assignment_started') and role!='support':return self.status()
        if s.get('authoring_contract',0)>=5 and focus:
            from discovery_scope import concept_scope,query_plan
            s['discovery_scope']=concept_scope(s['goal'],query_plan(terms or [focus]),s.get('discovery_scope'));focus=None;self.save(s)
        if focus:
            from discovery_scope import create
            scoped=create(s['goal'],focus,terms or [focus])
            if not s.get('discovery_scope'):s['discovery_scope']=scoped
            elif s['discovery_scope']['focus']!=focus and not any(x['focus']==focus for x in s['discovery_scope'].get('additional',[])):
                s['discovery_scope'].setdefault('additional',[]).append(scoped)
            self.save(s)
        path=Path(path).resolve()
        if path.is_dir():path=path/'SKILL.md'
        key=str(path)+':'+role;cache=s.setdefault('local_attempts',{})
        if key in cache:
            old=cache[key]
            if 'candidate' not in old:return self.end_discovery(s,'相同本地候选已被拒绝；停止重复登记')
            c=s['candidates'][old['candidate']]
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=c['sha256']:raise ValueError('已登记方法文件发生变化，保留原任务与候选快照')
            reuse=s.setdefault('reuse_counts',{});reuse[key]=reuse.get(key,0)+1;self.save(s)
            if s.get('authoring_contract',0)<5 and reuse[key]>=2:return self.end_discovery(s,'候选登记信息已重复返回，结束检索')
            if s.get('authoring_contract',0)>=6:
                return dict(candidate=old['candidate'],name=c['name'],already_registered=True,assessment=c.get('assessment'),
                            next='该候选已淘汰，选择其他专业能力。' if c.get('assessment',{}).get('fit')=='unsuitable' else '复用已读原文；核心能力完成 assess 后 assign，制作配套用 produce。')
            return dict(candidate=old['candidate'],name=c['name'],already_registered=True,next='候选已登记。继续 assign 委托。' if s.get('authoring_contract',0)>=5 else '复用已读方法与章节，继续填写 brief.json。')
        counter='support_attempts' if s.get('authoring_contract',0)>=5 and role=='support' else 'inspect_attempts'
        if (s.get('discovery_closed') and counter!='support_attempts') or s.get(counter,0)>=(3 if counter=='support_attempts' else self.inspection_limit(s)) or (s.get('authoring_contract',0)<5 and time.time()-s['started']>=300):return self.end_discovery(s,'候选核读预算已用完')
        s[counter]=s.get(counter,0)+1;self.save(s)
        try:result=self.candidate(s,dict(method_file=str(path)), 'installed',role)
        except (ValueError,OSError) as e:result=dict(status='candidate_unavailable',error=str(e),next='该路径核读失败；复用其他候选，停止重复登记。')
        s=self.load();s.setdefault('local_attempts',{})[key]=result;self.save(s);return result
    def section(self,candidate,section):
        s=self.load();self.writable(s);c=s['candidates'].get(candidate)
        if s.get('assignment_started'):return self.status()
        if not c:raise ValueError('未知候选编号')
        reads=s.setdefault('section_reads',[]);key=candidate+':'+section
        if key in reads:return dict(already_read=True,next='该章节已返回；复用原文完成 assess 选型，再 assign 委托。' if s.get('authoring_contract',0)>=6 else '该章节已返回；复用已有方法，完整写入 brief.json 后 submit。')
        if len(reads)>=2:return dict(stop_reading=True,next='补读结束；根据已读原文完成选型判断。')
        if '::' in section:
            file,sid=section.split('::',1);resource=c.get('resources',{}).get(file)
            if not resource:raise ValueError('先通过 resource 读取该文件')
            raw=Path(resource['file']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=resource['sha256']:raise ValueError('方法资源已变化')
            body=raw.decode('utf-8');actual_ref=sid
        else:
            name,body=entry(Path(c['method_file']).read_text());actual_ref=section
        reads.append(key);self.save(s)
        try:result=select_sections(body,[actual_ref])
        except ValueError:return dict(status='choose_existing_section',sections=[dict(id=x['id'],title=x['title']) for x in c['sections']],next='使用上面的实际章节 ID；配套文档文件名需通过 resource 读取，不是章节 ID。')
        return result
    def resource(self,candidate,path):
        s=self.load();self.writable(s);c=s['candidates'].get(candidate)
        if s.get('assignment_started'):return self.status()
        if not c:raise ValueError('未知候选编号')
        from acquire import safe_rel,verify_file,digest
        path=safe_rel(path)
        if Path(path).suffix.lower() not in ('.md','.json','.yaml','.yml','.txt'):raise ValueError('规划阶段只补读方法文档，不下载执行脚本或依赖')
        resources=c.setdefault('resources',{})
        if path in resources:
            if s.get('authoring_contract',0)>=5:return dict(already_read=True,next='文档已登记，程序自动绑定来源。继续 assign 登记委托。')
            return dict(already_read=True,sections=resources[path]['index'],next='复用已读规则；用返回的完整章节 ID 填 questions 内的 methods.section。')
        reads=s.setdefault('section_reads',[])
        if len(reads)>=2:return dict(stop_reading=True,next='补读结束；用已读方法 assign 委托并 publish。' if s.get('authoring_contract',0)>=5 else '本轮补读已结束；根据已读方法形成委托，尚无方法的问题留空 methods。')
        reads.append(candidate+':'+path);self.save(s)
        if c['origin']=='external':
            proposal=sos.read(c['proposal'])
            if digest(proposal)!=c['proposal_hash']:raise ValueError('提案已变化')
            row=next((f for f in proposal['files'] if f['path']==path),None)
            if not row:raise ValueError('文件不在固定版本清单中')
            if row['bytes']>65536:raise ValueError('规划补读文档超过 64 KiB；使用入口方法决定适配，完整资源留给执行')
            from tencent_source import fetch
            raw=fetch(row['url'],65536,time.monotonic()+20);verify_file(row,raw)
            dest=self.root/'.sos-flow-resources'/candidate/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        else:
            base=Path(c['method_file']).parent.resolve();dest=(base/path).resolve(strict=True)
            if not dest.is_relative_to(base):raise ValueError('配套文件必须位于已登记技能目录')
            if dest.stat().st_size>65536:raise ValueError('规划补读文档超过 64 KiB')
            raw=dest.read_bytes()
        body=raw.decode('utf-8');catalog=sections(body);index=[dict(id=path+'::'+x['id'],title=x['title']) for x in catalog]
        resources[path]=dict(file=str(dest),sha256=hashlib.sha256(raw).hexdigest(),index=index);self.save(s)
        if s.get('authoring_contract',0)>=6:
            return dict(candidate=candidate,resource=path,text=body[:16000],truncated=len(body)>16000,
                        method_index=[dict(ref=x['id'],title=path+'::'+x['title']) for x in index],
                        next='按实际适用的方法完成 assess，--method 可使用上述完整编号或标题。')
        if s.get('authoring_contract',0)>=5:
            return dict(candidate=candidate,resource=path,text=body[:16000],truncated=len(body)>16000,next='方法文档已登记。用 assign 说明适配理由与业务委托，引用由程序生成。')
        return dict(candidate=candidate,resource=path,text=body[:16000],truncated=len(body)>16000,sections=index,next='用这些完整 ID 填 questions 内的 methods.section，直接继续业务委托，无需再次读取或安装。')
    def draft(self,s,b):
        from brief_authoring import normalize
        if s.get('authoring_contract',0)>=5:
            from assignment import expand
            b=expand(b,s)
        b,suggestions=normalize(b)
        keys(b,('title','domain','action','constraints','assumptions','decisions','work'),'brief')
        title=text(b.get('title'),'title');domain=text(b.get('domain') or '任务专业方法','domain');action=text(b.get('action') or s['goal'],'action')
        for k in ('constraints','assumptions'):texts(b.get(k,[]),k,True)
        if not isinstance(b.get('work'),list) or not b['work']:raise ValueError('work：保留至少一个业务委托')
        draft=dict(draft_version=3,title=title,goal=s['goal'],mapping=dict(domain=domain,action=action,input_condition='；'.join(m['name'] for m in s['inputs']),capabilities=[action]),inputs=s['inputs'],skills=[],work=[],constraints=b.get('constraints',[]),assumptions=b.get('assumptions',[]),open_questions=[])
        chosen={};coverage_by_work=[]
        for i,w in enumerate(b['work']):
            at='work['+str(i)+']';keys(w,('title','purpose','candidate','expertise','questions','coverage','missing_methods','input_basis','after','deliverables'),at)
            title=text(w.get('title'),at+'.title');questions=texts(w.get('questions'),at+'.questions');role=w.get('purpose','core')
            if role not in ('core','support','basic'):raise ValueError(at+'.purpose：core / support / basic')
            cid=w.get('candidate');c=s['candidates'].get(cid) if isinstance(cid,str) else None
            if cid is not None and not c:raise ValueError(at+'.candidate：使用 inspect/local 返回的编号或 null')
            missing=[];missing_questions=[]
            if not isinstance(w.get('missing_methods',[]),list):raise ValueError(at+'.missing_methods：需要列表')
            for gap in w.get('missing_methods',[]):
                if not isinstance(gap,dict):raise ValueError(at+'.missing_methods：只登记未被原文覆盖的问题，使用 {"question":"questions 原句","required_method":"缺少的专业判断方法"}；缺字段、缺材料、需安装写 constraints，不写方法缺口。')
                keys(gap,('question','required_method'),at+'.missing_methods')
                q=text(gap.get('question'),at+'.missing_methods.question')
                if q not in questions:raise ValueError(at+'.missing_methods.question：引用 questions 原句')
                missing_questions.append(q);missing.append(q+'：'+text(gap.get('required_method'),at+'.missing_methods.required_method'))
            coverage=w.get('coverage',[])
            if not isinstance(coverage,list):raise ValueError(at+'.coverage：需要列表')
            applications=[];section_ids=[];covered=[]
            for row in coverage:
                keys(row,('question','section','application','inputs'),at+'.coverage')
                q=text(row.get('question'),at+'.coverage.question')
                if q not in questions:raise ValueError(at+'.coverage.question：引用本委托 questions 中的原句')
                if not c:raise ValueError(at+'.coverage：先选择真实候选')
                ref=text(row.get('section'),at+'.coverage.section')
                if '::' in ref:
                    file,sid=ref.split('::',1);resource=c.get('resources',{}).get(file)
                    if not resource:raise ValueError('先用 resource 核读清单中的方法文档')
                    raw=Path(resource['file']).read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=resource['sha256']:raise ValueError('方法资源已改变')
                    selected=select_sections(raw.decode('utf-8'),[sid])[0];selected['source_file']=resource['file']
                    method_sid=c['sections'][0]['id']
                else:
                    selected=select_sections(entry(Path(c['method_file']).read_text())[1],[ref])[0];method_sid=selected['id']
                app=text(row.get('application'),at+'.coverage.application')
                covered.append(q);section_ids.append(method_sid);applications.append(dict(question=q,section=selected,application=app,inputs=row.get('inputs',[])))
            if c and role!='basic':
                if hashlib.sha256(Path(c['method_file']).read_bytes()).hexdigest()!=c['sha256']:raise ValueError('候选原文已改变，保留现场并重新核对')
                if set(covered)&set(missing_questions):raise ValueError(at+'：同一问题不能同时已覆盖和缺少方法。材料限制写 constraints；真正缺少原文方法时移除相应 coverage。')
                if set(covered)|set(missing_questions)!=set(questions):raise ValueError(at+'.coverage：逐项对应 questions；原文没有规则的判断写 missing_methods，不能用自填 pass 放行')
            if role!='basic' and not c and not missing:missing=['尚未选定覆盖本委托的专业方法']
            if c and role=='core':
                from capability_profile import core_issue,classify
                profile=classify(Path(c['method_file']).read_text(),c['source_profile'].get('profile_version',1))
                explanation=w.get('expertise')
                if isinstance(explanation,dict):explanation=explanation.get('reason')
                issue=core_issue(s['goal'],profile,dict(request=s['goal'],specialty=c.get('assessment',{}).get('professional_purpose',profile['identity']),reason=explanation))
                if issue:missing.append(issue)
                from discovery_scope import source_issue
                from capability_profile import task_kind
                format_task=task_kind(s['goal'])=='artifact' and profile['kind']=='artifact_tool'
                issue=source_issue(s.get('discovery_scope'),profile['identity'],[x['section'] for x in applications]) if not format_task else None
                if issue:missing.append(issue)
            # Declared gaps cannot be waived by a second, contradictory pass field.
            use=bool(c and not missing and role!='basic')
            if use:
                basis=text(w.get('input_basis'),at+'.input_basis')
                fit_reason='；'.join(dict.fromkeys(x['application'] for x in applications))
                skill=dict(name=c['name'],source=c['source'],method_file=c['method_file'],method_sections=list(dict.fromkeys(section_ids)),method_scope='specialist' if role=='core' else 'general',fit_reason=fit_reason,input_fit=basis,origin=c['origin'])
                if c['origin']=='external':
                    from acquire import digest,validate
                    proposal=validate(sos.read(c['proposal']))
                    if digest(proposal)!=c['proposal_hash']:raise ValueError('实际安装提案已变化')
                    skill['proposal']=c['proposal']
                if cid not in chosen:chosen[cid]=skill
                else:
                    old=chosen[cid];old['method_sections']=list(dict.fromkeys(old['method_sections']+skill['method_sections']));old['fit_reason']='；'.join(dict.fromkeys([old['fit_reason'],skill['fit_reason']]))
                    if role=='core':old['method_scope']='specialist'
            outputs=w.get('deliverables')
            if not isinstance(outputs,list) or not outputs:raise ValueError(at+'.deliverables：保留成果名称、格式与标准')
            for o in outputs:
                keys(o,('title','format','criteria','pages'),at+'.deliverables');text(o.get('title'),'deliverable.title');text(o.get('format'),'deliverable.format');texts(o.get('criteria'),'deliverable.criteria')
            after=texts(w.get('after',[]),at+'.after',True)
            work_inputs=after if s.get('authoring_contract',0)>=6 and role=='support' else [m['name'] for m in s['inputs']]+after
            draft['work'].append(dict(title=title,role=role,skill=c['name'] if use else None,inputs=work_inputs,questions=questions,gap='；'.join(missing),deliverables=outputs,reason='；'.join(dict.fromkeys(x['application'] for x in applications)) or '；'.join(missing) or '按约定完成材料交接'))
            coverage_by_work.append(applications)
        draft['skills']=list(chosen.values())
        decisions=b.get('decisions',[])
        if not isinstance(decisions,list):raise ValueError('decisions：需要列表')
        for decision in decisions:
            keys(decision,('question','affects','reason'),'decisions')
            draft['open_questions'].append(dict(decision,blocking=True))
        return draft,coverage_by_work
    def assess(self,candidate,fit,reason,methods=(),limits=(),coverage='task',purpose=None):
        s=self.load()
        if s['phase']!='authoring' or s.get('assignment_started'):return self.status()
        if candidate not in s['candidates']:raise ValueError('使用核读结果中的候选编号')
        from selection_review import assess
        c=s['candidates'][candidate]
        specialty=None
        if purpose is not None and fit=='suitable':
            chosen=next((v for v in c['source_profile'].get('purpose_options',[]) if v['number']==purpose),None)
            if not chosen:return dict(status='purpose_choice_required',candidate=candidate,purpose_options=c['source_profile'].get('purpose_options',[]),next='使用用途列表中的编号；无需抄写或翻译原文。')
            specialty=chosen['text']
        if s.get('authoring_contract',0)>=9 and fit=='suitable' and c.get('registration_role','core')=='core':
            from capability_profile import responsibility_issue,core_issue
            profile=c['source_profile']
            issue=responsibility_issue(s['goal'],profile,specialty)
            if not issue:issue=core_issue(s['goal'],profile,dict(request=s['goal'],specialty=specialty or profile['identity'],reason=reason))
            if issue:
                return dict(status='core_choice_rejected',candidate=candidate,reason=issue,purpose_options=profile.get('purpose_options',[]),
                    source_purpose=profile['identity'],next='保留原始任务，选择承担业务判断的专业方法；配套工具不接管核心。')
        if s.get('authoring_contract',0)>=7 and fit=='suitable' and coverage=='domain':
            from selection_review import domain_gate
            issue=domain_gate(s,candidate)
            if issue:return dict(status='specific_search_required',reason=issue,next='核对任务专用候选；来源故障不作为采用领域通用能力的理由。')
        if s.get('authoring_contract',0)>=8:
            from selection_review import MethodChoiceError
            try:decision=assess(c,s['goal'],fit,reason,methods,limits,whole_default=True)
            except MethodChoiceError as e:
                return dict(status='method_choice_required',candidate=candidate,error=str(e),
                            method_index=e.choices,next='使用返回的编号或完整标题；委托完整工作流时省略 --method。无需读取内部文件。',
                            assessment_command=command(self.root,'assess',candidate,'--fit',fit,'--reason',reason))
        else:decision=assess(c,s['goal'],fit,reason,methods,limits)
        if s.get('authoring_contract',0)>=7:
            decision['coverage']=coverage
            if coverage=='domain':
                decision['compared_candidates']=[dict(candidate=k,name=v['name'],reason=v['assessment']['reason']) for k,v in s['candidates'].items() if k!=candidate and v.get('assessment',{}).get('fit')=='unsuitable']
                decision['specific_searches']=[x for x in s.get('search_history',[]) if x['level']=='task']
        if s.get('authoring_contract',0)>=9 and fit=='suitable':
            decision['professional_purpose']=specialty or c['source_profile']['identity']
        c['assessment']=decision
        self.save(s)
        return dict(candidate=candidate,name=c['name'],assessment=c['assessment'],
                    next='已淘汰；继续选择其他专业能力。' if fit=='unsuitable' else '选型判断已登记。确认其他已核读核心候选的取舍后 assign；首个核心委托自动保留完整原始需求。')
    def methods(self,candidate):
        from selection_review import method_choices
        s=self.load();self.writable(s)
        if candidate not in s['candidates']:raise ValueError('使用核读结果中的候选编号')
        return dict(candidate=candidate,method_index=method_choices(s['candidates'][candidate]),
                    next='默认委托完整工作流，无需章节参数；局部委托可使用序号、完整标题或编号。')
    def produce(self,candidate,outputs,checks,after,takeover=None):
        s=self.load()
        if s['phase']!='authoring':return self.status()
        c=s['candidates'].get(candidate,{})
        if c.get('source_profile',{}).get('kind')!='artifact_tool' or c.get('registration_role')!='support':
            raise ValueError('produce 使用 local --role support 实际返回的制作技能编号；专业技能分工用 assign')
        if takeover:
            if outputs or after:raise ValueError('takeover 与 output/after 分开使用，避免交付物重复')
            return self.transfer_production(s,candidate,takeover,checks)
        if not outputs:raise ValueError('使用 --output 新文件名，或 --takeover 已登记文件名')
        if not after:raise ValueError('制作模块通过 --after 接收上游专业成果')
        from selection_review import assess
        from assignment import source_refs
        reason='使用 '+c['name']+' 将上游专业成果制作成约定文件，保持结论、数字与依据一致。'
        c['assessment']=assess(c,s['goal'],'suitable',reason,source_refs(c,[]))
        self.save(s)
        return self.assign(candidate,'制作 '+'、'.join(outputs),reason,
            ['将已完成的 '+'、'.join(after)+' 制作成 '+'、'.join(outputs)+'；专业判断与计算沿用上游成果。'],
            outputs,checks,'support',after,_production=True)
    def transfer_production(self,s,candidate,output,checks):
        """Atomically separate analysis and production of an existing output."""
        from assignment import item,source_refs
        from selection_review import assess
        from capability_profile import task_kind
        if task_kind(s['goal'])=='artifact':raise ValueError('纯制作任务直接由原制作模块交付')
        b=sos.read(self.root/'brief.json');owners=[w for w in b['work'] if any(d['title']==output for d in w['deliverables'])]
        if len(owners)!=1:raise ValueError('takeover 使用已登记且只有一个负责模块的交付物')
        owner=owners[0]
        if owner['purpose']!='core':raise ValueError('该交付物已由制作模块负责')
        if any(output in w.get('after',[]) for w in b['work']):raise ValueError('交付物已有下游依赖；保留现有委托，通过方案页面调整')
        c=s['candidates'][candidate]
        reason='使用 '+c['name']+' 制作专业模块交付的内容，保持数字、结论和依据一致。'
        c['assessment']=assess(c,s['goal'],'suitable',reason,source_refs(c,[]))
        original=next(d for d in owner['deliverables'] if d['title']==output)
        handoff=Path(output).stem+'-专业内容.md'
        existing={d['title'] for w in b['work'] for d in w['deliverables']}
        if handoff in existing:raise ValueError('专业内容文件名已有委托，保留原分工')
        original.update(title=handoff,format='md')
        work=item(candidate,'制作 '+output,reason,['将上游专业内容制作成 '+output+'；沿用专业模块的计算和判断。'],[output],checks,'support',[handoff])
        b['work'].append(work)
        sos.save(self.root/'brief.json',b);s['assignment_hash']=sos.digest(b);self.save(s)
        return dict(self.status(),transferred=output,professional_content=handoff)
    def assign(self,candidate,title,reason,questions,outputs,checks,role='core',after=(),limits=(),_production=False):
        s=self.load()
        if s['phase']!='authoring':return self.status()
        if candidate not in s['candidates']:raise ValueError('选择已核读并登记的候选编号')
        if s.get('authoring_contract',0)>=6:
            c=s['candidates'][candidate]
            if role=='support' and not _production:
                raise ValueError('制作配套使用 produce <真实制作候选编号> --after 上游成果 --output 文件 --check 要求；专业问题由 core 委托承担')
            a=c.get('assessment',{})
            if a.get('fit')!='suitable':raise ValueError('候选尚未获选或已被淘汰；先完成 assess 选型判断')
            reason=reason or a['reason']
            if role=='core':
                pending=[k for k,v in s['candidates'].items() if v.get('registration_role','core')=='core' and not v.get('assessment')]
                if pending:raise ValueError('先记录已核读候选的取舍：'+', '.join(pending)+'；优先直接回答原始问题的方法')
                if not s.get('primary_title'):
                    questions=list(dict.fromkeys([s['goal'],*questions]))
        if role=='core':
            from capability_profile import core_issue
            profile=s['candidates'][candidate]['source_profile']
            issue=core_issue(s['goal'],profile,dict(request=s['goal'],specialty=s['candidates'][candidate].get('assessment',{}).get('professional_purpose',profile['identity']),reason=reason))
            if issue:return dict(self.status(),status='core_choice_rejected',reason=issue,next='选择已经核读的专业候选承担核心委托；制作工具可用 --role support 登记。')
        from assignment import item
        work=item(candidate,title,reason,questions,outputs,checks,role,after)
        b=sos.read(self.root/'brief.json')
        if b.get('brief_version')!=3:raise ValueError('旧任务沿用原提交协议；assign 用于新版初始化的任务')
        titles=[w['title'] for w in b['work']]
        if title in titles:
            if b['work'][titles.index(title)]!=work:
                return dict(status='assignment_already_registered',next='该工作已登记。publish 交付后在 HTML 中修改，避免重复编排。')
        else:
            known={d['title'] for w in b['work'] for d in w['deliverables']}
            if set(after)-known:raise ValueError('after 引用已登记的上游成果文件名')
            if known & set(outputs):raise ValueError('成果文件已有负责委托；为配套成果使用不同文件名')
            b['work'].append(work)
        b['constraints']=list(dict.fromkeys(b.get('constraints',[])+list(limits)))
        sos.save(self.root/'brief.json',b)
        s['assignment_started']=True;s['assignment_hash']=sos.digest(b);self.save(s)
        if s.get('authoring_contract',0)>=6 and role=='core' and not s.get('primary_title'):
            s['primary_title']=title;self.save(s)
        return dict(self.status(),assignments=[dict(title=w['title'],skill=s['candidates'][w['candidate']]['name'],outputs=[d['title'] for d in w['deliverables']]) for w in b['work']])
    def submit(self,path):
        """Accept one complete business document; preserve the previous file on parse failure."""
        s=self.load()
        if s['phase']!='authoring':return self.status()
        if s.get('authoring_contract',0)>=5:return dict(self.status(),next='新版委托通过 assign 登记，publish 生成方案；submit 保留给旧任务。')
        path=Path(path).resolve()
        if path.suffix!='.json' or not path.is_file():raise ValueError('submit 使用已写完的业务 JSON 文件')
        try:
            if path.stat().st_size>256*1024:raise ValueError('业务委托超过 256 KiB；保留问题、方法与成果，详细正文交给执行')
            data=json.loads(path.read_text())
        except (ValueError,OSError) as e:return self.authoring_error(s,str(e),path.read_bytes() if path.is_file() else b'')
        if not isinstance(data,dict):return self.authoring_error(s,'业务委托需要 JSON 对象',path.read_bytes())
        if path!=self.root/'brief.json':sos.save(self.root/'brief.json',data)
        return self.build()
    def authoring_error(self,s,error,raw):
        fingerprint=hashlib.sha256(raw).hexdigest()
        s['build_errors'].append(dict(hash=fingerprint,error=error));self.save(s)
        if s.get('authoring_contract',0)>=5:
            sos.save(self.root/'.sos-planning-error.json',dict(error=error,assignment_hash=fingerprint))
            s.update(phase='planning_failed',blocked_reason=error);self.save(s)
            return self.status()
        if len(s['build_errors'])>=2:return self.blocked(s,error)
        return dict(status='repair_brief_once',error=error,brief=str(self.root/'brief.json'),
                    next_command=command(self.root,'submit',self.root/'brief.json'),
                    next='用 Write 完整替换 brief.json 一次，保留原需求及已选方法；再次 submit。按错误信息修正，无需查看控制器源码。')
    def build(self):
        s=self.load()
        if s['phase']!='authoring':return self.status()
        raw=(self.root/'brief.json').read_bytes();fingerprint=hashlib.sha256(raw).hexdigest()
        try:untouched=sos.digest(json.loads(raw))==s.get('initial_form_hash')
        except ValueError:untouched=False
        if untouched and s.get('authoring_contract',0)>=5:return dict(self.status(),status='brief_not_authored',next='先通过 assign 登记专业委托，再 publish。')
        if s.get('authoring_contract',0)>=5:
            try:registered=sos.digest(json.loads(raw))==s.get('assignment_hash')
            except ValueError:registered=False
            if not registered:return self.authoring_error(s,'委托文件与 assign 登记版本不同，保留现场供检查。',raw)
        if untouched:
            return dict(status='brief_not_authored',phase='authoring',next='当前仍是初始化样表。用 Write 一次写入完整委托，再 submit；尚未发布或锁定方案。',
                        brief=str(self.root/'brief.json'),candidates=[dict(id=k,name=c['name'],sections=[dict(id=x['id'],title=x['title']) for x in c['sections']]) for k,c in s['candidates'].items()])
        errors=s['build_errors']
        if errors and errors[-1]['hash']==fingerprint:return self.blocked(s,'业务草案未修正，停止重复编译。'+errors[-1]['error'])
        try:
            b=json.loads(raw);draft,coverage=self.draft(s,b)
            from prepare_plan import prepare
            p,_=prepare(draft,self.root)
        except (ValueError,KeyError,TypeError,OSError) as e:
            return self.authoring_error(s,str(e),raw)
        s['submitted_hash']=fingerprint
        return self.publish(s,p,coverage)
    def blocked(self,s,reason):
        # A valid, explicitly unresolved plan terminates schema-repair loops.
        from prepare_plan import prepare
        d=dict(draft_version=3,title=s['goal'],goal=s['goal'],mapping=dict(domain='原任务',action=s['goal'],input_condition='已登记原始材料',capabilities=[s['goal']]),inputs=s['inputs'],skills=[],constraints=['本轮规划未完成：'+reason],work=[dict(title=s['goal'],role='core',skill=None,inputs=[x['name'] for x in s['inputs']],questions=[s['goal']],gap='规划草案未通过校验，保留原需求与修复记录供继续处理',deliverables=[dict(title='目标成果',format='md',criteria=[s['goal']])])])
        p,_=prepare(d,self.root);s['blocked_reason']=reason
        return self.publish(s,p,[])
    def publish(self,s,p,coverage):
        p['review_protocol_version']=2;p['handoff_protocol_version']=1;p['flow_protocol_version']=1
        p['profile_policy_version']=1
        try:b=sos.read(self.root/'brief.json')
        except (ValueError,OSError):b={}
        if not isinstance(b,dict):b={}
        from brief_authoring import normalize
        try:
            from assignment import expand
            _,p['suggestions']=normalize(expand(b,s) if s.get('authoring_contract',0)>=5 else b)
        except (ValueError,TypeError):p['suggestions']=[]
        for candidate in p['capability_candidates']:
            source=next((c for c in s['candidates'].values() if c['name']==candidate['name'] and c['source']==candidate['source']),None)
            if source:
                from capability_profile import classify
                candidate['source_profile']=classify(Path(source['method_file']).read_text(),source['source_profile'].get('profile_version',1))
                if s.get('authoring_contract',0)>=6:
                    candidate['selection_assessment']=copy.deepcopy(source.get('assessment',{}))
        authored_work=b.get('work',[])
        if not isinstance(authored_work,list):authored_work=[authored_work]
        authored_work=[w if isinstance(w,dict) else {} for w in authored_work]
        for index,(need,w) in enumerate(zip(p['capability_needs'],authored_work)):
            c=next((c for c in p['capability_candidates'] if c['id']==need.get('decision',{}).get('candidate_id')),None)
            explanation=w.get('expertise')
            if isinstance(explanation,dict):explanation=explanation.get('reason')
            need['expertise']=dict(request=s['goal'],specialty=c.get('selection_assessment',{}).get('professional_purpose',c.get('source_profile',{}).get('identity','')) if c else '',reason=explanation)
            if s.get('discovery_scope'):
                need['domain_method_evidence']=[x['section'] for x in coverage[index]] if index<len(coverage) else []
        from method_inputs import check,tabular
        profiles=sos.read(self.root/'input-profile.json')
        from capability_profile import task_kind
        if s.get('authoring_contract',0)==4 and tabular(profiles) and task_kind(s['goal'])!='artifact':
            p['input_contract_version']=1
            for index,need in enumerate(p['capability_needs']):
                if need.get('role')!='core':continue
                rows=coverage[index] if index<len(coverage) else []
                need['method_input_checks']=[dict(section=row['section']['id'],inputs=row.get('inputs',[]),issues=check(row.get('inputs',[]),row['section']['excerpt'],profiles,True)) for row in rows]
        if s.get('authoring_contract',0)>=5:p['assignment_protocol_version']=1
        if s.get('authoring_contract',0)>=6:
            p['selection_review_version']=1
            owner=next((n for n in p['nodes'] if n['title']==s.get('primary_title')),None)
            p['primary_assignment']=dict(request=s['goal'],node=owner['id'] if owner else None)
            p['selection_decisions']=[dict(name=c['name'],source=c['source'],**c['assessment']) for c in s['candidates'].values() if c.get('assessment')]
        if s.get('authoring_contract',0)>=7:p['selection_policy_version']=2
        if s.get('authoring_contract',0)>=9:p['message_protocol_version']=2
        p['coverage_map']=coverage
        if s.get('discovery_scope'):p['discovery_scope']=copy.deepcopy(s['discovery_scope'])
        resource_paths=list(dict.fromkeys(row['section']['source_file'] for group in coverage for row in group if 'source_file' in row['section']))
        for i,path in enumerate(resource_paths):p['materials'].append(dict(id='MR'+str(i+1),title='专业方法配套依据 '+Path(path).name,path=path))
        from method_review import packet,accept,basis
        review=packet(p,self.root)
        from capability_profile import issues
        all_supported=not issues(p) and all(n['decision'].get('fit')=='supported' for n in p['capability_needs'] if n.get('task_kind')!='basic')
        if all_supported:
            for r in review['items']:
                n=next(x for x in p['capability_needs'] if x['id']==r['need']);c=next(x for x in p['capability_candidates'] if x['id']==n['decision']['candidate_id'])
                r.update(verdict='pass',reason=n['decision']['reason'],input_basis=c['evidence'][0]['finding'],limits='按委托执行；宿主判断技能适配，程序绑定真实来源，专业 Skill 负责字段解释、适用条件和专业验证')
                if s.get('authoring_contract',0)>=6:
                    a=c['selection_assessment']
                    r.update(judged_by='host',reason=a['reason'],limits='；'.join(a.get('limits',[])) or '执行时由专业 Skill 确认适用条件；当前仅完成选型判断。',
                             verification='source_and_ownership_only')
            p=accept(p,review,self.root)
        path=self.root/'plan.json'
        if path.exists():raise ValueError('plan.json 已存在，保留用户方案；使用 status 恢复交付。')
        sos.save(path,p)
        sos.save(self.root/'.sos-completion.json',dict(status='pending',plan_id=p['id'],plan_hash=sos.digest(p)))
        s.update(phase='awaiting_delivery',published_basis=basis(p),published_hash=sos.digest(p));self.save(s)
        return self.deliver(s)
    def deliver(self,s):
        from plan_delivery import prepare
        result=prepare(self.root/'plan.json')
        if result['status']=='delivery_setup_failed':
            s['service_failures']=s.get('service_failures',0)+1
            if s['service_failures']>=2:
                s['phase']='delivery_blocked';s['blocked_reason']=result.get('error','保存服务未就绪')
            s['delivery']=result;self.save(s)
            if s['phase']=='delivery_blocked':return dict(self.status(),error=s['blocked_reason'])
            return dict(result,retry_command=command(self.root,'status'))
        s['delivery']=result;self.save(s);return self.status()
    def receipt(self,paths=None,reply=None):
        s=self.load()
        if s['phase'] not in ('awaiting_delivery','delivery_blocked','delivered'):return self.status()
        if s.get('authoring_contract',0)>=8 and reply is None:
            from plan_message import render
            p=sos.read(self.root/'plan.json')
            return dict(phase=s['phase'],status='reply_review_required',completion_required=True,
                        final_reply_template=render(p,True)['user_message'],
                        next='使用模板或准备发送的完整回复作为 --reply；程序核对交付承诺后返回 final_reply。')
        from handoff import record,record_paths,resolve_reported_paths,HandoffVersionError
        try:r=record_paths(self.root/'plan.json',self.root/'plan.html',resolve_reported_paths(self.root,paths)) if paths is not None else record(self.root/'plan.json',self.root/'plan.html',self.root/'receipt.txt')
        except HandoffVersionError as e:
            s['phase']='awaiting_delivery';self.save(s)
            return dict(self.deliver(s),error=str(e),next='页面已按当前 JSON 刷新；重新交付两个附件，再使用本次返回的收尾命令。')
        except (ValueError,KeyError,TypeError,OSError) as e:
            s['delivery_errors'].append(str(e))
            if len(s['delivery_errors'])>=2:s['phase']='delivery_blocked'
            self.save(s);return dict(self.status(),error=str(e),next='将 PresentToUser 实际返回的两个 file_path 作为 --files 参数；只补漏交文件，不手写回执格式。' if s['phase']=='awaiting_delivery' else '交付登记失败两次；报告交付未完成并结束，保留文件，不执行。')
        with edit_lock(self.root/'plan.json'):
            from plan_message import render
            p=sos.read(self.root/'plan.json')
            from handoff import location
            if sos.read(location(self.root)).get('delivered_hash')!=sos.digest(p):
                return dict(phase='awaiting_delivery',status='delivery_changed',completion_required=True,next='登记期间方案已保存新版本；交付最新 HTML 和 JSON 后再次 finish。')
            result=render(p,True,s.get('blocked_reason'))
            sos.save(self.root/'.sos-completion.json',dict(status='finished',message_status='prepared',plan_id=p['id'],plan_hash=sos.digest(p),revision=p['revision'],user_message=result['user_message'],message_hash=hashlib.sha256(result['user_message'].encode()).hexdigest()))
            if s.get('authoring_contract',0)>=8:
                from plan_message import review_reply
                reviewed=review_reply(p,reply)
                sos.save(self.root/'.sos-reply-review.json',dict(reviewed,plan_hash=sos.digest(p)))
            s.update(phase='delivered',handoff=r);self.save(s)
            result=self.status()
            if s.get('authoring_contract',0)>=8:
                result.update(final_reply=reviewed['final_reply'],reply_review=reviewed['action'],
                              next='下一条消息发送 final_reply 字段的正文，然后结束。该正文已按最新方案核对。')
            return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('task_dir');sub=ap.add_subparsers(dest='action',required=True)
    p=sub.add_parser('init');p.add_argument('--goal',required=True);p.add_argument('--inputs',nargs='*',default=[]);p.add_argument('--new-request',help='仅用户另行交办新任务时记录其完整原话，保留旧任务历史')
    p=sub.add_parser('search');p.add_argument('queries',nargs='+');p.add_argument('--focus');p.add_argument('--category');p.add_argument('--level',choices=['task','domain'],default='task')
    p=sub.add_parser('inspect');p.add_argument('slug');p.add_argument('--terms',nargs='+')
    p=sub.add_parser('local');p.add_argument('method_file');p.add_argument('--focus');p.add_argument('--terms',nargs='+');p.add_argument('--role',choices=['core','support'],default='core')
    p=sub.add_parser('section');p.add_argument('candidate');p.add_argument('section')
    p=sub.add_parser('methods');p.add_argument('candidate')
    p=sub.add_parser('resource');p.add_argument('candidate');p.add_argument('path')
    p=sub.add_parser('probe');p.add_argument('input_index',type=int);p.add_argument('column');p.add_argument('kind',choices=['types','date_range']);p.add_argument('--sheet')
    p=sub.add_parser('receipt');p.add_argument('--files',nargs=2);p.add_argument('--reply')
    p=sub.add_parser('finish');p.add_argument('--files',nargs=2,required=True);p.add_argument('--reply')
    p=sub.add_parser('submit');p.add_argument('file')
    p=sub.add_parser('assign');p.add_argument('candidate');p.add_argument('--title',required=True);p.add_argument('--why');p.add_argument('--question',action='append',default=[]);p.add_argument('--output',action='append',required=True);p.add_argument('--check',action='append',required=True);p.add_argument('--role',choices=['core','support'],default='core');p.add_argument('--after',action='append',default=[]);p.add_argument('--limit',action='append',default=[])
    p=sub.add_parser('assess');p.add_argument('candidate');p.add_argument('--fit',choices=['suitable','unsuitable'],required=True);p.add_argument('--reason',required=True);p.add_argument('--method',action='append',default=[]);p.add_argument('--limit',action='append',default=[]);p.add_argument('--coverage',choices=['task','domain'],default='task');p.add_argument('--purpose',type=int,help='未分类用途时选择 purpose_options 的实际编号')
    p=sub.add_parser('produce');p.add_argument('candidate');p.add_argument('--output',action='append',default=[]);p.add_argument('--check',action='append',required=True);p.add_argument('--after',action='append',default=[]);p.add_argument('--takeover')
    for n in ('build','publish','status'):sub.add_parser(n)
    a=ap.parse_args();f=Flow(a.task_dir,getattr(a,'inputs',()));f.root.mkdir(parents=True,exist_ok=True)
    with edit_lock(f.root/'.sos-flow-lock'):
        if a.action in ('search','inspect','local','section','methods','resource','probe') and f.load()['phase']!='authoring':r=f.status()
        elif a.action=='init':r=f.init(a.goal,a.inputs,new_request=a.new_request)
        elif a.action=='search':r=f.search(a.queries,a.focus,a.category,a.level)
        elif a.action=='inspect':r=f.inspect(a.slug,a.terms)
        elif a.action=='local':r=f.local(a.method_file,a.focus,a.terms,a.role)
        elif a.action=='section':r=f.section(a.candidate,a.section)
        elif a.action=='methods':r=f.methods(a.candidate)
        elif a.action=='resource':r=f.resource(a.candidate,a.path)
        elif a.action=='probe':r=f.probe(a.input_index,a.column,a.kind,a.sheet)
        elif a.action=='assign':r=f.assign(a.candidate,a.title,a.why,a.question,a.output,a.check,a.role,a.after,a.limit)
        elif a.action=='assess':r=f.assess(a.candidate,a.fit,a.reason,a.method,a.limit,a.coverage,a.purpose)
        elif a.action=='produce':r=f.produce(a.candidate,a.output,a.check,a.after,a.takeover)
        elif a.action in ('build','publish'):r=f.build()
        elif a.action=='submit':r=f.submit(a.file)
        elif a.action in ('receipt','finish'):r=f.receipt(a.files,a.reply)
        else:
            s=f.load()
            r=f.deliver(s) if s['phase']=='awaiting_delivery' and 'next_tool' not in s.get('delivery',{}) else f.status()
    details=f.root/'.sos-flow-results'/(str(time.time_ns())+'.json');sos.save(details,r)
    if a.action=='finish' and r.get('phase') in ('delivered','delivery_blocked'):
        if f.load().get('authoring_contract',0)>=8 and r.get('final_reply'):
            print(json.dumps(dict(terminal=True,phase=r['phase'],plan_hash=r.get('plan_hash'),
                reply_review=r['reply_review'],final_reply=r['final_reply'],
                next='发送 final_reply 字段的完整正文并结束本轮。'),ensure_ascii=False));return
        if f.load().get('authoring_contract',0)==7:
            print(r['user_message']);return
        if 6<=f.load().get('authoring_contract',0)<7:
            print(json.dumps(dict(terminal=True,phase=r['phase'],plan_hash=r.get('plan_hash'),
                                  user_message=r['user_message'],next='下一条消息原样发送 user_message 后结束。任务范围、模块和安装授权均已来自最新方案。'),ensure_ascii=False));return
        if f.load().get('authoring_contract',0)<6:print(r['user_message']);return
    print(json.dumps(compact_for_host(r,details),ensure_ascii=False))
    if r.get('status') in ('candidate_unavailable','candidate_scope_mismatch','core_choice_rejected','flow_error') or r.get('phase')=='planning_failed':sys.exit(2)
if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:
        print(json.dumps(dict(status='flow_error',error=str(e),next='保留现场；按具体业务字段修正，不修改脚本或内部状态。'),ensure_ascii=False));sys.exit(2)
