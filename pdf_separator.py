from __future__ import annotations
import io, re, zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from pypdf import PdfReader, PdfWriter
AC_PATTERNS=(re.compile(r"A\s*/\s*C\s*REG\s*\.?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\s\-]{3,12})",re.I),re.compile(r"(?:^|\n)\s*A\s*/\s*C\s*[:\-]?\s*([A-Z0-9][A-Z0-9\s\-]{3,12})",re.I))
WO_RE=re.compile(r"W\s*/\s*O\s*[:#]?\s*(\d{4,12})",re.I)
@dataclass
class SeparationResult: pdfs:dict[str,bytes]; pages_by_registration:dict[str,list[int]]; warnings:list[str]; unassigned_pages:list[int]
def _winner(v):
 c=Counter(v); r=c.most_common(); return r[0][0] if r and (len(r)==1 or r[0][1]>r[1][1]) else None
def _reg(raw):
 v=re.sub(r"[^A-Z0-9]","",raw.upper())
 for m in ("DESCRIPTION","DESCRI","DOC","PRINTDATE","SEQNO","TASKCARD","WO"):
  if m in v:v=v.split(m,1)[0]
 if re.fullmatch(r"X[ABC][A-Z0-9]{3}",v):return v[:2]+"-"+v[2:]
 if re.fullmatch(r"N\d{1,5}[A-Z]{0,2}",v):return v
 return v if 5<=len(v)<=8 and any(x.isdigit() for x in v) and any(x.isalpha() for x in v) else None
def separate_pdf(source):
 data=source if isinstance(source,bytes) else Path(source).read_bytes(); reader=PdfReader(io.BytesIO(data),strict=False); info=[]
 for i,p in enumerate(reader.pages):
  try:t=p.extract_text() or ""
  except:t=""
  regs=[]
  for pat in AC_PATTERNS:
   for m in pat.finditer(t):
    x=_reg(m.group(1)); regs += [x] if x and x not in regs else []
  info.append((i,tuple(regs),tuple(dict.fromkeys(WO_RE.findall(t)))))
 votes=defaultdict(list)
 for _,regs,wos in info:
  if (r:=_winner(regs)):
   for wo in wos:votes[wo].append(r)
 womap={wo:r for wo,v in votes.items() if (r:=_winner(v))}; assigned=[]
 for _,regs,wos in info:assigned.append(_winner(regs) or _winner([womap[x] for x in wos if x in womap]))
 known=[i for i,x in enumerate(assigned) if x]
 for i,x in enumerate(assigned):
  if x or not known:continue
  l=next((j for j in reversed(known) if j<i),None); r=next((j for j in known if j>i),None); lv=assigned[l] if l is not None else None; rv=assigned[r] if r is not None else None
  if lv==rv and lv:assigned[i]=lv
  elif l is None:assigned[i]=rv
  elif r is None:assigned[i]=lv
 groups=defaultdict(list); un=[]
 for i,r in enumerate(assigned):(groups[r].append(i) if r else un.append(i+1))
 outputs={}
 for r,idx in sorted(groups.items()):
  w=PdfWriter(); [w.add_page(reader.pages[i]) for i in idx]; b=io.BytesIO(); w.write(b); outputs[r+'.pdf']=b.getvalue()
 return SeparationResult(outputs,{r:[i+1 for i in x] for r,x in sorted(groups.items())},[f"No fue posible asignar {len(un)} pagina(s)."] if un else [],un)
def build_zip(result):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
  for n,d in sorted(result.pdfs.items()):z.writestr(n,d)
  z.writestr('REPORTE.txt','\n'.join([f"{r}: {len(p)} paginas" for r,p in result.pages_by_registration.items()]).encode())
 return b.getvalue()
