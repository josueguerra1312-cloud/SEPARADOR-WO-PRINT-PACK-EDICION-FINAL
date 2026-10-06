from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter

PREDRAW = re.compile(r"P/N\s+Pre-Draw\s+Print", re.I)
TASK_PAGE = re.compile(r"\bPage\s*:\s*(\d+)\s+of\s+(\d+)", re.I)
EO_PAGE = re.compile(r"\bPAGE\s*:\s*(\d+)\s+of\s+(\d+)", re.I)
FORM_PAGE = re.compile(r"\bPAGE\s+(\d+)\s+OF\s+(\d+)", re.I)
EO_ID = re.compile(r"E\.O\.\s*No\.\s*:\s*([A-Z0-9._-]+)", re.I)
TASK_ID = re.compile(r"Task\s*Card\s*:\s*(.+?)(?=\s+A\s*/?\s*C\s+Reg\.|\s+Description\s*:|$)", re.I)
WO_PATTERNS = [
    re.compile(r"\bW\s*[./-]?\s*O\s*(?:No\.?|Number|#)?\s*[:.-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})", re.I),
    re.compile(r"\bWORK\s+ORDER\s*(?:No\.?|Number|#)?\s*[:.-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})", re.I),
]
BSI_IDS = {"VA-72-0102", "VA-72-0205"}
BSI_TERMS = ("BOROSCOPE INSPECTION", "BORESCOPE INSPECTION", "BOROSCOPE", "BORESCOPE", " BSI ")

@dataclass
class PageInfo:
    source: int
    kind: str
    doc_id: str = ""
    number: int = 0
    total: int = 0
    wo: str = ""
    is_bsi: bool = False

def clean(text): return " ".join((text or "").replace("\x00", " ").split())
def task_id(text, fallback=""):
    m = TASK_ID.search(text); return clean(m.group(1)) if m else fallback

def extract_wo(text):
    normalized = clean(text)
    for area in (normalized[:1800], normalized):
        for pattern in WO_PATTERNS:
            match = pattern.search(area)
            if match: return match.group(1).strip(" ._-:").upper()
    return ""

def is_bsi(text, doc_id=""):
    upper = f" {clean(text).upper()} "
    return clean(doc_id).upper().rstrip("_.-") in BSI_IDS or any(term in upper for term in BSI_TERMS)

def classify(text, index):
    text = clean(text); upper = text.upper(); wo = extract_wo(text)
    if not text: return PageInfo(index, "blank")
    if PREDRAW.search(text): return PageInfo(index, "predraw", task_id(text), wo=wo, is_bsi=is_bsi(text))
    eoid, eopage = EO_ID.search(text), EO_PAGE.search(text)
    if eoid and eopage:
        doc = eoid.group(1).rstrip("_.-")
        return PageInfo(index, "eo", doc, int(eopage.group(1)), int(eopage.group(2)), wo, is_bsi(text, doc))
    form = FORM_PAGE.search(text)
    if form and any(x in upper for x in ("DAILY CHECK", "WEEKLY CHECK", "FORM N", "FORM Nº")):
        doc = task_id(text, "CHECK")
        return PageInfo(index, "check", doc, int(form.group(1)), int(form.group(2)), wo, is_bsi(text, doc))
    task = TASK_PAGE.search(text)
    if task and "TASK CARD" in upper:
        doc = task_id(text, "TASK")
        return PageInfo(index, "task", doc, int(task.group(1)), int(task.group(2)), wo, is_bsi(text, doc))
    return PageInfo(index, "attachment", task_id(text), wo=wo, is_bsi=is_bsi(text))

def same_wo(left, right): return bool(left and right and left.upper() == right.upper())

