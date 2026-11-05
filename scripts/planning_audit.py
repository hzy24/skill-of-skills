"""Host-call boundary and observed-reply audit for the planning phase.

check_tool can be called BEFORE dispatch by hosts supporting tool hooks. audit
checks a saved trace AFTER dispatch. Installing this Skill alone does not install
a host hook or prevent arbitrary shell tools outside flow.py.
"""
import argparse,json,re,shlex
from pathlib import Path
from plan_message import check_response
from planning_actions import ACTIONS as PUBLIC_ACTIONS, LEGACY_ACTIONS
ACTIONS=set(PUBLIC_ACTIONS)|LEGACY_ACTIONS

def controller_tokens(command):
    if not isinstance(command,str) or any(x in command for x in ('`','$(')):return []
    try:
        lexer=shlex.shlex(command,posix=True,punctuation_chars=';&|<>\n');lexer.whitespace=' \t\r'
        tokens=list(lexer)
    except ValueError:return []
    # A single cwd change is structural, not business computation.
    if len(tokens)>3 and tokens[0]=='cd' and tokens[2]=='&&' and not tokens[1].startswith('-'):tokens=tokens[3:]
    if any(t and all(c in ';&|<>\n' for c in t) for t in tokens):return []
    return tokens

def authoring_file(value,task_dir=None,context=False):
    if not isinstance(value,str) or '..' in Path(value).parts:return False
    p=Path(value)
    if task_dir:
        root=Path(task_dir)
        if not p.is_absolute():p=root/p
        try:p=p.relative_to(root)
        except ValueError:return False
    elif p.is_absolute():
        # Without an observed task directory only recognize the form shape.
        if p.name in ('route.json','route-review.json'):return True
        return bool(re.search(r'/\.sos/reviews/[0-9a-f]{64}/(?:decisions'+('|context' if context else '')+r')\.json$',str(p)))
    return str(p) in ('route.json','route-review.json') or bool(re.fullmatch(
        r'\.sos/reviews/[0-9a-f]{64}/(?:decisions'+('|context' if context else '')+r')\.json',str(p)))

def check_tool(name,args,phase='authoring',new_request_authorized=False,task_dir=None):
    if phase in ('delivered','planning_failed','delivery_blocked'):
        return dict(allowed=False,reason='规划终态之后只发送收尾文本；后续执行等待用户确认')
    if name in ('Bash','exec_command'):
        command=args.get('command',args.get('cmd',''));tokens=controller_tokens(command)
        if tokens and Path(tokens[0]).name=='ls' and phase=='authoring':
            return dict(allowed=True,category='structure_read',reason='列出文件路径')
        valid=(len(tokens)>=4 and re.fullmatch(r'python(?:3(?:\.\d+)?)?',Path(tokens[0]).name)
               and Path(tokens[1]).name=='flow.py' and tokens[3] in ACTIONS)
        if '--new-request' in tokens and not new_request_authorized:valid=False
        if valid and phase=='awaiting_delivery':valid=tokens[3] in ('status','finish')
        category='controller' if valid else 'workflow_drift'
        if not valid and re.search(r'groupby\s*\(|Counter\s*\(|pivot_table\s*\(|\.resample\s*\(|\.agg\s*\(',command):category='business_analysis'
        if not valid and not tokens:category='business_analysis' if category=='business_analysis' else 'unreviewed_command'
        return dict(allowed=bool(valid),category=category,reason='规划控制器动作' if valid else '调用超出规划入口；定位文件用目录工具，业务处理留给执行')
    if name in ('Write','Edit'):
        valid=authoring_file(args.get('file_path',''),task_dir)
        return dict(allowed=valid and phase=='authoring',category='route_authoring' if valid else 'workflow_drift',reason='写业务路线或适配判断；格式错误由 route/review 一次诊断')
    if name=='Skill':return dict(allowed=args.get('skill')=='skill-of-skills',reason='首轮仅加载 SoS，所选专业技能在确认后执行')
    if name=='Read':
        p=Path(args.get('file_path',''))
        allowed=p.name=='SKILL.md' and p.parent.name=='skill-of-skills' or p.name=='planning.md' and p.parent.name=='references' and p.parent.parent.name=='skill-of-skills'
        allowed=allowed or phase=='authoring' and authoring_file(str(p),task_dir,context=True)
        return dict(allowed=allowed,reason='读取规划入口；附件由 init 画像、专业原文由 inspect/section 提供')
    if name in ('Glob','ListFiles'):return dict(allowed=True,reason='定位附件和已安装入口，不读取业务内容')
    if name=='PresentToUser':
        paths=args.get('filepaths',[])
        return dict(allowed=phase=='awaiting_delivery' and len(paths)==2 and {Path(p).name for p in paths}=={'plan.html','plan.json'},reason='只交付当前方案的两个附件')
    return dict(allowed=False,reason='本轮未开放该业务处理工具')

