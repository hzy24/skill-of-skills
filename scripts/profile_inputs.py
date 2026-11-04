#!/usr/bin/env python3
"""Bounded input reconnaissance; deliberately provides no business analysis."""
import argparse,csv,json,zipfile,io,re
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
    if kind not in ('types','date_range'):raise ValueError('规划探查只支持 types / date_range；业务聚合交给执行阶段')
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
        index=header.index(column);counts=dict(empty=0,number=0,date=0,text=0);dates=[];limited=False;count=0
        for row in rows:
            if count>=10000:limited=True;break
            count+=1;v=row[index].strip() if index<len(row) else ''
            if not v:counts['empty']+=1;continue
            try:float(v);counts['number']+=1;continue
            except ValueError:pass
            try:d=datetime.fromisoformat(v.replace('Z','+00:00').replace('/','-'));dates.append(d.date().isoformat());counts['date']+=1
            except ValueError:counts['text']+=1
        result=dict(column=column,kind=kind,rows_scanned=count,row_count_exact=not limited,types=counts)
        if kind=='date_range':result.update(earliest=min(dates) if dates else None,latest=max(dates) if dates else None,note='仅 ISO 日期或斜杠年月日；数字日期保留原类型，业务口径由执行技能确定')
        return result
    finally:
        if handle:handle.close()

def profile(path,max_rows=10000):
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
    else:result['next']='用现有读取能力获取目录、表头或章节范围；专业处理在选定方法后执行。'
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
