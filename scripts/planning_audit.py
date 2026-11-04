"""Host-call boundary and observed-reply audit for the planning phase.

check_tool can be called BEFORE dispatch by hosts supporting tool hooks. audit
checks a saved trace AFTER dispatch. Installing this Skill alone does not install
a host hook or prevent arbitrary shell tools outside flow.py.
"""
import argparse,json,re,shlex
from pathlib import Path
from plan_message import check_response

ACTIONS={'init','search','inspect','local','section','methods','resource','probe','assess','assign','produce','publish','status','finish'}

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

def check_tool(name,args,phase='authoring',new_request_authorized=False):
    if phase in ('delivered','planning_failed','delivery_blocked'):
        return dict(allowed=False,reason='规划终态之后只发送收尾文本；后续执行等待用户确认')
    if name in ('Bash','exec_command'):
        tokens=controller_tokens(args.get('command',args.get('cmd','')))
        valid=(len(tokens)>=4 and re.fullmatch(r'python(?:3(?:\.\d+)?)?',Path(tokens[0]).name)
               and Path(tokens[1]).name=='flow.py' and tokens[3] in ACTIONS)
        if '--new-request' in tokens and not new_request_authorized:valid=False
        if valid and phase=='awaiting_delivery':valid=tokens[3] in ('status','finish')
        return dict(allowed=bool(valid),reason='规划控制器动作' if valid else '调用超出规划入口；定位文件用目录工具，业务处理留给执行')
    if name=='Skill':return dict(allowed=args.get('skill')=='skill-of-skills',reason='首轮仅加载 SoS，所选专业技能在确认后执行')
    if name=='Read':
        p=Path(args.get('file_path',''))
        allowed=p.name=='SKILL.md' and p.parent.name=='skill-of-skills' or p.name=='planning.md' and p.parent.name=='references' and p.parent.parent.name=='skill-of-skills'
        return dict(allowed=allowed,reason='读取规划入口；附件由 init 画像、专业原文由 inspect/section 提供')
    if name in ('Glob','ListFiles'):return dict(allowed=True,reason='定位附件和已安装入口，不读取业务内容')
    if name=='PresentToUser':
        paths=args.get('filepaths',[])
        return dict(allowed=phase=='awaiting_delivery' and len(paths)==2 and {Path(p).name for p in paths}=={'plan.html','plan.json'},reason='只交付当前方案的两个附件')
    return dict(allowed=False,reason='本轮未开放该业务处理工具')

def audit(snapshot,plan=None):
    phase='authoring';violations=[];seen=set();last_reply='';calls={}
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
                result=check_tool(b['name'],b.get('input',{}),phase)
                if not result['allowed']:violations.append(dict(call_id=ident,tool=b['name'],reason=result['reason']))
        elif event.get('kind')=='tool_result':
            raw=event.get('content','');call=calls.get(event.get('tool_use_id'),{})
            if call.get('name')!='Bash' or 'flow.py' not in call.get('input',{}).get('command',''):continue
            if isinstance(raw,str):
                for line in raw.splitlines():
                    try:value=json.loads(line)
                    except ValueError:continue
                    if isinstance(value,dict) and value.get('phase') in ('authoring','awaiting_delivery','planning_failed','delivery_blocked'):phase=value['phase']
                    if isinstance(value,dict) and value.get('phase')=='delivered' and not event.get('is_error') and plan:
                        message=value.get('final_reply',value.get('user_message',''))
                        if check_response(plan,message)['consistent']:phase='delivered'
                if ' finish --files ' in call['input']['command'] and not event.get('is_error') and raw.strip() and plan:
                    # Exact canonical text establishes successful v7 completion;
                    # an error string or the call's mere presence never does.
                    clean='\n'.join(line for line in raw.splitlines() if not line.startswith(('mux_client_request_session:', 'ControlSocket '))).strip()
                    if check_response(plan,clean)['consistent']:phase='delivered'
    reply=check_response(plan,last_reply) if plan else dict(consistent=False,reason='没有可交付方案；按保留现场的失败消息结束')
    return dict(accepted=phase=='delivered' and not violations and reply['consistent'],phase=phase,tool_violations=violations,
                reply=reply,execution_authorized=False,evidence='observed_host_trace',
                enforcement='post_run_audit; pre_dispatch only when host installs check_tool')

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('snapshot');ap.add_argument('--plan');ap.add_argument('--out');a=ap.parse_args()
    result=audit(json.loads(Path(a.snapshot).read_text()),json.loads(Path(a.plan).read_text()) if a.plan else None)
    rendered=json.dumps(result,ensure_ascii=False,indent=2)
    if a.out:Path(a.out).write_text(rendered+'\n')
    print(rendered)
if __name__=='__main__':main()
