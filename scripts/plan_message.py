"""Render the chat handoff from the same live plan used by the HTML and executor."""
import re
from plan_status import assess,confirmation

def render(plan,delivered,blocked_reason=None):
    state=assess(plan);status=state['status']
    if not delivered:
        return dict(readiness=state,user_message='方案文件已生成，附件交付尚未完成。完成交付后再审阅；当前不启动执行。')
    if blocked_reason:
        lines=['规划未完成。已交付 plan.html 和 plan.json，保存了原始需求和问题记录。', '需要修复：'+blocked_reason, '当前方案不可执行。']
    elif status=='ready_for_confirmation':
        lines=['方案已交付：plan.html 和 plan.json。可在页面审阅、修改并保存。']
    elif status=='needs_installation_approval':
        lines=['方案已交付，执行前需要同意以下具体技能安装提案：']
        for item in state['installation_approval_required']:
            size=item.get('download_bytes');size_text=str(size)+' 字节' if size is not None else '大小未核实'
            lines.append('- ['+item['skill']+']('+str(item.get('catalog_url') or '')+')，'+size_text+'。')
    else:
        lines=['方案草稿已交付，当前不可执行。',state['message']]
        lines+=['- '+x['reason'] for x in state['issues']]
        if status=='needs_decision':lines+=['- '+str(x.get('question','')) for x in plan.get('open_questions',[])]
    if not blocked_reason and status in ('ready_for_confirmation','needs_installation_approval') and plan.get('message_protocol_version')==2:
        # Keep the chat handoff short; the editable plan holds the full scope.
        lines[0]='方案 v'+str(plan.get('revision',1))+' 已交付：plan.html 和 plan.json。可在页面审阅、修改并保存。'
        lines.append('计划成果：'+'、'.join(d['title'] for d in plan['deliverables'])+'。详细分工与检查要求见页面。')
        lines.append(confirmation(plan))
    elif not blocked_reason and status in ('ready_for_confirmation','needs_installation_approval'):
        lines.append('本次任务：'+plan['goal'])
        outputs={d['id']:d['title'] for d in plan['deliverables']}
        for node in plan['nodes']:
            skills='、'.join(b['skill'] for b in node['bindings']) or '基础交接'
            products='、'.join(outputs[x] for x in node['outputs'] if x in outputs)
            lines.append('- '+node['title']+'：'+skills+'；交付 '+products+'。')
        lines.append(confirmation(plan))
    return dict(readiness=state,plan_revision=plan.get('revision'),user_message='\n\n'.join(lines))

def presentation_text(value):
    """Ignore inline emphasis only, never URLs, names, numbers or extra claims."""
    if not isinstance(value,str):return None
    value=value.replace('\r\n','\n').strip()
    for pattern in (r'\*\*([^*\n]+)\*\*',r'__([^_\n]+)__',r'`([^`\n]+)`'):
        value=re.sub(pattern,r'\1',value)
    return '\n'.join(line.strip() for line in value.splitlines() if line.strip())

def check_response(plan,message):
    """Acceptance hook for hosts/evaluators with access to the sent chat reply.

    Preparing a reply does not attest that the host sent it. This function never
    awards consistency to an expanded summary merely because files were saved.
    """
    expected=render(plan,True)['user_message']
    # Names and URLs are literal commitments even when they contain Markdown
    # characters. Styling cannot normalize a different filename into equality.
    critical=[d['title'] for d in plan.get('deliverables',[]) if d['title'] in expected]
    critical+=re.findall(r'https?://[^\s)]+',expected)
    missing=[v for v in critical if not isinstance(message,str) or v not in message]
    expected_text=presentation_text(expected);actual_text=presentation_text(message)
    matched=not missing and actual_text==expected_text
    expected_lines=expected_text.splitlines();actual_lines=(actual_text or '').splitlines()
    return dict(consistent=matched,comparison='presentation_only_normalization',
                missing_commitments=missing,
                omitted_lines=[v for v in expected_lines if v not in actual_lines][:8] if not matched else [],
                added_lines=[v for v in actual_lines if v not in expected_lines][:8] if not matched else [],
                reason='与最新方案生成的交付文本一致' if matched else '最终回复偏离方案生成文本；需核对新增事实、范围、判断与授权表述')


def review_reply(plan,draft):
    """Correct a proposed reply before finalizing; never attest to a sent chat."""
    expected=render(plan,True)['user_message']
    verdict=check_response(plan,draft)
    return dict(proposed_reply=draft,consistent=verdict['consistent'],
                action='kept' if verdict['consistent'] else 'replaced_from_plan',
                final_reply=expected,verification='prepared_reply_only',
                commitments=[dict(node=n['id'],skills=[b['skill'] for b in n['bindings']],
                    outputs=[d['title'] for d in plan['deliverables'] if d['id'] in n['outputs']])
                    for n in plan['nodes']])
