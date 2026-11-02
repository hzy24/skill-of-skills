"""Recognize explicit Skill calls and directly executed Skill scripts.

Reads exported tool-call lists; neither infers adoption from imports nor treats
reading a SKILL.md as execution. Unobserved use requires substantive review.
"""
import argparse, json, re, shlex
from pathlib import Path

def inspect(p,n,calls):
    if not isinstance(calls,list) or any(not isinstance(c,dict) for c in calls):raise ValueError('trace 需要实际工具调用对象列表')
    roots=[]
    for c in p['capability_candidates']:
        m=next(m for m in p['materials'] if m['id']==c['method_support']['material_id'])
        roots.append((str(Path(m['path']).parent).rstrip('/')+'/',c['name']))
    roots.sort(key=lambda x:-len(x[0]))
    bound={b['skill'] for b in n['bindings']};observed=[]
    def register(skill,call,evidence):
        matches=[name for name in bound|{c['name'] for c in p['capability_candidates']} if name==skill or name.split(':')[-1]==skill]
        if len(matches)==1:skill=matches[0]
        observed.append(dict(skill=skill,call_id=call.get('id'),evidence=evidence,bound=skill in bound))
    for call in calls:
        name=call.get('name','');args=call.get('input') or call.get('arguments') or {}
        if not isinstance(args,dict):continue
        if name.lower()=='skill':
            skill=args.get('skill') or args.get('name')
            if isinstance(skill,str):register(skill,call,'Skill '+skill)
        elif name.lower() in ('bash','terminal','exec_command'):
            command=args.get('command') or args.get('cmd') or ''
            try:
                lexer=shlex.shlex(command,posix=True,punctuation_chars=';&|\n');lexer.whitespace=' \t\r';lexer.whitespace_split=True
                tokens=list(lexer)
            except ValueError:continue
            groups=[[]]
            for token in tokens:
                if token and all(c in ';&|\n' for c in token):groups.append([])
                else:groups[-1].append(token)
            for argv in groups:
                if not argv:continue
                executable=Path(argv[0]).name
                target=argv[0]
                if re.fullmatch(r'(python[\d.]*|node|bash|sh)',executable):
                    if len(argv)<2 or argv[1].startswith('-'):continue
                    target=argv[1]
                if not target.startswith('/'):continue
                skill=next((label for root,label in roots if target.startswith(root)),None)
                if not skill:
                    match=re.search(r'/skills/(?:plugins/[^/]+/skills/|private/)?([^/]+)/scripts/',target)
                    if match:skill=match.group(1)
                if skill and skill.split(':')[-1]!='skill-of-skills':register(skill,call,target)
    return dict(observed=observed,unbound=sorted({x['skill'] for x in observed if not x['bound']}),
                not_observed=sorted(bound-{x['skill'] for x in observed}),
                scope='仅识别显式 Skill 调用和直接脚本命令；阅读方法后的应用、包装脚本及运行成败由成果和完整执行记录审阅。')

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('plan');ap.add_argument('trace');ap.add_argument('--node',required=True);a=ap.parse_args()
    p=json.loads(Path(a.plan).read_text());n=next(n for n in p['nodes'] if n['id']==a.node)
    print(json.dumps(inspect(p,n,json.loads(Path(a.trace).read_text())),ensure_ascii=False,indent=2))
