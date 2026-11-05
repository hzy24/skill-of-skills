#!/usr/bin/env python3
"""Inspect a specific catalog Skill; install only a reviewed, pinned file manifest.

No archive extraction, clone, dependency execution or global Skill installation.
Network readers and the installer share byte, time and request limits.
"""
import argparse, hashlib, json, os, re, shutil, sys, tempfile, time
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse, unquote, quote
from urllib.request import build_opener, HTTPRedirectHandler, Request
from plan_io import edit_lock

MAX_PACKAGE = 10 * 1024 * 1024
MAX_META = 256 * 1024
MAX_FILES = 100
CATALOG_HOSTS = {'claudeskillhub.com','www.claudeskillhub.com','skillhub.cn','www.skillhub.cn'}

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def write(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');os.replace(temp,path)

def https(url, hosts):
    u=urlparse(url)
    if u.scheme!='https' or u.hostname not in hosts or u.username or u.password or u.port not in (None,443) or u.fragment:
        raise ValueError('来源地址不在允许的 HTTPS 域名内：'+url)
    return u

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('来源发生重定向；请核对真实地址后重新提案')

def fetch(url, limit, deadline):
    https(url, CATALOG_HOSTS | {'api.github.com','raw.githubusercontent.com'})
    if time.monotonic()>=deadline:raise ValueError('获取时间预算已用完')
    req=Request(url,headers={'User-Agent':'Skill-of-Skills/1.4','Accept':'application/vnd.github+json','Accept-Encoding':'identity'})
    with build_opener(NoRedirect()).open(req,timeout=min(15,max(1,deadline-time.monotonic()))) as response:
        size=response.headers.get('Content-Length')
        if size and int(size)>limit:raise ValueError('远程文件超过下载上限；未读取正文')
        parts=[];total=0
        while True:
            if time.monotonic()>deadline:raise ValueError('获取时间预算已用完')
            block=response.read(min(32768,limit-total+1))
            if not block:break
            total+=len(block)
            if total>limit:raise ValueError('实际下载超过字节上限，已中止')
            parts.append(block)
        return b''.join(parts)

class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.links.extend(v for k,v in attrs if k=='href' and v)

def safe_rel(value):
    p=PurePosixPath(value)
    if not value or p.is_absolute() or any(x in ('..','.') for x in value.split('/')) or '\\' in value or '%' in value:
        raise ValueError('文件路径需要安全的相对路径')
    return value

def validate(p,require_size=False):
    if not isinstance(p,dict):raise ValueError('安装提案需要对象')
    if p.get('schema')=='sos-tencent-proposal-v1':
        from tencent_source import validate as validate_tencent
        return validate_tencent(p)
    if p.get('schema')=='sos-market-proposal-v1':
        for key in ('name','skill_id','version','catalog_url','reason','solves','dependencies','license','metadata_evidence'):
            if not isinstance(p.get(key),str) or not p[key].strip():raise ValueError('元景市场提案缺少 '+key)
        u=urlparse(p['catalog_url'])
        if u.scheme!='https' or not u.hostname or u.username or u.password:raise ValueError('市场详情需要实际 HTTPS 链接')
        size=p.get('download_bytes')
        if size is None and not require_size:return p
        if type(size) is not int or not 0<size<=MAX_PACKAGE:raise ValueError('市场下载大小未知或超过 10 MiB，先核对再安装')
        return p
    if p.get('schema')!='sos-install-proposal-v1':raise ValueError('需要 acquire inspect 生成的安装提案')
    https(p['catalog_url'],CATALOG_HOSTS)
    if not re.fullmatch(r'[0-9a-f]{40}',p['commit']):raise ValueError('版本需要固定的 Git commit')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',p['repo']):raise ValueError('仓库标识无效')
    safe_rel(p['directory'])
    for key in ('name','reason','solves','dependencies','license'):
        if not isinstance(p.get(key),str) or not p[key].strip():raise ValueError('提案缺少 '+key)
    files=p.get('files')
    if not isinstance(files,list) or not 1<=len(files)<=MAX_FILES:raise ValueError('技能文件清单为空或超过 100 项')
    names=[];total=0
    prefix='https://raw.githubusercontent.com/'+p['repo']+'/'+p['commit']+'/'+p['directory']+'/'
    for f in files:
        path=safe_rel(f['path']);names.append(path)
        if f['url']!=prefix+path:raise ValueError('下载地址与固定目录/版本不一致')
        if type(f['bytes']) is not int or f['bytes']<0:raise ValueError('文件大小未知，先核对再申请安装')
        if not re.fullmatch(r'[0-9a-f]{40}',f['git_blob_sha']):raise ValueError('文件缺少版本校验值')
        total+=f['bytes']
    if len(set(names))!=len(names) or 'SKILL.md' not in names or 'installation.json' in names:raise ValueError('文件清单重复、使用保留文件名或缺少 SKILL.md')
    if total!=p.get('download_bytes') or total>MAX_PACKAGE:raise ValueError('下载总量不匹配或超过 10 MiB；需要单独设计安装方案')
    return p

def inspect(task,catalog,method,reason,solves,dependencies,license_text,reader=fetch):
    task=Path(task).resolve();task.mkdir(parents=True,exist_ok=True)
    https(catalog,CATALOG_HOSTS)
    u=https(method,{'raw.githubusercontent.com','github.com'})
    parts=unquote(u.path).strip('/').split('/')
    if u.hostname=='github.com':
        if len(parts)<6 or parts[2]!='blob':raise ValueError('需要具体技能的 SKILL.md 文件链接；不接受归档或整仓库')
        parts.pop(2)
    if len(parts)<5 or parts[-1]!='SKILL.md' or not re.fullmatch(r'[A-Za-z0-9_.-]+',parts[2]) or u.query:
        raise ValueError('method-url 需要具体技能目录的 SKILL.md；含斜线的分支请提供固定 commit')
    repo='/'.join(parts[:2]);commit=parts[2];directory='/'.join(parts[3:-1]);safe_rel(directory)
    request_hash=digest(dict(catalog=catalog,method=method,reason=reason,solves=solves,dependencies=dependencies,license=license_text))
    cache=task/'.sos-candidates'/('request-'+request_hash+'.json')
    budget=task/'.sos-acquisition.json'
    with edit_lock(budget):
        if cache.exists():
            result=json.loads(cache.read_text());proposal=validate(json.loads(Path(result['proposal']).read_text()))
            if digest(proposal)!=result['proposal_hash']:raise ValueError('候选缓存提案已变化；重新核对来源')
            verify_file(next(f for f in proposal['files'] if f['path']=='SKILL.md'),Path(result['method_file']).read_bytes())
            return dict(result,reused=True)
        b=json.loads(budget.read_text()) if budget.exists() else dict(started=time.time(),attempts=0)
        # Shared with the task discovery clock. Restarting this command does not reset it.
        clock=task/'.sos-planning.json'
        if clock.exists():b['started']=min(b['started'],json.loads(clock.read_text())['started_epoch'])
        if b['attempts']>=3 or time.time()-b['started']>=300:raise ValueError('候选获取预算耗尽；交付已取得的方法或明确能力缺口')
        b['attempts']+=1;write(budget,b)
        deadline=time.monotonic()+min(60,300-(time.time()-b['started']))
        page=reader(catalog,MAX_META,deadline);links=Links();links.feed(page.decode('utf-8',errors='replace'))
        if not any(urlparse(link).hostname=='github.com' and unquote(urlparse(link).path).strip('/').split('/')[:2]==repo.split('/') for link in links.links):
            raise ValueError('技能目录详情页未提供对应仓库链接；不能将其他目录冒记为该来源')
        requests=1
        if not re.fullmatch(r'[0-9a-f]{40}',commit):
            ref=json.loads(reader('https://api.github.com/repos/'+repo+'/git/ref/heads/'+quote(commit,safe=''),MAX_META,deadline));requests+=1
            obj=ref.get('object',{});commit=obj.get('sha','')
            if obj.get('type')!='commit' or not re.fullmatch(r'[0-9a-f]{40}',commit):raise ValueError('分支未解析为固定 commit；请核对具体文件版本')
        method='https://raw.githubusercontent.com/'+repo+'/'+commit+'/'+directory+'/SKILL.md'
        pending=[directory];files=[]
        while pending:
            sub=pending.pop()
            if requests>=12:raise ValueError('目录元数据超过 12 次请求；停止扩大获取范围')
            raw=reader('https://api.github.com/repos/'+repo+'/contents/'+sub+'?ref='+commit,MAX_META,deadline);requests+=1
            entries=json.loads(raw)
            if not isinstance(entries,list):raise ValueError('无法取得具体 Skill 目录清单')
            for e in entries:
                if e.get('submodule_git_url') or e.get('target'):raise ValueError('技能包含子模块或链接，需另行核验')
                path=e.get('path','')
                if not path.startswith(directory+'/'):raise ValueError('目录清单越界')
                rel=safe_rel(path[len(directory)+1:])
                if e.get('type')=='dir':pending.append(path)
                elif e.get('type')=='file':files.append(dict(path=rel,url='https://raw.githubusercontent.com/'+repo+'/'+commit+'/'+path,bytes=e.get('size'),git_blob_sha=e.get('sha')))
                else:raise ValueError('技能含链接或子模块，需要单独核验安装方式')
                if len(files)+len(pending)>MAX_FILES:raise ValueError('目录超过 100 项；不下载整个仓库')
        if not any(f['path']=='SKILL.md' for f in files):raise ValueError('目录缺少 SKILL.md')
        source=reader(method,MAX_META,deadline)
        from method_source import entry
        name,_=entry(source.decode('utf-8'))
        if not name:raise ValueError('技能原文缺少 name')
        p=dict(schema='sos-install-proposal-v1',name=name,catalog_url=catalog,repo=repo,commit=commit,directory=directory,
               reason=reason,solves=solves,dependencies=dependencies,license=license_text,files=files,
               download_bytes=sum(f['bytes'] for f in files),catalog_sha256=hashlib.sha256(page).hexdigest())
        validate(p);verify_file(next(f for f in files if f['path']=='SKILL.md'),source)
        root=task/'.sos-candidates'/digest(p);root.mkdir(parents=True,exist_ok=True)
        (root/'SKILL.md').write_bytes(source);write(root/'proposal.json',p)
        result=dict(proposal=str(root/'proposal.json'),proposal_hash=digest(p),method_file=str(root/'SKILL.md'),download_bytes=p['download_bytes'],
                    status='approval_needed',next='将提案写入方案并展示来源、价值、大小与依赖；收到针对该技能的安装授权后再 install。此处只读取原文和目录元数据。')
        write(cache,result);return result

def verify_file(f,data):
    if 'sha256' in f:
        if len(data)!=f['bytes'] or hashlib.sha256(data).hexdigest()!=f['sha256']:raise ValueError('实际文件大小或版本与用户审阅的提案不一致')
        return
    if len(data)!=f['bytes'] or hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=f['git_blob_sha']:
        raise ValueError('实际文件大小或版本与用户审阅的提案不一致')

def require_install_approval(evidence):
    if not isinstance(evidence,str) or not evidence.strip():raise ValueError('需要具体技能安装授权；普通执行确认不作为安装授权')
    text=evidence.strip().lower()
    if not re.search(r'安装|\binstall(?:ation|ing)?\b',text) or re.search(r'不同意|不允许|不要|不安装|拒绝|取消|禁止|请勿|暂缓|待.{0,8}(同意|授权|确认)|等待.{0,8}(同意|授权|确认)|\b(?:no|not|pending|decline\w*|reject\w*|cancel\w*)\b|don.t',text):
        raise ValueError('该记录未表达安装同意，或包含拒绝；请记录本次具体安装请求与用户肯定答复。普通执行确认不授予安装权限')
    affirmative=r'同意|允许|批准|授权|确认安装|(?:请|帮我|帮忙).{0,12}安装|^安装\s|\b(?:approve[ds]?|agree[ds]?|authorize[ds]?|yes)\b|go ahead|^install\s'
    if text.endswith(('?','？')) or not re.search(affirmative,text):
        raise ValueError('安装建议或问题尚未获得肯定答复；记录具体安装请求与用户同意后继续')

def install(proposal,task,proposal_hash,evidence,reader=fetch):
    from closing import guard_failure
    guard_failure(task)
    p=validate(proposal)
    if p['schema'] not in ('sos-install-proposal-v1','sos-tencent-proposal-v1'):raise ValueError('元景市场技能由宿主市场工具安装；随后 record-market 登记实际结果')
    if proposal_hash!=digest(p):raise ValueError('安装提案已变化，原授权不能复用')
    require_install_approval(evidence)
    if p['schema']=='sos-tencent-proposal-v1' and reader is fetch:
        from tencent_source import fetch as reader
    root=Path(task).resolve()/'.sos-installed';root.mkdir(parents=True,exist_ok=True)
    target=root/proposal_hash
    with edit_lock(root/'install'):
        if target.exists():
            verify_install(p,target);return dict(status='installed',directory=str(target),reused=True)
        temp=Path(tempfile.mkdtemp(prefix='.partial-',dir=root))
        try:
            deadline=time.monotonic()+120
            for f in p['files']:
                data=reader(f['url'],f['bytes'],deadline);verify_file(f,data)
                out=temp/f['path'];out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data)
            write(temp/'installation.json',dict(proposal_hash=proposal_hash,user_authorization=evidence,download_bytes=p['download_bytes'],dependencies_installed=False))
            os.replace(temp,target)
        finally:
            if temp.exists():shutil.rmtree(temp)
    return dict(status='installed',directory=str(target),download_bytes=p['download_bytes'],dependencies_installed=False,
                next='只下载了批准的技能文件；依赖安装和外部数据权限仍需对应授权。用 execute.py ready 核验入口。')

