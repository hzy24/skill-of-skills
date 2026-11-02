#!/usr/bin/env python3
"""Record Yuanjing attachment delivery before accepting plan execution consent."""
import argparse,hashlib,json,re,time
from pathlib import Path
import sos
from plan_io import edit_lock

def location(base):return Path(base)/'.sos-handoff.json'

def record(plan,html,receipt):
    plan=Path(plan).resolve();html=Path(html).resolve();receipt=Path(receipt).resolve()
    if len({plan,html,receipt,location(plan.parent)})!=4:raise ValueError('方案、页面、回执与交付记录需要不同文件')
    with edit_lock(plan):
        p=sos.read(plan);sos.require_plan(p)
        if not html.is_file() or html.suffix.lower()!='.html':raise ValueError('先生成可交付的 HTML 方案')
        page=html.read_text()
        if p['id'] not in page:raise ValueError('HTML 未包含当前方案标识，请重新生成当前方案页面')
        raw=receipt.read_text();body=raw
        try:
            envelope=json.loads(raw)
            if isinstance(envelope,dict):
                if envelope.get('is_error') or envelope.get('isError'):raise ValueError('附件交付失败，先补交文件')
                body=envelope.get('content','')
                if not isinstance(body,str):raise ValueError('请保存 PresentToUser 的原始文本回执或 tool_result JSON')
        except json.JSONDecodeError:pass
        body=body.replace('\\n','\n')
        delivered=set(re.findall(r'<file_path>([^<]+)</file_path>',body))
        copies=re.findall(r'^Copied (.+?) to (.+)$',body,re.M)
        for file in (plan,html):
            matched=any(Path(src).is_absolute() and Path(src).resolve()==file and dest.strip() in delivered for src,dest in copies)
            if not matched:raise ValueError('附件回执未确认交付 '+file.name+'；用 PresentToUser 补交 HTML 和 JSON，并保存实际回执')
        result=dict(plan_id=p['id'],execution_plan=str(plan),delivered_revision=p['revision'],delivered_hash=sos.digest(p),
                    html=str(html),html_sha256=hashlib.sha256(html.read_bytes()).hexdigest(),receipt=str(receipt),
                    receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),delivered_at=time.time())
        sos.save(location(plan.parent),result)
        return dict(status='awaiting_user_confirmation',next='HTML 与 JSON 附件已登记。现在结束规划回复，等待用户审阅或修改后确认执行。不要继续核算、写正文或制作成果。')

def delivered(p,base):
    path=location(base)
    if not path.is_file():raise ValueError('方案尚未交付：先用 PresentToUser 交付 plan.html 与 plan.json，再运行 handoff.py record 登记实际回执')
    r=sos.read(path)
    if r.get('plan_id')!=p['id'] or Path(r.get('execution_plan','')).parent.resolve()!=Path(base).resolve():raise ValueError('交付记录属于其他方案')
    plan=Path(r['execution_plan'])
    if not plan.is_file() or sos.digest(sos.read(plan))!=sos.digest(p):raise ValueError('请读取交付记录指向的最新 plan.json，不使用旧快照或副本执行')
    receipt=Path(r['receipt'])
    if not receipt.is_file() or hashlib.sha256(receipt.read_bytes()).hexdigest()!=r['receipt_sha256']:raise ValueError('附件交付回执缺失或已变化')
    return r

def consent(evidence):
    if not isinstance(evidence,str):raise ValueError('等待用户审阅方案后的明确执行确认')
    text=evidence.strip().strip('“”\"').strip()
    # Recognize a short affirmative instruction; quoted authorization narratives
    # and the initial business request do not qualify as post-plan consent.
    prefix=r'(?:(?:好的|好|可以|没问题|同意|确认)[，,。!！\s]*)?'
    action=r'(?:按(?:照)?(?:最新|修改后|调整后|这个|此|该)?(?:的)?方案(?:开始)?执行(?:吧)?|(?:确认|同意|开始)执行(?:方案)?(?:吧)?|执行吧|就这样执行(?:吧)?)'
    english=r'(?:execute|run|proceed with|go ahead with) (?:the |this |updated )?plan'
    if not re.fullmatch(prefix+action+r'[。！!\s]*|'+english+r'[.!\s]*',text,re.I):
        raise ValueError('等待用户针对方案的明确执行确认。初始“准备报告”等任务请求、模型推断或转述不作为确认；记录用户审阅后的执行原话')

def require(p,base,evidence=None,confirm=False):
    if p.get('handoff_protocol_version')!=1:return
    delivered(p,base)
    if confirm:consent(evidence)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['record']);ap.add_argument('plan');ap.add_argument('--html',required=True);ap.add_argument('--receipt',required=True);a=ap.parse_args()
    print(json.dumps(record(a.plan,a.html,a.receipt),ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:raise SystemExit(str(e))
