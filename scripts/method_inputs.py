"""Verify declared method prerequisites against the original input structure.

This checks references and explicitly supported renames. It does not infer the
business meaning of a column from plausible-looking values or from an LLM claim.
"""
import re
from pathlib import Path

def norm(s):return re.sub(r'[\s_\-]+','',str(s)).lower()

def tabular(profiles):return any(p.get('columns') or p.get('sheets') for p in profiles)

def check(bindings,source,profiles,required=False):
    if not bindings:
        return ['所选方法尚未列明所需输入与原始字段的对应关系'] if required else []
    if not isinstance(bindings,list):return ['方法 inputs 使用对应关系列表']
    errors=[]
    for b in bindings:
        if not isinstance(b,dict):errors.append('方法输入对应关系需要对象');continue
        need=b.get('required');col=b.get('column');index=b.get('input')
        if not isinstance(need,str) or not need.strip() or norm(need) not in norm(source):
            errors.append('required 需引用所选方法原文的实际输入概念');continue
        if not col:errors.append('缺少方法输入：'+need);continue
        if not isinstance(index,int) or isinstance(index,bool) or not 1<=index<=len(profiles):
            errors.append(need+'：输入编号不在已登记材料中');continue
        p=profiles[index-1];sheets=p.get('sheets')
        if sheets:
            selected=[s for s in sheets if s.get('name')==b.get('sheet')]
            if len(selected)!=1:errors.append(need+'：指定实际工作表');continue
            p=selected[0]
        cols=p.get('columns',[])
        if cols.count(col)!=1:errors.append(need+'：原始材料没有唯一字段 '+str(col));continue
        pos=cols.index(col)
        if p.get('rows_scanned',0)==0 or p.get('missing_by_column',[])[pos]>=p['rows_scanned']:
            errors.append(need+'：字段 '+col+' 全空，不能承担此方法');continue
        if norm(need)==norm(col):continue
        # Renaming needs a literal data dictionary/mapping in supplied text.
        # Samples, dates and model-authored input_basis are not semantic evidence.
        evidence=b.get('evidence',{});n=evidence.get('input') if isinstance(evidence,dict) else None
        quote=evidence.get('quote','') if isinstance(evidence,dict) else ''
        if evidence.get('source') is True and isinstance(quote,str) and 0<len(quote)<=600 and quote in source and norm(need) in norm(quote) and norm(col) in norm(quote):continue
        valid=isinstance(n,int) and not isinstance(n,bool) and 1<=n<=len(profiles) and isinstance(quote,str) and 0<len(quote)<=600
        if valid:
            doc=profiles[n-1];path=Path(doc['path'])
            valid=path.suffix.lower() in ('.txt','.md','.json') and path.stat().st_size<=1024*1024
            if valid:
                content=path.read_text(encoding='utf-8-sig')
                valid=quote in content and norm(need) in norm(quote) and norm(col) in norm(quote)
        if not valid:errors.append(need+' 与 '+col+' 的语义对应缺少材料依据；先核实映射或移除此方法')
    return list(dict.fromkeys(errors))

def issues(plan):
    result=[]
    if plan.get('input_contract_version')!=1:return result
    for n in plan.get('capability_needs',[]):
        if n.get('role')!='core' or n.get('decision',{}).get('kind')!='skill':continue
        records=n.get('method_input_checks')
        if not records:result.append(dict(need=n['id'],kind='method_input',reason='核心方法缺少输入适配记录'));continue
        for r in records:
            for reason in r.get('issues',[]):result.append(dict(need=n['id'],kind='method_input',reason=reason))
    return result