def audit(snapshot,plan=None):
    from closing import json_objects,envelope,check_reply,SCHEMA,FAILED,BLOCKED
    import sos
    phase='authoring';violations=[];seen=set();last_reply='';calls={};terminal=None;after_terminal=[];task_dir=None;terminal_origin=None
    for event in snapshot.get('events',[]):
        if event.get('kind')=='assistant_message':
            content=event.get('content',[])
            texts=[b.get('text','') for b in content if b.get('type')=='text']
            if texts:last_reply='\n'.join(texts)
            for b in content:
                if b.get('type')!='tool_use':continue
                ident=b.get('tool_use_id',b.get('id'))
                if ident in seen:continue
                seen.add(ident);calls[ident]=b
                if terminal:after_terminal.append(ident)
                result=check_tool(b['name'],b.get('input',{}),phase,task_dir=task_dir)
                if not result['allowed']:violations.append(dict(call_id=ident,tool=b['name'],reason=result['reason'],category=result.get('category','workflow_drift')))
        elif event.get('kind')=='tool_result':
            raw=event.get('content','');call=calls.get(event.get('tool_use_id'),{})
            command=call.get('input',{}).get('command',call.get('input',{}).get('cmd',''))
            controller=call.get('name') in ('Bash','exec_command') and bool(re.search(r'(?:^|[/\s])flow\.py(?:\s|$)',command))
            source=call.get('input',{}).get('file_path','') if call.get('name')=='Read' else command
            # A terminal read back from the task's saved result is observable
            # even if the host hid the original stdout behind a shell pipeline.
            recorded=bool(task_dir and re.search(re.escape(task_dir)+r'/(?:\.sos-flow-results/[0-9]+\.json|\.sos-terminal\.json)(?:[\s\x22\x27)]|$)',source))
            if not recorded and task_dir and re.search(r'\bcd\s+'+re.escape(str(Path(task_dir).parent))+r'\s+&&',command):
                recorded=bool(re.search(re.escape(Path(task_dir).name)+r'/(?:\.sos-flow-results/[0-9]+\.json|\.sos-terminal\.json)',command))
            if not controller and not recorded:continue
            if isinstance(raw,str):
                for value in json_objects(raw):
                    if terminal:continue
                    if controller and value.get('task_dir'):task_dir=value['task_dir']
                    if not controller and not (value.get('schema')==SCHEMA and check_reply(value,value.get('final_reply',''))['consistent']):continue
                    if value.get('phase') in ('authoring','awaiting_delivery','planning_failed','delivery_blocked'):phase=value['phase']
                    if value.get('phase') in ('planning_failed','delivery_blocked'):
                        message=FAILED if phase=='planning_failed' else BLOCKED
                        terminal=value if value.get('schema')==SCHEMA else envelope(phase,value.get('user_message',message))
                        terminal_origin='controller' if controller else 'saved_result'
                        last_reply=''
                    if value.get('phase')=='delivered' and not event.get('is_error') and plan:
                        message=value.get('final_reply',value.get('user_message',''))
                        if check_response(plan,message)['consistent']:
                            phase='delivered'
                            if value.get('schema')==SCHEMA:
                                if value.get('plan_hash')==sos.digest(plan):terminal=value;last_reply='';terminal_origin='controller' if controller else 'saved_result'
                                else:violations.append(dict(call_id=event.get('tool_use_id'),tool=call['name'],category='terminal_version_mismatch',reason='收尾协议与实际交付方案版本不同'))
                if not terminal and ' finish --files ' in command and not event.get('is_error') and raw.strip() and plan:
                    # Exact canonical text establishes successful v7 completion;
                    # an error string or the call's mere presence never does.
                    clean='\n'.join(line for line in raw.splitlines() if not line.startswith(('mux_client_request_session:', 'ControlSocket '))).strip()
                    if check_response(plan,clean)['consistent']:phase='delivered'
    reply=check_reply(terminal,last_reply) if terminal else check_response(plan,last_reply) if plan else dict(consistent=False,reason='没有可交付方案；按保留现场的失败消息结束')
    return dict(accepted=phase=='delivered' and not violations and reply.get('commitments_consistent',reply['consistent']),phase=phase,tool_violations=violations,
                terminal_observed=terminal is not None,terminal_origin=terminal_origin,post_terminal_calls=after_terminal,
                failure_closed=phase=='planning_failed' and terminal is not None and not after_terminal and reply['consistent'],
                business_analysis_calls=sum(v['category']=='business_analysis' for v in violations),
                workflow_deviations=sum(v['category']!='business_analysis' for v in violations),
                reply=reply,execution_authorized=False,evidence='observed_host_trace',
                enforcement='post_run_audit; pre_dispatch only when host installs check_tool')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('snapshot');ap.add_argument('--plan');ap.add_argument('--out');a=ap.parse_args()
    result=audit(json.loads(Path(a.snapshot).read_text()),json.loads(Path(a.plan).read_text()) if a.plan else None)
    rendered=json.dumps(result,ensure_ascii=False,indent=2)
    if a.out:Path(a.out).write_text(rendered+'\n')
    print(rendered)
if __name__=='__main__':main()
