"""Resolve logical presentation order from OOXML relationships."""
import posixpath
from xml.etree import ElementTree as ET
P='{http://schemas.openxmlformats.org/presentationml/2006/main}'
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
def slide_parts(z):
    presentation=ET.fromstring(z.read('ppt/presentation.xml'))
    rels={x.get('Id'):x for x in ET.fromstring(z.read('ppt/_rels/presentation.xml.rels'))}
    parts=[]
    for item in presentation.findall('./'+P+'sldIdLst/'+P+'sldId'):
        rel=rels.get(item.get(R+'id'))
        if rel is None or rel.get('TargetMode')=='External' or not rel.get('Type','').endswith('/slide'):
            raise ValueError('无效幻灯片关系')
        target=rel.get('Target','')
        part=target.lstrip('/') if target.startswith('/') else posixpath.normpath('ppt/'+target)
        if not part.startswith('ppt/') or part not in z.namelist(): raise ValueError('幻灯片部件缺失')
        parts.append(part)
    if len(set(parts))!=len(parts): raise ValueError('幻灯片关系重复')
    return parts
