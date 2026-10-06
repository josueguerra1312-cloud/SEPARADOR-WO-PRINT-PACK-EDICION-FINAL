from __future__ import annotations
import io,re,zipfile
from collections import Counter,defaultdict
from dataclasses import dataclass
from pathlib import Path
from pypdf import PdfReader,PdfWriter
AC=(re.compile(r"A\s*/\s*C\s*REG\s*\.?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\s\-]{3,12})",re.I),re.compile(r"(?:^|\n)\s*A\s*/\s*C\s*[:\-]?\s*([A-Z0-9][A-Z0-9\s\-]{3,12})",re.I));WO=re.compile(r"W\s*/\s*O\s*[:#]?\s*(\d{4,12})",re.I)
@dataclass
class SeparationResult:pdfs:dict[str,bytes];pages_by_registration:dict[str,list[int]];warnings:list[str];unassigned_pages:list[int]
def win(v):
 c=Counter(v).most_common();return c[0][0] if c and (len(c)==1 or c[0][1]>c[1][1]) else None
def reg(s):
 v=re.sub('[^A-Z0-9]','',s.upper())
 for m in ('DESCRIPTION','DESCRI','DOC','PRINTDATE','SEQNO','TASKCARD','WO'):
  if m in v:v=v.split(m,1)[0]
 if re.fullmatch(r'X[ABC][A-Z0-9]{3}',v):return v[:2]+'-'+v[2:]
 if re.fullmatch(r'N\d{1,5}[A-Z]{0,2}',v):return v
 return v if 5<=len(v)<=8 and any(x.isdigit() for x in v) and any(x.isalpha() for x in v) else None
def separate_pdf(source):
 data=source if isinstance(source,bytes) else Path(source).read_bytes();r=PdfReader(io.BytesIO(data),strict=False);info=[]
 for i,p in enumerate(r.pages):
  try:t=p.extract_text() or ''
  except:t=''
  rs=[]
  for pat in AC:
   for m in pat.finditer(t):
    x=reg(m.group(1));rs += [x] if x and x not in rs else []
  info.append((i,tuple(rs),tuple(dict.fromkeys(WO.findall(t)))))
 votes=defaultdict(list)
 for _,rs,wos in info:
  if (x:=win(rs)):
   for wo in wos:votes[wo].append(x)
 wm={wo:x for wo,v in votes.items() if (x:=win(v))};a=[win(rs) or win([wm[x] for x in wos if x in wm]) for _,rs,wos in info];known=[i for i,x in enumerate(a) if x]
 for i,x in enumerate(a):
  if x or not known:continue
  l=next((j for j in reversed(known) if j<i),None);rr=next((j for j in known if j>i),None);lv=a[l] if l is not None else None;rv=a[rr] if rr is not None else None
  if lv==rv and lv:a[i]=lv
  elif l is None:a[i]=rv
  elif rr is None:a[i]=lv
 g=defaultdict(list);un=[]
 for i,x in enumerate(a):(g[x].append(i) if x else un.append(i+1))
 out={}
 for x,idx in sorted(g.items()):
  w=PdfWriter();[w.add_page(r.pages[i]) for i in idx];b=io.BytesIO();w.write(b);out[x+'.pdf']=b.getvalue()
 return SeparationResult(out,{x:[i+1 for i in idx] for x,idx in sorted(g.items())},[f'No fue posible asignar {len(un)} pagina(s).'] if un else [],un)
def build_zip(result):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
  for n,d in sorted(result.pdfs.items()):z.writestr(n,d)
  z.writestr('REPORTE.txt','\n'.join(f'{x}: {len(p)} paginas' for x,p in result.pages_by_registration.items()))
 return b.getvalue()