def verify_install(p,target):
    validate(p,require_size=True);target=Path(target)
    receipt=json.loads((target/'installation.json').read_text())
    if receipt.get('proposal_hash')!=digest(p) or not receipt.get('user_authorization'):raise ValueError('缺少当前提案的安装授权记录')
    require_install_approval(receipt['user_authorization'])
    if p['schema']=='sos-market-proposal-v1':
        for key in ('method','record'):
            f=Path(receipt[key+'_path'])
            if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=receipt[key+'_sha256']:raise ValueError('市场安装原文或实际安装记录已变化')
        return
    for f in p['files']:
        path=target/f['path']
        if path.is_symlink() or not path.is_file():raise ValueError('安装文件缺失或被替换')
        verify_file(f,path.read_bytes())

def record_market(p,task,proposal_hash,evidence,method,record):
    from closing import guard_failure
    guard_failure(task)
    validate(p,require_size=True)
    if p['schema']!='sos-market-proposal-v1' or proposal_hash!=digest(p):raise ValueError('需要当前市场安装提案')
    require_install_approval(evidence)
    from method_source import entry,same_name
    method=Path(method).resolve();record=Path(record).resolve()
    if method==record or not record.is_file() or not record.read_bytes().strip():raise ValueError('需要独立的实际市场安装工具结果记录')
    if not same_name(p['name'],entry(method.read_text())[0]):raise ValueError('实际安装技能与提案名称不一致')
    target=Path(task).resolve()/'.sos-installed'/proposal_hash
    receipt=dict(proposal_hash=proposal_hash,user_authorization=evidence,method_path=str(method),record_path=str(record),
                 method_sha256=hashlib.sha256(method.read_bytes()).hexdigest(),record_sha256=hashlib.sha256(record.read_bytes()).hexdigest())
    write(target/'installation.json',receipt);verify_install(p,target)
    return dict(status='host_installation_recorded',directory=str(target),next='ready 将核对方法版本；此记录是宿主工具证据，不代表独立认证。')

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='action',required=True)
    s=sub.add_parser('inspect');s.add_argument('--task-dir',required=True)
    for key in ('catalog-url','method-url','reason','solves','dependencies','license'):s.add_argument('--'+key,required=True)
    s=sub.add_parser('inspect-tencent');s.add_argument('--task-dir',required=True);s.add_argument('--slug',required=True)
    for key in ('reason','solves','dependencies','license'):s.add_argument('--'+key,required=True)
    s=sub.add_parser('install');s.add_argument('proposal');s.add_argument('--task-dir',required=True);s.add_argument('--proposal-hash',required=True);s.add_argument('--evidence',required=True)
    s=sub.add_parser('market');s.add_argument('--metadata',required=True);s.add_argument('--out',required=True)
    s=sub.add_parser('record-market');s.add_argument('proposal');s.add_argument('--task-dir',required=True);s.add_argument('--proposal-hash',required=True);s.add_argument('--evidence',required=True);s.add_argument('--method-file',required=True);s.add_argument('--record',required=True)
    a=ap.parse_args()
    if a.action=='inspect':r=inspect(a.task_dir,a.catalog_url,a.method_url,a.reason,a.solves,a.dependencies,a.license)
    elif a.action=='inspect-tencent':
        from tencent_source import inspect as inspect_tencent
        r=inspect_tencent(a.task_dir,a.slug,a.reason,a.solves,a.dependencies,a.license)
    elif a.action=='market':
        p=validate(json.loads(Path(a.metadata).read_text()))
        if p['schema']!='sos-market-proposal-v1':raise ValueError('需要元景市场提案格式')
        if Path(a.out).exists():raise ValueError('输出已存在；保留用户已审阅的提案')
        write(a.out,p);r=dict(proposal=str(Path(a.out).resolve()),proposal_hash=digest(p),status='approval_needed')
    elif a.action=='record-market':r=record_market(json.loads(Path(a.proposal).read_text()),a.task_dir,a.proposal_hash,a.evidence,a.method_file,a.record)
    else:r=install(json.loads(Path(a.proposal).read_text()),a.task_dir,a.proposal_hash,a.evidence)
    if a.action=='inspect-tencent':
        from method_source import entry,sections
        _,body=entry(Path(r['method_file']).read_text())
        r['method_sections']=[dict(id=s['id'],title=s['title'],preview=s['text'][:100]) for s in sections(body)]
        r['next']='从 method_sections 选与领域判断直接相关的章节，按需读取原文；在 draft.skills 填 method_scope、method_sections、fit_reason 和 input_fit。已给出目录，无需再运行 method_source 获取同一目录。'
    print(json.dumps(r,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:print(str(e),file=sys.stderr);sys.exit(2)
