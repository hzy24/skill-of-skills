#!/usr/bin/env python3
"""Record Yuanjing attachment delivery before accepting plan execution consent."""
import argparse,hashlib,json,re,time
from pathlib import Path
import sos
from plan_io import edit_lock

def location(base):return Path(base)/'.sos-handoff.json'

class HandoffVersionError(ValueError):pass

def verify_page(p,html):
    page=Path(html).read_text()
    if p['id'] not in page:raise HandoffVersionError('HTML 未包含当前方案标识')
    if p.get('message_protocol_version')!=2:return
    data=re.search(r'<script id="plan-data" type="application/json">(.*?)</script>',page,re.S)
    stamp=re.search(r'<script id="plan-hash" type="text/plain">(.*?)</script>',page,re.S)
    try:embedded=json.loads(data.group(1)) if data else None
    except ValueError:embedded=None
    if not stamp or stamp.group(1).strip()!=sos.digest(p) or sos.digest(embedded)!=sos.digest(p):
        raise HandoffVersionError('HTML 与 JSON 不是同一版方案；刷新页面文件后交付最新两个附件')

def resolve_reported_paths(root,paths):
    """Resolve relative host paths; never guess from a basename or accept stale copies."""
    if not isinstance(paths,list) or len(paths)!=2:return paths
    root=Path(root).resolve();bases=[Path.cwd(),root]
    # Yuanjing uses /sessions/<name>/mnt/outputs even for nested task directories.
    for base in root.parents:
        if base.parent.name=='sessions':bases.append(base);break
    resolved=[]
    for value in paths:
        path=Path(value)
        if path.is_absolute():resolved.append(str(path));continue
        if '..' in path.parts:raise ValueError('交付路径包含上级跳转；使用工具返回的原始路径')
        candidates={str((base/path).resolve()) for base in bases if (base/path).is_file()}
        if len(candidates)!=1:raise ValueError('相对交付路径无法唯一定位：'+str(path)+'；使用工具返回的绝对路径')
        resolved.append(candidates.pop())
    return resolved

def record_paths(plan,html,paths):
    """Verify host-reported presented paths against actual files; do not forge raw tool output."""
    plan=Path(plan).resolve();html=Path(html).resolve()
    if not isinstance(paths,list) or len(paths)!=2 or len(set(paths))!=2:raise ValueError('传入 PresentToUser 返回的两个不同 file_path：HTML 和 JSON')
    source={'.html':html,'.json':plan};records=[]
    for item in paths:
        dest=Path(item)
        if not dest.is_absolute() or not dest.is_file() or dest.suffix not in source:raise ValueError('实际交付路径必须是可读取的 HTML / JSON 文件')
        src=source.pop(dest.suffix)
        if hashlib.sha256(dest.read_bytes()).hexdigest()!=hashlib.sha256(src.read_bytes()).hexdigest():raise ValueError('交付副本与当前方案不同：'+dest.name+'；交付最新文件后再登记')
        records.append(dict(source=str(src),presented=str(dest.resolve()),sha256=hashlib.sha256(src.read_bytes()).hexdigest()))
    evidence=plan.parent/'.sos-presented-files.json'
    if evidence in (plan,html):raise ValueError('交付记录路径冲突')
    # Same immutable evidence ledger as raw receipts; the host trace remains the
    # authority for whether PresentToUser was actually called.
    with edit_lock(plan):
        for item in records:
            if any(hashlib.sha256(Path(item[k]).read_bytes()).hexdigest()!=item['sha256'] for k in ('source','presented')):raise ValueError('登记期间文件已变化；重新交付最新版本')
        p=sos.read(plan);sos.require_plan(p)
        verify_page(p,html)
        sos.save(evidence,dict(schema='sos-presented-files-v1',origin='host-reported-paths-verified-on-disk',files=records))
        sos.save(location(plan.parent),dict(plan_id=p['id'],execution_plan=str(plan),delivered_revision=p['revision'],delivered_hash=sos.digest(p),html=str(html),html_sha256=hashlib.sha256(html.read_bytes()).hexdigest(),receipt=str(evidence),receipt_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),delivered_at=time.time()))
    from plan_status import confirmation
    return dict(status='awaiting_user_confirmation',confirmation=confirmation(p))

