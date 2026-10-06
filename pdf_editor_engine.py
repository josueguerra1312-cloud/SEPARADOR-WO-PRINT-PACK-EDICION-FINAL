from __future__ import annotations
import csv, hashlib, io, json, re, zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from pypdf import PdfReader, PdfWriter

PREDRAW = re.compile(r"(?:P/N\s+)?PRE\s*[- ]?\s*DRAW\s+PRINT", re.I)
PAGE = re.compile(r"\bPAGE\s*:?[ \t]*(\d{1,3})\s*(?:OF|/)[ \t]*(\d{1,3})(?!\d)", re.I)
TASK_ID = re.compile(r"TASK\s*CARD\s*:?\s*([A-Z0-9][A-Z0-9._/-]*(?:\s+(?:RH|LH))?)", re.I)
EO_ID = re.compile(r"E\s*\.?\s*O\s*\.?\s*(?:NO\s*\.?)?\s*:?\s*(VA-[A-Z0-9._-]+)", re.I)
WO = re.compile(r"W\s*[./-]?\s*O\s*(?:NO\.?|NUMBER|#)?\s*[:.-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})", re.I)
BSI_IDS={"VA-72-0102","VA-72-0205"}
BSI_TERMS=("BOROSCOPE INSPECTION","BORESCOPE INSPECTION","BOROSCOPE","BORESCOPE"," BSI ")

@dataclass
class Event:
    action:str
    source_pages:list[int]
    detail:str

def clean(text): return " ".join((text or "").replace("\x00"," ").split())
def gettext(page):
    try:return page.extract_text() or ""
    except:return ""
def number(text):
    vals=[]
    for a,b in PAGE.findall(text):
        a,b=int(a),int(b)
        if 1<=a<=b<=500: vals.append((a,b))
    return vals[-1] if vals else None
def refs(text):
    values={x.upper().strip() for x in TASK_ID.findall(text)}
    values.update(x.upper().strip() for x in EO_ID.findall(text))
    return values
def work_order(text):
    m=WO.search(clean(text)); return m.group(1).strip(" ._-:").upper() if m else ""
def is_bsi(text, identifiers=()):
    upper=f" {clean(text).upper()} "
    return bool(set(identifiers)&BSI_IDS) or any(term in upper for term in BSI_TERMS)
def output_name(name):
    stem=Path(name).stem
    stem=re.sub(r"\s+SIN\s+EDITAR\s*$","",stem,flags=re.I).strip()
    stem=re.sub(r"\s+D\s*$","",stem,flags=re.I).strip()
    return stem+" D.pdf"

def next_kept(infos,start):
    for i in range(start,len(infos)):
        if not infos[i]['predraw']: return i
    return None

def duplicate_cover(infos,i):
    cur=infos[i]
    if cur['number']!=(1,1): return False
    va={x for x in cur['refs'] if x.startswith('VA-')}
    if not va:return False
    # Search only until the next normal task starts. Image-only EO page 1 is allowed.
    for j in range(i+1,min(len(infos),i+4)):
        if infos[j]['predraw']:continue
        nxt=infos[j]
        if va & nxt['refs'] and (EO_ID.search(nxt['text']) or (nxt['number'] and nxt['number'][0] in (1,2))): return True
        if nxt['number'] and nxt['number'][0]==1 and not (va & nxt['refs']): break
    return False

def complete_block(infos,start):
    """Return principal numbered pages. Supports an unnumbered graphical EO page 1 before PAGE 2 OF N."""
    first=infos[start]['number']
    if first and first[0]==1:
        total=first[1]; idx=[]; j=start
        for expected in range(1,total+1):
            if j>=len(infos) or infos[j]['predraw'] or infos[j]['number']!=(expected,total): return None
            idx.append(j);j+=1
        return idx,j
    # Infer page 1 when current page shares WO/reference with following PAGE 2 OF N.
    if start+1<len(infos):
        second=infos[start+1]['number']
        if not first and second and second[0]==2:
            total=second[1]; shared_ref=bool(infos[start]['refs']&infos[start+1]['refs']); shared_wo=infos[start]['wo'] and infos[start]['wo']==infos[start+1]['wo']
            if shared_ref or shared_wo:
                idx=[start];j=start+1
                for expected in range(2,total+1):
                    if j>=len(infos) or infos[j]['predraw'] or infos[j]['number']!=(expected,total):return None
                    idx.append(j);j+=1
                return idx,j
    return None