def detect_blocks(reader):
    pages = [classify(page.extract_text() or "", i) for i, page in enumerate(reader.pages, 1)]
    blocks, current = [], None
    for info in pages:
        if info.kind in {"task", "eo", "check"}:
            continuation = current and info.kind == current["kind"] and info.number == current["numbered"][-1].number + 1 and info.total == current["total"]
            if info.number == 1 or not continuation:
                if current: blocks.append(current)
                current = {"kind": info.kind, "doc_id": info.doc_id, "total": info.total, "numbered": [info], "annexes": [], "pages": [info], "wo": info.wo, "is_bsi": info.is_bsi, "keep": True}
            else:
                current["numbered"].append(info); current["pages"].append(info)
                current["wo"] = current["wo"] or info.wo
                current["is_bsi"] = current["is_bsi"] or info.is_bsi
            continue
        if info.kind == "predraw":
            if current: blocks.append(current); current = None
            continue
        if info.kind == "attachment" and current:
            if same_wo(info.wo, current["wo"]) or current["is_bsi"] or info.is_bsi or current["doc_id"].upper() in BSI_IDS:
                current["annexes"].append(info); current["pages"].append(info)
                current["is_bsi"] = current["is_bsi"] or info.is_bsi
    if current: blocks.append(current)
    for i, block in enumerate(blocks):
        if len(block["numbered"]) != block["total"]: block["keep"] = False
        elif block["kind"] == "task" and block["total"] == 1 and i + 1 < len(blocks):
            nxt = blocks[i + 1]
            adjacent = nxt["numbered"][0].source == block["numbered"][-1].source + 1
            if adjacent and nxt["kind"] in {"eo", "check"} and (same_wo(block["wo"], nxt["wo"]) or not block["wo"] or not nxt["wo"]): block["keep"] = False
    return blocks

def output_name(name):
    stem = Path(name).stem
    if stem.endswith(" F") or stem.endswith(" D"): stem = stem[:-2]
    return f"{stem} D.pdf"


def edit_pdf(name, data):
    reader = PdfReader(io.BytesIO(data), strict=False)
    blocks = detect_blocks(reader); kept = [b for b in blocks if b["keep"]]
    if not kept: raise ValueError("No se detectaron documentos tecnicos completos")
    writer = PdfWriter()
    for block in kept:
        for info in block["pages"]: writer.add_page(reader.pages[info.source - 1])
        if len(block["pages"]) % 2:
            last = reader.pages[block["pages"][-1].source - 1]
            writer.add_blank_page(width=float(last.mediabox.width), height=float(last.mediabox.height))
    pdf_buffer = io.BytesIO(); writer.write(pdf_buffer); pdf_data = pdf_buffer.getvalue()
    audit = {"version": "11.0", "input": name, "output": output_name(name), "input_pages": len(reader.pages), "output_pages": len(writer.pages), "blocks": [{"kind": b["kind"], "doc_id": b["doc_id"], "wo": b["wo"], "is_bsi": b["is_bsi"], "numbered_pages": [p.source for p in b["numbered"]], "annex_pages": [p.source for p in b["annexes"]], "source_pages": [p.source for p in b["pages"]], "keep": b["keep"]} for b in blocks]}
    if len(PdfReader(io.BytesIO(pdf_data), strict=False).pages) != len(writer.pages): raise ValueError("Validacion del PDF fallida")
    return {"input_name": name, "pdf_name": output_name(name), "pdf_data": pdf_data, "audit_name": Path(output_name(name)).with_suffix(".audit.json").name, "audit_data": json.dumps(audit, indent=2, ensure_ascii=False).encode(), "input_pages": len(reader.pages), "output_pages": len(writer.pages)}


def create_zip(results):
    buffer = io.BytesIO()
    # ZIP_STORED is the most compatible option with Windows Explorer and avoids compression-stream truncation.
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        rows = [["entrada", "salida", "paginas_entrada", "paginas_salida", "sha256_pdf"]]
        for item in results:
            archive.writestr("PDF_EDITADOS/" + item["pdf_name"], item["pdf_data"])
            archive.writestr("AUDITORIAS/" + item["audit_name"], item["audit_data"])
            rows.append([item["input_name"], item["pdf_name"], item["input_pages"], item["output_pages"], hashlib.sha256(item["pdf_data"]).hexdigest()])
        manifest = io.StringIO(newline=""); csv.writer(manifest).writerows(rows)
        archive.writestr("MANIFIESTO.csv", manifest.getvalue().encode("utf-8-sig"))
    zip_data = buffer.getvalue()
    # Full reopen, CRC check, entry count and embedded PDF validation.
    with zipfile.ZipFile(io.BytesIO(zip_data), "r") as verify:
        if verify.testzip() is not None: raise ValueError("Fallo CRC del ZIP")
        pdf_entries = [n for n in verify.namelist() if n.startswith("PDF_EDITADOS/") and n.endswith(".pdf")]
        if len(pdf_entries) != len(results): raise ValueError("El ZIP no contiene todos los PDF")
        for entry in pdf_entries:
            if not PdfReader(io.BytesIO(verify.read(entry)), strict=False).pages: raise ValueError(f"PDF invalido: {entry}")
    return zip_data