def record(plan,html,receipt):
    plan=Path(plan).resolve();html=Path(html).resolve();receipt=Path(receipt).resolve()
    if len({plan,html,receipt,location(plan.parent)})!=4:raise ValueError('方案、页面、回执与交付记录需要不同文件')
    with edit_lock(plan):
        p=sos.read(plan);sos.require_plan(p)
        if not html.is_file() or html.suffix.lower()!='.html':raise ValueError('先生成可交付的 HTML 方案')
        page=html.read_text()
        verify_page(p,html)
        raw=receipt.read_text();body=raw
        try:
            envelope=json.loads(raw)
            if isinstance(envelope,dict):
                if envelope.get('is_error') or envelope.get('isError'):raise ValueError('附件交付失败，先补交文件')
                body=envelope.get('content','')
                if isinstance(body,list) and all(isinstance(b,dict) and b.get('type')=='text' and isinstance(b.get('text'),str) for b in body):body='\n'.join(b['text'] for b in body)
                if not isinstance(body,str):raise ValueError('请保存 PresentToUser 的原始文本回执或 tool_result JSON')
        except json.JSONDecodeError:pass
        body=body.replace('\\n','\n')
        delivered=set(re.findall(r'<file_path>([^<]+)</file_path>',body))
        copies=re.findall(r'^Copied (.+?) to (.+)$',body,re.M)
        for file in (plan,html):
            matched=any(Path(dest).is_absolute() and Path(dest).resolve()==file for dest in delivered) or any(Path(src).is_absolute() and Path(src).resolve()==file and dest.strip() in delivered for src,dest in copies)
            if not matched:raise ValueError('附件回执未确认交付 '+file.name+'；用 PresentToUser 补交 HTML 和 JSON，并保存实际回执')
        result=dict(plan_id=p['id'],execution_plan=str(plan),delivered_revision=p['revision'],delivered_hash=sos.digest(p),
                    html=str(html),html_sha256=hashlib.sha256(html.read_bytes()).hexdigest(),receipt=str(receipt),
                    receipt_sha256=hashlib.sha256(receipt.read_bytes()).hexdigest(),delivered_at=time.time())
        sos.save(location(plan.parent),result)
        from plan_status import confirmation
        return dict(status='awaiting_user_confirmation',confirmation=confirmation(p),next='HTML 与 JSON 附件已登记。现在结束规划回复，等待用户审阅或修改后确认执行。不要继续核算、写正文或制作成果。')

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
    name=r'[A-Za-z0-9_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff .:()（）-]{0,199}'
    combined=re.fullmatch(r'同意安装\s+('+name+r'(?:\s*[、,，]\s*'+name+r')*)[，,\s]*(?:并|然后)按(?:最新|修改后)?方案执行[。！!\s]*',text)
    if combined and not any(n.strip() in {'所有技能','全部技能','推荐技能','全部','所有'} for n in re.split('[、,，]',combined.group(1))):return
    prefix=r'(?:(?:好的|好|可以|没问题|同意|确认)[，,。!！\s]*)?'
    action=r'(?:按(?:照)?(?:最新|修改后|调整后|这个|此|该)?(?:的)?方案(?:开始)?执行(?:吧)?|(?:确认|同意|开始)执行(?:方案)?(?:吧)?|执行吧|就这样执行(?:吧)?)'
    english=r'(?:execute|run|proceed with|go ahead with) (?:the |this |updated )?plan'
    if not re.fullmatch(prefix+action+r'[。！!\s]*|'+english+r'[.!\s]*',text,re.I):
        raise ValueError('等待用户针对方案的明确执行确认。初始“准备报告”等任务请求、模型推断或转述不作为确认；记录用户审阅后的执行原话')

def finished(p,base):
    path=Path(base)/'.sos-completion.json'
    if not path.is_file():raise ValueError('交付收尾缺失，先运行 flow.py finish')
    c=sos.read(path);r=delivered(p,base)
    if c.get('status')!='finished' or c.get('plan_id')!=p['id'] or c.get('plan_hash')!=r['delivered_hash'] or c.get('message_hash')!=hashlib.sha256(c.get('user_message','').encode()).hexdigest():
        raise ValueError('交付收尾记录不完整或已变化，先运行 finish 恢复')
    flow=Path(base)/'.sos-flow.json'
    if flow.is_file() and sos.read(flow).get('authoring_contract',0)>=8:
        review=Path(base)/'.sos-reply-review.json'
        if not review.is_file():raise ValueError('交付承诺核对记录缺失；使用 finish --reply 恢复')
        v=sos.read(review)
        if v.get('plan_hash')!=c.get('plan_hash') or v.get('final_reply')!=c.get('user_message'):
            raise ValueError('交付承诺记录与已交付方案不同；使用 finish --reply 恢复')
    return c

def require(p,base,evidence=None,confirm=False):
    if p.get('handoff_protocol_version')!=1:return
    delivered(p,base)
    if p.get('flow_protocol_version')==1:
        flow=sos.read(Path(base)/'.sos-flow.json')
        if flow.get('phase')!='delivered':raise ValueError('规划控制器尚未完成附件登记；运行 flow.py <任务目录> receipt，不跳过交付状态。')
        if flow.get('authoring_contract',0)>=4:finished(p,base)
    if confirm:consent(evidence)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['record']);ap.add_argument('plan');ap.add_argument('--html',required=True);ap.add_argument('--receipt',required=True);a=ap.parse_args()
    print(json.dumps(record(a.plan,a.html,a.receipt),ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:raise SystemExit(str(e))
