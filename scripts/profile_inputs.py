#!/usr/bin/env python3
"""Bounded input reconnaissance; deliberately provides no business analysis."""
import argparse,csv,json
from pathlib import Path

def profile(path,max_rows=10000):
    p=Path(path)
    result={'path':str(p.resolve()),'bytes':p.stat().st_size,'stage':'input_profile'}
    if p.suffix.lower() in ('.csv','.tsv'):
        with p.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.reader(f,delimiter='\t' if p.suffix.lower()=='.tsv' else ',')
            header=next(reader,[])
            if len(header)>100:raise ValueError('列数超过100；请按任务相关字段读取结构')
            missing=[0]*len(header);samples=[];count=0;malformed=0;limited=False
            for row in reader:
                if count>=max_rows:limited=True;break
                count+=1;malformed+=len(row)!=len(header)
                for i in range(len(header)):missing[i]+=i>=len(row) or not row[i].strip()
                if len(samples)<3:samples.append([v[:100] for v in row[:len(header)]])
        result.update(columns=header,rows_scanned=count,row_count_exact=not limited,
                      missing_by_column=missing,sample_rows=samples,malformed_rows=malformed)
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
