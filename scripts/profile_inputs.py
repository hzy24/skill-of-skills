#!/usr/bin/env python3
"""Bounded input reconnaissance; deliberately provides no business analysis."""
import argparse,csv,json,zipfile,io,re,shutil,subprocess,tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

NS='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

def xlsx_tables(path,sheet=None):
    """Bounded structure reads; never execute formulas or load workbook macros."""
    with zipfile.ZipFile(path) as z:
        def read(name):
            if z.getinfo(name).file_size>8*1024*1024:raise ValueError('工作表结构超过 8 MiB；按任务相关工作表提供精简材料')
            return z.read(name)
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(x.itertext()) for x in ET.fromstring(read('xl/sharedStrings.xml')).findall(NS+'si')]
        rels={x.attrib['Id']:x.attrib['Target'] for x in ET.fromstring(read('xl/_rels/workbook.xml.rels'))}
        sheets=ET.fromstring(read('xl/workbook.xml')).findall('.//'+NS+'sheet')
        if len(sheets)>10 and sheet is None:raise ValueError('工作簿超过10张表；先指定相关表名')
        for sh in sheets:
            title=sh.attrib['name']
            if sheet is not None and sheet!=title:continue
            target=rels[sh.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
            filename=target.lstrip('/') if target.startswith('/') else 'xl/'+target
            if '..' in filename.split('/'):raise ValueError('工作表路径不合法')
            rows=[]
            for _,row in ET.iterparse(io.BytesIO(read(filename)),events=('end',)):
                if row.tag!=NS+'row':continue
                values=[]
                for cell in row.findall(NS+'c'):
                    match=re.match('[A-Z]+',cell.attrib.get('r','A1'));col=0
                    for char in match.group():col=col*26+ord(char)-64
                    if col>100:raise ValueError('工作表超过100列；提供任务相关字段')
                    while len(values)<col:values.append('')
                    v=cell.find(NS+'v');value=v.text if v is not None else ''
                    if cell.attrib.get('t')=='s':value=strings[int(value)]
                    elif cell.attrib.get('t')=='inlineStr':value=''.join(cell.find(NS+'is').itertext())
                    elif cell.find(NS+'f') is not None and not value:value='[公式无缓存]'
                    values[col-1]=value or ''
                rows.append(values);row.clear()
                if len(rows)>=10002:break
            yield title,rows

def row_profile(rows,max_rows=10000):
    rows=iter(rows);header=next(rows,[])
    if len(header)>100:raise ValueError('列数超过100；请按任务相关字段读取结构')
    missing=[0]*len(header);samples=[];count=0;malformed=0;limited=False
    kinds=[set() for _ in header];unique=[set() for _ in header];dates=[[] for _ in header]
    for row in rows:
        if count>=max_rows:limited=True;break
        count+=1;malformed+=len(row)!=len(header)
        for i in range(len(header)):
            value=str(row[i]).strip() if i<len(row) else '';missing[i]+=not value
            if not value:continue
            if len(unique[i])<=100:unique[i].add(value)
            try:float(value);kinds[i].add('number');continue
            except ValueError:pass
            try:
                d=datetime.fromisoformat(value.replace('Z','+00:00').replace('/','-'))
                kinds[i].add('date');dates[i].append(d.date().isoformat())
            except ValueError:kinds[i].add('text')
        if len(samples)<3:samples.append([str(v)[:100] for v in row[:len(header)]])
    structure=[dict(column=c,types=sorted(kinds[i]),distinct_count=len(unique[i]) if len(unique[i])<=100 else None,
                    distinct_count_capped=len(unique[i])>100,
                    date_range=[min(dates[i]),max(dates[i])] if dates[i] else None) for i,c in enumerate(header)]
    return dict(columns=header,rows_scanned=count,row_count_exact=not limited,missing_by_column=missing,sample_rows=samples,malformed_rows=malformed,column_structure=structure)

def probe(path,column,kind,sheet=None):
    if kind not in ('types','date_range','labels'):raise ValueError('规划探查只支持 types / date_range / labels；业务聚合交给执行阶段')
    path=Path(path)
    if path.suffix.lower()=='.xlsx':
        tables=list(xlsx_tables(path,sheet))
        if len(tables)!=1:raise ValueError('用 --sheet 指定一个实际工作表')
        rows=iter(tables[0][1]);handle=None
    elif path.suffix.lower() in ('.csv','.tsv'):
        handle=path.open(encoding='utf-8-sig',newline='');rows=csv.reader(handle,delimiter='\t' if path.suffix.lower()=='.tsv' else ',')
    else:raise ValueError('结构探查支持 CSV、TSV、XLSX')
    try:
        header=next(rows,[])
        if header.count(column)!=1:raise ValueError('column 需要唯一的原始列名')
        index=header.index(column);counts=dict(empty=0,number=0,date=0,text=0);dates=[];limited=False;count=0;labels=set();labels_limited=False
        for row in rows:
            if count>=10000:limited=True;break
            count+=1;v=row[index].strip() if index<len(row) else ''
            if v:
                if len(labels)<20:labels.add(v[:150])
                elif v[:150] not in labels:labels_limited=True
            if not v:counts['empty']+=1;continue
            try:float(v);counts['number']+=1;continue
            except ValueError:pass
            try:d=datetime.fromisoformat(v.replace('Z','+00:00').replace('/','-'));dates.append(d.date().isoformat());counts['date']+=1
            except ValueError:counts['text']+=1
        result=dict(column=column,kind=kind,rows_scanned=count,row_count_exact=not limited,types=counts)
        if kind=='labels':return dict(column=column,kind=kind,values=sorted(labels),truncated=labels_limited or limited,note='最多20项取值，不提供频次、分组或排名')
        if kind=='date_range':result.update(earliest=min(dates) if dates else None,latest=max(dates) if dates else None,note='仅 ISO 日期或斜杠年月日；数字日期保留原类型，业务口径由执行技能确定')
        return result
    finally:
        if handle:handle.close()

def document_profile(path,section=None):
    try:return _document_profile(path,section)
    except (zipfile.BadZipFile,ET.ParseError,UnicodeError,subprocess.SubprocessError) as e:
        raise ValueError('材料结构读取失败：'+str(e)[:300]) from e

def _document_profile(path,section=None):
    """Bounded document reading, never model-generated code or business queries."""
    path=Path(path);suffix=path.suffix.lower();parts=[];headings=[];limited=False
    if section is not None and section<1:raise ValueError('section 使用目录中的正整数编号')
    if path.stat().st_size>32*1024*1024:raise ValueError('文档超过32 MiB；先提供任务相关章节')
    if suffix in ('.docx','.pptx'):
        with zipfile.ZipFile(path) as z:
            names=['word/document.xml'] if suffix=='.docx' else sorted((n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)),key=lambda n:int(re.search(r'(\d+)\.xml',n).group(1)))[:50]
            for name in names:
                if z.getinfo(name).file_size>8*1024*1024:raise ValueError('章节 XML 超过8 MiB')
                root=ET.fromstring(z.read(name));ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}' if suffix=='.docx' else '{http://schemas.openxmlformats.org/drawingml/2006/main}'
                if suffix=='.pptx':headings.append((len(parts),'幻灯片 '+str(len(headings)+1)))
                for para in root.iter(ns+'p'):
                    text=''.join(t.text or '' for t in para.iter(ns+'t')).strip()
                    if not text:continue
                    if suffix=='.docx':
                        style=para.find('.//'+ns+'pStyle');val=style.get(ns+'val','') if style is not None else ''
                        if re.search(r'heading|标题',val,re.I):headings.append((len(parts),text[:180]))
                    parts.append(text[:6000])
                    if len(parts)>=3000:limited=True;break
                if limited:break
    elif suffix=='.pdf':
        binary=shutil.which('pdftotext')
        if binary:
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'text.txt'
                result=subprocess.run([binary,'-f','1','-l','20','-layout','-enc','UTF-8',str(path.resolve()),str(out)],capture_output=True,timeout=20)
                if result.returncode:raise ValueError('PDF 文本提取失败：'+result.stderr.decode(errors='replace')[:300])
                with out.open(encoding='utf-8') as stream:body=stream.read(150000)
        else:
            try:from pypdf import PdfReader
            except ImportError:raise ValueError('读取 PDF 结构需要 pdftotext 或 pypdf；当前环境没有可用解析器')
            try:
                reader=PdfReader(path);body='\f'.join((p.extract_text() or '')[:10000] for p in reader.pages[:20])
            except Exception as e:raise ValueError('PDF 结构读取失败：'+str(e)[:300]) from e
        for page in body.split('\f'):
            if page.strip():headings.append((len(parts),'PDF 文本页 '+str(len(headings)+1)));parts.append(page.strip()[:10000])
        limited=True  # A bounded extraction never asserts completeness of a PDF.
    elif suffix in ('.txt','.md','.json','.py','.js'):
        with path.open(encoding='utf-8-sig') as stream:body=stream.read(150001)
        limited=len(body)>150000;parts=body[:150000].splitlines()
        headings=[(i,t.lstrip('# ').strip()[:180]) for i,t in enumerate(parts) if re.match(r'^#{1,6}\s',t)]
    else:raise ValueError('材料章节读取支持 DOCX/PPTX/PDF/TXT/MD/JSON/源码文本；表格使用 init/probe')
    if not parts:return dict(path=str(path),sections=[],excerpt='',note='未提取到可读文本；扫描件需要文本识别能力')
    if not headings:headings=[(i,'文本片段 '+str(i//12+1)) for i in range(0,len(parts),12)]
    elif headings[0][0]>0:headings.insert(0,(0,'开篇内容'))
    catalog=[dict(number=i+1,title=t) for i,(_,t) in enumerate(headings[:100])]
    if section is None:return dict(path=str(path),sections=catalog,excerpt='\n'.join(parts)[:1200],truncated=limited or len(headings)>100)
    if section>len(catalog):raise ValueError('section 超出目录；先用 material 查看目录')
    start=headings[section-1][0];end=headings[section][0] if section<len(headings) else len(parts)
    text='\n'.join(parts[start:end]);return dict(path=str(path),section=catalog[section-1],excerpt=text[:6000],truncated=len(text)>6000 or limited)

def profile(path,max_rows=10000):
    try:return _profile(path,max_rows)
    except (ValueError,OSError,zipfile.BadZipFile,ET.ParseError) as e:
        return dict(path=str(Path(path).resolve()),readable=False,stage='input_profile',error=str(e)[:500],
                    next='已登记原始材料；先确认文件格式和读取依赖，材料内容尚未核读。规划中据实判断方法前提，业务处理由专业执行完成。')

def _profile(path,max_rows=10000):
    p=Path(path)
    result={'path':str(p.resolve()),'bytes':p.stat().st_size,'stage':'input_profile'}
    if p.suffix.lower() in ('.csv','.tsv'):
        with p.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.reader(f,delimiter='\t' if p.suffix.lower()=='.tsv' else ',')
            result.update(row_profile(reader,max_rows))
    elif p.suffix.lower()=='.xlsx':result['sheets']=[dict(name=title,**row_profile(rows,max_rows)) for title,rows in xlsx_tables(p)]
    elif p.suffix.lower() in ('.txt','.md','.py','.js','.json'):
        with p.open(encoding='utf-8-sig') as f:excerpt=f.read(1200)
        result.update(excerpt=excerpt,excerpt_complete=p.stat().st_size<=len(excerpt.encode('utf-8')))
    elif p.suffix.lower() in ('.docx','.pptx','.pdf'):result.update(document_profile(p))
    else:result.update(readable=False,next='当前结构读取器不支持该格式；记录材料格式需求，选择对应读取能力。')
    result['scope']='仅文件结构、缺失计数及少量原文样本；关系、归因、分组统计和成品内容留给确认后的专业能力。'
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('files',nargs='+');ap.add_argument('--out',required=True);a=ap.parse_args()
    if len(a.files)>10:ap.error('一次最多10份相关材料；其余先保留目录')
    output=Path(a.out)
    if output.exists():ap.error('画像文件已存在；复用现有画像，新增材料使用新路径')
    if output.resolve() in [Path(f).resolve() for f in a.files]:ap.error('输出不能覆盖材料')
    results=[profile(f) for f in a.files]
    output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'profile':str(output.resolve()),'inputs':results},ensure_ascii=False))
if __name__=='__main__':main()
