"""Read names and source excerpts without rewriting a Skill's original bytes."""
import argparse,hashlib,json,re,sys
from pathlib import Path

def entry(text):
    text=text.lstrip('\ufeff').replace('\r\n','\n')
    front=re.match(r'\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)(.*)',text,re.S)
    if not front:return None,''
    line=re.search(r'^name:[ \t]*(.*)$',front.group(1),re.M)
    if not line:return None,front.group(2)
    value=line.group(1).strip()
    quoted=re.fullmatch(r'''(["'])(.*?)\1\s*(?:#.*)?''',value)
    if quoted:value=quoted.group(2)
    else:value=re.split(r'\s+#',value,maxsplit=1)[0].strip()
    # Marketplace entries use Unicode display names, including Chinese. The
    # pinned catalog slug identifies the download; name is never a path.
    if len(value)>200 or not re.fullmatch(r'[\w.-]+(?::[\w.-]+)*',value):return None,front.group(2)
    return value,front.group(2)

def same_name(requested,declared):
    if not declared:return False
    if requested==declared:return True
    # Two qualified names with different namespaces are distinct skills.
    return (':' not in requested or ':' not in declared) and requested.split(':')[-1]==declared.split(':')[-1]

def contains_excerpt(body,excerpt):
    normalize=lambda s:' '.join(s.split())
    return isinstance(excerpt,str) and 12<=len(excerpt.strip())<=1200 and normalize(excerpt) in normalize(body)

def resolve_name(name,skills):
    if name in skills:return skills[name]
    matches=[c for k,c in skills.items() if isinstance(name,str) and same_name(name,k)]
    if len(matches)>1:raise ValueError('技能短名存在多个候选：'+name+'；请使用完整命名空间，不修改原文')
    return matches[0] if matches else None

def sections(body):
    """Index actual Markdown sections; headings inside fenced code are data.

    IDs include position and content hash. Selecting an ID never certifies its
    professional relevance; it only makes the selected source reproducible.
    """
    lines=body.splitlines(keepends=True);starts=[];fence=None
    for i,line in enumerate(lines):
        marker=re.match(r'^\s{0,3}(`{3,}|~{3,})',line)
        if marker:
            value=marker.group(1)
            if fence is None:fence=value
            elif value[0]==fence[0] and len(value)>=len(fence):fence=None
            continue
        if fence:continue
        heading=re.match(r'^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$',line)
        if heading:starts.append((i,heading.group(1)))
        elif i and re.match(r'^\s{0,3}(?:={3,}|-{3,})\s*$',line) and lines[i-1].strip():
            if not starts or starts[-1][0]!=i-1:starts.append((i-1,lines[i-1].strip()))
    if not starts or starts[0][0]>0:starts.insert(0,(0,'正文'))
    result=[]
    for index,(start,title) in enumerate(starts):
        end=starts[index+1][0] if index+1<len(starts) else len(lines)
        text=''.join(lines[start:end]).strip()
        content=re.sub(r'^\s*#{1,6}\s+[^\n]*\n?', '', text).strip()
        if not content or len(text)<12:continue
        digest=hashlib.sha256(text.encode()).hexdigest()
        result.append(dict(id='s'+str(index+1)+'-'+digest[:12],title=title,text=text,sha256=digest))
    return result

def select_sections(body,refs):
    if not isinstance(refs,list) or not refs or any(not isinstance(r,str) or not r.strip() for r in refs):
        raise ValueError('method_sections 需要目录中的章节 ID 列表')
    catalog=sections(body);selected=[]
    for ref in dict.fromkeys(refs):
        matches=[s for s in catalog if ref==s['id'] or ref==s['title']]
        if len(matches)!=1:raise ValueError('method_sections 无法唯一定位：'+ref+'；运行 method_source.py 查看实际章节 ID')
        s=matches[0]
        selected.append(dict(id=s['id'],title=s['title'],sha256=s['sha256'],excerpt=s['text'][:2400]))
    return selected

def verify_evidence(body,evidence):
    if 'sections' not in evidence:return contains_excerpt(body,evidence.get('excerpt'))
    chosen=evidence.get('sections')
    if not isinstance(chosen,list) or not chosen or any(not isinstance(s,dict) or not isinstance(s.get('id'),str) for s in chosen):return False
    try:actual=select_sections(body,[s['id'] for s in chosen])
    except ValueError:return False
    return chosen==actual and evidence.get('excerpt')=='\n\n'.join(s['excerpt'] for s in actual)

def main():
    ap=argparse.ArgumentParser(description='提取真实 Skill 方法目录；选择章节 ID 后由编译器保存原文，无需抄写或翻译引用。')
    ap.add_argument('method_file');ap.add_argument('--sections',nargs='+');ap.add_argument('--out');a=ap.parse_args()
    f=Path(a.method_file).resolve();raw=f.read_bytes();name,body=entry(raw.decode('utf-8'))
    if not name:raise ValueError('需要含 name 的原始 SKILL.md')
    catalog=sections(body)
    if a.sections:
        selected=select_sections(body,a.sections);ids={s['id'] for s in selected}
        items=[dict(id=s['id'],title=s['title'],text=s['text'][:6000],truncated=len(s['text'])>6000) for s in catalog if s['id'] in ids]
    else:items=[dict(id=s['id'],title=s['title'],preview=s['text'][:160]) for s in catalog]
    value=dict(name=name,method_file=str(f),sha256=hashlib.sha256(raw).hexdigest(),sections=items,
               next='选择实际适用的章节 ID 写入 method_sections；fit_reason 与 input_fit 用用户语言解释。完整方法仍以原始文件为准。')
    data=json.dumps(value,ensure_ascii=False,indent=2)
    if a.out:
        if Path(a.out).resolve()==f:raise ValueError('目录输出不能覆盖技能原文')
        Path(a.out).write_text(data,encoding='utf-8')
    print(data)

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,UnicodeError) as e:print(str(e),file=sys.stderr);sys.exit(2)
