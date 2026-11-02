"""Compile business assignments into the existing editable execution protocol.

The author supplies scope, specialist evidence and acceptance criteria. IDs,
ownership, contracts, dependencies and format checks are mechanical derivatives.
"""
import hashlib
from pathlib import Path
from method_source import entry,same_name,contains_excerpt,resolve_name,select_sections


def expand(d, base=None):
    errors=[]
    if type(d.get('draft_version')) is not int or d['draft_version']!=2:errors.append('draft_version 需要整数 2')
    def known(x,keys,at):
        for key in x:
            if key not in keys:errors.append(at+'.'+key+' 不是业务草案字段；结构字段由编译器生成')
    known(d,{'draft_version','id','title','goal','mapping','inputs','skills','work','mode','constraints','assumptions','open_questions','final_checks'},'draft')
    def obj(x, at):
        if not isinstance(x,dict): errors.append(at+' 需要对象');return {}
        return x
    def txt(x, at):
        if not isinstance(x,str) or not x.strip():errors.append(at+' 需要非空文本');return ''
        return x.strip()
    def seq(x, at, nonempty=True):
        if not isinstance(x,list) or (nonempty and not x):errors.append(at+' 需要'+('非空' if nonempty else '')+'列表');return []
        return x
    def texts(x, at):
        if isinstance(x,str):x=[x]
        return [txt(v,at+'['+str(i)+']') for i,v in enumerate(seq(x,at))]
    title=txt(d.get('title'),'title');goal=txt(d.get('goal'),'goal')
    for key in ('constraints','assumptions','open_questions'):
        for value in seq(d.get(key,[]),key,False):txt(value,key)
    mapping=obj(d.get('mapping'),'mapping')
    known(mapping,{'domain','action','input_condition','capabilities'},'mapping')
    for k in ('domain','action','input_condition'):txt(mapping.get(k),'mapping.'+k)
    texts(mapping.get('capabilities'),'mapping.capabilities')
    materials=[];names={};candidates=[];skills={};bodies={};defaults={};requirements=[];outlines=[];nodes=[];needs=[];deliverables=[]
    def register(name, ident, at):
        if name in names:errors.append(at+' 名称重复：'+name)
        names[name]=ident
    for i,raw in enumerate(seq(d.get('inputs'),'inputs'),1):
        at='inputs['+str(i-1)+']';x=obj(raw,at);name=txt(x.get('name'),at+'.name');path=txt(x.get('path'),at+'.path')
        known(x,{'name','path'},at)
        ident='M'+str(i);register(name,ident,at);materials.append(dict(id=ident,title=name,path=path))
    for i,raw in enumerate(seq(d.get('skills',[]),'skills',False),1):
        at='skills['+str(i-1)+']';x=obj(raw,at);name=txt(x.get('name'),at+'.name')
        known(x,{'name','source','method_file','workflow','checks','fit_reason','input_fit','version','license','installation','method_excerpt','method_sections','origin','proposal'},at)
        if name in skills:errors.append(at+' 技能名称重复：'+name)
        values={k:txt(x.get(k),at+'.'+k) for k in ('source','method_file','fit_reason','input_fit')}
        values['workflow']=txt(x.get('workflow','遵循所选 Skill 的完整方法；本次依据见自动提取的原文章节'),at+'.workflow')
        values['checks']=txt(x.get('checks','执行原文要求的检查，并核对本次委托的成果标准'),at+'.checks')
        mid='S'+str(i);cid='C'+str(i)
        materials.append(dict(id=mid,title=name+' 方法原文',path=values['method_file']))
        support=dict(material_id=mid,workflow=values['workflow'],checks=values['checks'])
        if base is not None and values['method_file']:
            f=Path(values['method_file']);f=f if f.is_absolute() else Path(base)/f
            if not f.is_file():errors.append(at+'.method_file 原文文件不存在；未读到技能原文时将工作 skill 留空并填写 gap')
            else:
                raw_method=f.read_bytes()
                if not raw_method.strip():errors.append(at+'.method_file 原文为空')
                declared,body=entry(raw_method.decode('utf-8',errors='replace'))
                if not same_name(name,declared):errors.append(at+'.method_file 需要所选 Skill 的原始说明（name 与所选技能一致）；登记名='+name+'，原文名='+str(declared)+'。使用正确原文或登记名，不修改原文。')
                elif ':' in declared:name=declared
                bodies[cid]=body
                support['sha256']=hashlib.sha256(raw_method).hexdigest()
                support['declared_name']=declared
        c=dict(id=cid,name=name,source=values['source'],version=x.get('version','未记录版本'),license=x.get('license','待核对授权'),
               evidence=[dict(kind='method',locator=values['method_file'],finding=values['fit_reason']+'；输入适配：'+values['input_fit'])],
               setup=dict(status='blocked',dependencies=x.get('installation','执行前核对技能依赖'),permissions='沿用用户授权范围',verification='规划只核对方法；执行前核验入口和依赖'),method_support=support)
        origin=x.get('origin','external' if any(t in values['source'].lower() for t in ('https://','http://','github','skillhub')) else 'installed')
        if origin not in ('external','installed'):errors.append(at+'.origin 需要 installed 或 external')
        c['origin']=origin
        if origin=='external':
            try:
                import json
                from acquire import validate,digest,verify_file
                proposal_path=Path(txt(x.get('proposal'),at+'.proposal'))
                if not proposal_path.is_absolute():proposal_path=Path(base or '.')/proposal_path
                proposal=validate(json.loads(proposal_path.read_text()))
                if not same_name(name,proposal['name']):raise ValueError('安装提案与技能名不一致')
                if base is not None and proposal['schema'] in ('sos-install-proposal-v1','sos-tencent-proposal-v1'):
                    method_path=Path(values['method_file'])
                    if not method_path.is_absolute():method_path=Path(base)/method_path
                    verify_file(next(item for item in proposal['files'] if item['path']=='SKILL.md'),method_path.read_bytes())
                c['acquisition']=proposal
                c['proposal_hash']=digest(proposal)
                c['source']=proposal['catalog_url']
                if proposal['schema']=='sos-install-proposal-v1':c['source']+=' → https://github.com/'+proposal['repo']+'/tree/'+proposal['commit']+'/'+proposal['directory']
                c['version']=proposal.get('commit',proposal.get('version'));c['license']=proposal['license']
                c['setup'].update(status='approval_needed',installation=c['source'],request_reason=proposal['reason'],
                                  dependencies=proposal['dependencies'],permissions='仅安装提案列出的技能文件；用户单独确认安装',fallback='暂不安装时保留方案，等待能力落实')
            except (ValueError,KeyError,TypeError,OSError) as e:errors.append(at+' 外部安装提案无效：'+str(e))
        if name in skills:errors.append(at+' 解析后的技能名称重复：'+name)
        candidates.append(c);skills[name]=c;defaults[cid]=x
    work=seq(d.get('work'),'work')
    # Resolve business names first so cross-module inputs derive dependencies.
    for i,raw in enumerate(work,1):
        x=obj(raw,'work['+str(i-1)+']')
        for j,output in enumerate(seq(x.get('deliverables'),'work['+str(i-1)+'].deliverables'),1):
            if not isinstance(output,dict):
                errors.append('work['+str(i-1)+'].deliverables['+str(j-1)+'] 需要对象，例如 {"title":"成果名称","format":"md","criteria":["本次具体验收条件"]}；不能只写成果名称')
                continue
            o=obj(output,'deliverable');name=txt(o.get('title'),'deliverable.title')
            register(name,'D'+str(i)+'_'+str(j),'deliverable')
    for i,raw in enumerate(work,1):
        at='work['+str(i-1)+']';x=obj(raw,at);nid='N'+str(i);rid='R'+str(i);bid='B'+str(i);needid='need-'+str(i)
        known(x,{'title','role','skill','inputs','questions','deliverables','gap','reason','method_excerpt','method_sections'},at)
        name=txt(x.get('title'),at+'.title');questions=texts(x.get('questions'),at+'.questions')
        role=x.get('role','core')
        if role not in ('core','support','basic'):errors.append(at+'.role 需要 core / support / basic')
        inputs=[]
        for ref in texts(x.get('inputs'),at+'.inputs'):
            if ref not in names:errors.append(at+'.inputs 未知材料或成果：'+ref)
            else:inputs.append(names[ref])
        chosen=x.get('skill');candidate=resolve_name(chosen,skills) if isinstance(chosen,str) else None
        if chosen is not None and not candidate:errors.append(at+'.skill 未在 skills 中登记：'+str(chosen))
        gap=x.get('gap','')
        if role!='basic' and not candidate:txt(gap,at+'.gap（未选到技能时说明缺口及下一步）')
        outputs=[];checks=[]
        for j,output in enumerate(seq(x.get('deliverables'),at+'.deliverables'),1):
            if not isinstance(output,dict):continue
            o=obj(output,at+'.deliverables');oid='D'+str(i)+'_'+str(j);outputs.append(oid)
            known(o,{'title','format','criteria','pages'},at+'.deliverables['+str(j-1)+']')
            fmt=txt(o.get('format'),at+'.deliverables.format').lower().lstrip('.')
            criteria=texts(o.get('criteria'),at+'.deliverables.criteria')
            deliverables.append(dict(id=oid,title=o.get('title',''),description='；'.join(questions),format=fmt,outline_ids=[bid],outline_level='sections'))
            checks.append(dict(id=nid+'-review-'+str(j),kind='review',artifact=oid,criteria='；'.join(criteria)))
            if 'pages' in o:
                if fmt!='pptx' or type(o['pages']) is not int or o['pages']<1:errors.append(at+'.deliverables.pages 仅用于 PPTX 的明确正整数页数')
                else:checks.append(dict(id=nid+'-pages-'+str(j),kind='pptx_pages',artifact=oid,value=o['pages']))
        standard='；'.join(questions)
        requirements.append(dict(id=rid,text=standard))
        outlines.append(dict(id=bid,title=name,claim=standard,points=questions,sources=inputs or ['用户需求'],visual='由负责技能确定成果内部结构',acceptance=[c['criteria'] for c in checks if 'criteria' in c]))
        source_defaults=defaults.get(candidate['id'],{}) if candidate else {}
        selection=x if 'method_sections' in x or 'method_excerpt' in x else source_defaults
        excerpt=selection.get('method_excerpt');evidence={};method_issue=''
        if candidate:
            body=bodies.get(candidate['id'],'')
            if 'method_sections' in selection:
                try:
                    chosen_sections=select_sections(body,selection['method_sections'])
                    evidence['sections']=chosen_sections;excerpt='\n\n'.join(s['excerpt'] for s in chosen_sections)
                except ValueError as e:method_issue=str(e)
            elif not contains_excerpt(body,excerpt):
                method_issue='方法引用待定位：运行 method_source.py 查看原文章节，将所选 ID 写入 method_sections；中文解释保留在 fit_reason。'
        grounded=bool(candidate and not method_issue)
        decision=dict(kind='skill' if candidate else ('direct' if role=='basic' else 'deferred'),
                      reason=(candidate['evidence'][0]['finding'] if candidate else (gap or '基础材料交接')),application=standard)
        bindings=[]
        if candidate:
            decision.update(candidate_id=candidate['id'],fit='supported' if role!='core' or grounded else 'unverified')
            if role=='core' and not grounded:
                decision['method_issue']=method_issue
                decision['reason']='方法适配待核验：'+method_issue
            bindings=[dict(skill=candidate['name'],candidate_id=candidate['id'],readiness='needs_setup' if candidate.get('origin')=='external' else 'unknown',scope=standard,reason=decision['reason'],contract=dict(inherit='node',invocation='读取 '+candidate['method_support']['material_id']+' 的 Skill 原文，按完整流程处理本模块；宿主按实际入口调用'))]
        needs.append(dict(id=needid,role=role,task_kind='basic' if role=='basic' else ('professional' if role=='core' else 'production'),requirement_ids=[rid],outline_ids=[bid],standard=standard,existing_assessment=decision['reason'],decision=decision))
        if grounded:needs[-1]['method_evidence']=dict(evidence,material_id=candidate['method_support']['material_id'],excerpt=excerpt,source_sha256=candidate['method_support'].get('sha256',''))
        nodes.append(dict(id=nid,title=name,description=standard,reason=x.get('reason',decision['reason']),method='skill' if candidate else 'direct',inputs=inputs,outputs=outputs,requirements=[rid],outline_ids=[bid],capability_need_ids=[needid],checks=checks,bindings=bindings))
    if not any(n['role']=='core' for n in needs):errors.append('work 至少需要一个 role=core 的核心业务委托')
    if errors:raise ValueError('\n'.join(dict.fromkeys(errors)))
    if base is not None:
        for material in materials:
            path=Path(material['path']);material['path']=str((path if path.is_absolute() else Path(base)/path).resolve())
    result=dict(id=d.get('id','task-'+hashlib.sha256((title+goal).encode()).hexdigest()[:10]),title=title,goal=goal,
                mode=d.get('mode','execute_after_confirmation'),mapping=mapping,requirements=requirements,materials=materials,
                capability_candidates=candidates,capability_needs=needs,nodes=nodes,deliverables=deliverables,content_outline=outlines,
                constraints=d.get('constraints',[]),assumptions=d.get('assumptions',[]),open_questions=d.get('open_questions',[]),method_evidence_version=1)
    from review_routing import route
    route(result,d.get('final_checks',[]))
    return result
