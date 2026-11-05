"""Pinned Tencent SkillHub file manifests, using official public file endpoints."""
import json,re,time
from pathlib import Path
from urllib.parse import quote,urlencode,urlparse
from urllib.request import Request,build_opener,HTTPRedirectHandler
from acquire import safe_rel,https,MAX_FILES,MAX_PACKAGE,MAX_META,digest,write,verify_file
from plan_io import edit_lock
API='https://api.skillhub.cn/api/v1/skills/'
OBJECT_HOST='skillhub-1388575217.cos.accelerate.myqcloud.com'

def file_url(slug,version,path):
    return API+quote(slug,safe='')+'/file?'+urlencode(dict(path=path,version=version))

class FileRedirect(HTTPRedirectHandler):
    def __init__(self):super().__init__();self.count=0
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        self.count+=1
        if self.count>2:raise ValueError('文件重定向次数超限')
        https(newurl,{OBJECT_HOST})
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(url,limit,deadline):
    https(url,{'api.skillhub.cn'})
    if not urlparse(url).path.startswith('/api/v1/skills/'):raise ValueError('需要官方技能文件接口')
    if time.monotonic()>=deadline:raise ValueError('获取时间预算已用完')
    with build_opener(FileRedirect()).open(Request(url,headers={'User-Agent':'Skill-of-Skills/1.0.1'}),timeout=min(15,max(1,deadline-time.monotonic()))) as response:
        parts=[];total=0
        while True:
            if time.monotonic()>deadline:raise ValueError('获取时间预算已用完')
            block=response.read(min(32768,limit-total+1))
            if not block:break
            total+=len(block)
            if total>limit:raise ValueError('实际文件超过下载上限')
            parts.append(block)
        return b''.join(parts)

def validate(p):
    for k in ('slug','version','name','reason','solves','dependencies','license'):
        if not isinstance(p.get(k),str) or not p[k].strip():raise ValueError('腾讯提案缺少 '+k)
    if not re.fullmatch(r'[\w.-]+',p['slug']) or not re.fullmatch(r'[\w.+-]+',p['version']):raise ValueError('技能标识或版本无效')
    if p.get('catalog_url')!='https://skillhub.cn/skills/'+quote(p['slug'],safe=''):raise ValueError('腾讯来源与技能标识不一致')
    files=p.get('files')
    if not isinstance(files,list) or not 1<=len(files)<=MAX_FILES:raise ValueError('技能文件数量超限或为空')
    names=[];total=0
    for f in files:
        path=safe_rel(f['path']);names.append(path)
        if f['url']!=file_url(p['slug'],p['version'],path):raise ValueError('文件地址与固定技能版本不一致')
        if type(f['bytes']) is not int or not 0<=f['bytes']<=1024*1024:raise ValueError('单文件大小未知或超过官方预览上限')
        if not re.fullmatch('[0-9a-f]{64}',f.get('sha256','')):raise ValueError('缺少文件 SHA256')
        total+=f['bytes']
    if len(set(names))!=len(names) or 'SKILL.md' not in names or 'installation.json' in names:raise ValueError('文件清单重复、缺少入口或使用保留文件名')
    if total!=p.get('download_bytes') or total>MAX_PACKAGE:raise ValueError('总大小不匹配或超过10 MiB')
    return p

def inspect(task,slug,reason,solves,dependencies,license_text,reader=fetch):
    if not re.fullmatch(r'[\w.-]+',slug):raise ValueError('需要搜索返回的准确 slug')
    task=Path(task).resolve();task.mkdir(parents=True,exist_ok=True)
    cache=task/'.sos-candidates'/('tencent-'+digest([slug,reason,solves,dependencies,license_text])+'.json')
    budget=task/'.sos-acquisition.json'
    with edit_lock(budget):
        if cache.exists():
            result=json.loads(cache.read_text());p=validate(json.loads(Path(result['proposal']).read_text()))
            if digest(p)!=result['proposal_hash']:raise ValueError('缓存提案已变化')
            verify_file(next(f for f in p['files'] if f['path']=='SKILL.md'),Path(result['method_file']).read_bytes())
            return dict(result,reused=True)
        b=json.loads(budget.read_text()) if budget.exists() else dict(started=time.time(),attempts=0)
        clock=task/'.sos-planning.json'
        if clock.exists():b['started']=min(b['started'],json.loads(clock.read_text())['started_epoch'])
        controller=task/'.sos-flow.json'
        state=json.loads(controller.read_text()) if controller.exists() else {}
        modern=state.get('authoring_contract',0)>=7
        # Flow owns the action budget. Model thinking time is not download time,
        # and failed reads must not consume all of the semantic review slots.
        max_attempts=6 if modern else 4 if state.get('authoring_contract',0)>=6 else 3
        if state.get('authoring_contract',0)>=13 and state.get('method_search_used'):max_attempts=8
        action_budget=state.get('authoring_contract',0)>=5
        if b['attempts']>=max_attempts or (not action_budget and time.time()-b['started']>=300):raise ValueError('候选获取预算已用完，请使用本轮已读取的方法')
        b['attempts']+=1;write(budget,b)
        deadline=time.monotonic()+(60 if action_budget else min(60,300-(time.time()-b['started'])))
        base=API+quote(slug,safe='')
        detail=json.loads(reader(base,MAX_META,deadline))
        if detail.get('skill',{}).get('slug')!=slug:raise ValueError('详情返回了不同技能')
        version=detail.get('latestVersion',{}).get('version')
        if not isinstance(version,str) or not re.fullmatch(r'[\w.+-]+',version):raise ValueError('平台未提供固定版本')
        manifest=json.loads(reader(base+'/files?'+urlencode(dict(version=version)),MAX_META,deadline))
        if manifest.get('version')!=version:raise ValueError('文件清单版本不一致')
        files=[dict(path=f['path'],bytes=f['size'],sha256=f['sha256'],url=file_url(slug,version,f['path'])) for f in manifest['files']]
        p=dict(schema='sos-tencent-proposal-v1',slug=slug,version=version,name=slug,catalog_url='https://skillhub.cn/skills/'+quote(slug,safe=''),files=files,
               download_bytes=sum(f['bytes'] for f in files),reason=reason,solves=solves,dependencies=dependencies,license=license_text)
        validate(p)
        entry=next(f for f in files if f['path']=='SKILL.md');source=reader(entry['url'],min(MAX_META,entry['bytes']),deadline);verify_file(entry,source)
        from method_source import entry as method_entry
        name,_=method_entry(source.decode('utf-8'))
        if not name:raise ValueError('技能原文缺少 name')
        p['name']=name;root=task/'.sos-candidates'/digest(p);root.mkdir(parents=True,exist_ok=True)
        (root/'SKILL.md').write_bytes(source);write(root/'proposal.json',p)
        result=dict(status='approval_needed',proposal=str(root/'proposal.json'),proposal_hash=digest(p),method_file=str(root/'SKILL.md'),download_bytes=p['download_bytes'],next='读取方法，说明适配理由并将安装提案放入方案，取得具体安装授权后运行 acquire install。')
        write(cache,result);return result