def edit_pdf(input_name,data):
    reader=PdfReader(io.BytesIO(data),strict=False)
    infos=[]
    for i,p in enumerate(reader.pages):
        text=gettext(p); r=refs(text)
        infos.append({'i':i,'text':text,'predraw':bool(PREDRAW.search(text)),'number':number(text),'refs':r,'wo':work_order(text),'bsi':is_bsi(text,r)})
    writer=PdfWriter(); events=[]; kept=[]; blanks=0; i=0
    while i<len(infos):
        x=infos[i]
        if x['predraw']:
            events.append(Event('removed_predraw',[i+1],'Positive Pre-Draw Print match'));i+=1;continue
        if duplicate_cover(infos,i):
            events.append(Event('removed_duplicate_cover',[i+1],'Task Card 1 of 1 introduces matching EO'));i+=1;continue
        block=complete_block(infos,i)
        if block:
            idx,end=block
            for j in idx:writer.add_page(reader.pages[j]);kept.append(j+1)
            # Preserve every following attachment until a positive new document boundary.
            attachments=[]; k=end
            while k<len(infos):
                if infos[k]['predraw']:break
                if duplicate_cover(infos,k):break
                if complete_block(infos,k):break
                attachments.append(k);k+=1
            any_bsi=any(infos[j]['bsi'] for j in idx+attachments)
            # Normal tasks are paired before attachments (validated reference behavior).
            # BSI packages remain intact and are paired after all their attachments.
            if not any_bsi and len(idx)%2:
                p=reader.pages[idx[-1]];writer.add_blank_page(float(p.mediabox.width),float(p.mediabox.height));blanks+=1
                events.append(Event('inserted_blank',[],f'After principal block ending at source page {idx[-1]+1}'))
            for j in attachments:writer.add_page(reader.pages[j]);kept.append(j+1)
            if any_bsi and (len(idx)+len(attachments))%2:
                p=reader.pages[(attachments or idx)[-1]];writer.add_blank_page(float(p.mediabox.width),float(p.mediabox.height));blanks+=1
                events.append(Event('inserted_blank_bsi',[],f'After complete BSI package ending at source page {(attachments or idx)[-1]+1}'))
            events.append(Event('kept_block_with_attachments',[j+1 for j in idx+attachments],f'Principal={len(idx)}, attachments={len(attachments)}, BSI={any_bsi}'))
            i=k;continue
        # Safety rule: unclassified pages and WO annexes are preserved, never silently omitted.
        writer.add_page(reader.pages[i]);kept.append(i+1)
        events.append(Event('kept_unclassified_or_attachment',[i+1],f"WO={x['wo'] or 'not extracted'}; BSI={x['bsi']}"));i+=1
    out=io.BytesIO(); name=output_name(input_name)
    writer.add_metadata({'/Producer':'Editor PDF Tecnico v12 conservative annex','/Title':name});writer.write(out);pdf=out.getvalue()
    audit={'version':'v12-conservative-annex-bsi','input_name':input_name,'output_name':name,'input_pages':len(reader.pages),'output_pages':len(writer.pages),'kept_source_pages':kept,'inserted_blank_pages':blanks,'sha256_input':hashlib.sha256(data).hexdigest(),'sha256_output':hashlib.sha256(pdf).hexdigest(),'events':[asdict(e) for e in events]}
    ad=json.dumps(audit,ensure_ascii=False,indent=2).encode()
    return {'input_name':input_name,'input_pages':len(reader.pages),'output_pages':len(writer.pages),'pdf_name':name,'pdf_data':pdf,'audit_name':Path(name).stem+'_AUDIT.json','audit_data':ad,'audit':audit}

def create_zip(results):
    b=io.BytesIO();s=io.StringIO(newline='');w=csv.writer(s);w.writerow(['input_name','output_name','input_pages','output_pages','sha256'])
    with zipfile.ZipFile(b,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
        for x in results:
            z.writestr('PDF_EDITADOS/'+x['pdf_name'],x['pdf_data']);z.writestr('AUDITORIAS/'+x['audit_name'],x['audit_data']);w.writerow([x['input_name'],x['pdf_name'],x['input_pages'],x['output_pages'],hashlib.sha256(x['pdf_data']).hexdigest()])
        z.writestr('MANIFIESTO.csv',s.getvalue().encode('utf-8-sig'))
    data=b.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC invalido')
        pdfs=[n for n in z.namelist() if n.lower().endswith('.pdf')]
        if len(pdfs)!=len(results):raise ValueError('Cantidad de PDF incorrecta')
        for n in pdfs:PdfReader(io.BytesIO(z.read(n)),strict=False)
    return data
