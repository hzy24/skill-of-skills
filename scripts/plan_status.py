#!/usr/bin/env python3
"""Derive current review readiness; never treat compilation as user approval."""
import argparse,json

def assess(p):
    needs=p.get('capability_needs',[])
    unresolved=[n for n in needs if n.get('task_kind')!='basic' and
                (n.get('decision',{}).get('kind')!='skill' or n['decision'].get('fit')!='supported')]
    issues=[dict(need=n['id'],reason=n.get('decision',{}).get('method_issue') or n.get('decision',{}).get('reason','能力待选择')) for n in unresolved]
    if p.get('capability_policy_version')==3 and not any(n.get('role')=='core' for n in needs):
        issues.append(dict(need='core',reason='尚未安排核心专业委托'))
    preparation=list(dict.fromkeys(b['skill'] for n in p['nodes'] for b in n['bindings'] if b.get('readiness')!='ready'))
    selected={b['candidate_id'] for n in p['nodes'] for b in n['bindings']}
    installs=[dict(skill=c['name'],proposal_hash=c.get('proposal_hash'),catalog_url=c.get('acquisition',{}).get('catalog_url'),download_bytes=c.get('acquisition',{}).get('download_bytes')) for c in p.get('capability_candidates',[]) if c['id'] in selected and c.get('origin')=='external' and c.get('setup',{}).get('status')!='available']
    if issues:
        status='needs_capability';message='方案可审阅，专业能力待落实；解决所列问题后再确认执行。'
    elif __import__('method_review').pending(p):
        status='needs_method_review';message='方案已生成；专业适配待实质审阅，引用核对通过尚不足以确认执行。'
    elif p.get('selection_needs_review'):
        status='needs_review';message='修改已保存，Agent 需按最新范围复核能力与依赖后执行。'
    elif p.get('open_questions'):
        status='needs_decision';message='方案可审阅，先解决待确认事项，再执行相关工作。'
    elif p.get('mode')=='plan_only':
        status='plan_only';message='当前仅供规划参考。'
    elif any(x['download_bytes'] is None for x in installs):
        status='needs_installation_details';message='方案可审阅；候选技能下载大小待核实，补齐提案后再申请具体安装授权。'
    elif installs:
        status='needs_installation_approval';message='方案可审阅；请先确认列出的具体技能安装提案。普通“按方案执行”不会授权新安装。'
    else:
        status='ready_for_confirmation';message='方案可确认；收到执行指令后，按已有授权完成必要准备并开始工作。'
    return dict(status=status,can_confirm=status=='ready_for_confirmation',message=message,issues=issues,
                preparation=preparation,installation_approval_required=installs,method_quality='来源引用可核对；专业适配与实际交付仍需实质审阅')

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('plan');a=ap.parse_args()
    import sos
    p=sos.read(a.plan);sos.require_plan(p);print(json.dumps(assess(p),ensure_ascii=False,indent=2))
