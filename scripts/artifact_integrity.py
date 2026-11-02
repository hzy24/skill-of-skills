"""Cheap file-integrity checks before review; content quality stays task-specific."""
import json, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

def verify(path, declared_format=None):
    path=Path(path)
    if not path.is_file() or not path.stat().st_size:
        raise ValueError('成果不存在或为空：'+str(path))
    kind=(declared_format or path.suffix.lstrip('.')).lower()
    try:
        if kind=='json':json.loads(path.read_text(encoding='utf-8-sig'))
        elif kind in ('docx','pptx','xlsx'):
            main={'docx':'word/document.xml','pptx':'ppt/presentation.xml','xlsx':'xl/workbook.xml'}[kind]
            with zipfile.ZipFile(path) as z:
                # Stream CRC checks; never extract an artifact into the workspace.
                if z.testzip():raise ValueError('ZIP 校验失败')
                for part in ('[Content_Types].xml','_rels/.rels',main):ET.fromstring(z.read(part))
        elif kind=='pdf':
            with path.open('rb') as f:
                head=f.read(1024);f.seek(max(0,path.stat().st_size-2048));tail=f.read()
            if b'%PDF-' not in head or b'%%EOF' not in tail:raise ValueError('PDF 文件头或结束标记缺失')
        elif kind in ('md','txt','html','csv','tsv'):
            with path.open('rb') as f:
                if not f.read(8192).strip():raise ValueError('文本成果为空白')
    except (ValueError,KeyError,UnicodeError,ET.ParseError,zipfile.BadZipFile) as e:
        raise ValueError('成果格式损坏（'+kind+'）：'+str(path)+'；'+str(e)) from e
