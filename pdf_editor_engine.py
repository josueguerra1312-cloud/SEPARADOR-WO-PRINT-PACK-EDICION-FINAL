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

@dataclass
class PageInfo:
    source: int; kind: str; doc_id: str; number: int; total: int


def clean(text): return " ".join((text or "").replace("\x00", " ").split())
def task_id(text, fallback=""): 
    m = TASK_ID.search(text); return clean(m.group(1)) if m else fallback


def classify(text, index):
    text = clean(text); upper = text.upper()
    if not text or PREDRAW.search(text): return None
    eoid, eopage = EO_ID.search(text), EO_PAGE.search(text)
    if eoid and eopage: return PageInfo(index, "eo", eoid.group(1).rstrip("_.-"), int(eopage.group(1)), int(eopage.group(2)))
    form = FORM_PAGE.search(text)
    if form and any(x in upper for x in ("DAILY CHECK", "WEEKLY CHECK", "FORM N", "FORM Nº")):
        return PageInfo(index, "check", task_id(text, "CHECK"), int(form.group(1)), int(form.group(2)))
    task = TASK_PAGE.search(text)
    if task and "TASK CARD" in upper:
        return PageInfo(index, "task", task_id(text, "TASK"), int(task.group(1)), int(task.group(2)))
    return None


def detect_blocks(reader):
    infos = [classify(page.extract_text() or "", i) for i, page in enumerate(reader.pages, 1)]
    infos = [x for x in infos if x]
    blocks, current = [], None
    for info in infos:
        continuation = current and info.kind == current["kind"] and info.number == current["pages"][-1].number + 1 and info.total == current["total"]
        if info.number == 1 or not continuation:
            if current: blocks.append(current)
            current = {"kind": info.kind, "doc_id": info.doc_id, "total": info.total, "pages": [info], "keep": True}
        else: current["pages"].append(info)
    if current: blocks.append(current)
    for i, block in enumerate(blocks):
        if len(block["pages"]) != block["total"]: block["keep"] = False
        elif block["kind"] == "task" and block["total"] == 1 and i + 1 < len(blocks):
            nxt = blocks[i + 1]
            if nxt["pages"][0].source == block["pages"][-1].source + 1 and nxt["kind"] in {"eo", "check"}: block["keep"] = False
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
    audit = {"version": "10.0", "input": name, "output": output_name(name), "input_pages": len(reader.pages), "output_pages": len(writer.pages), "blocks": [{"kind": b["kind"], "doc_id": b["doc_id"], "source_pages": [p.source for p in b["pages"]], "keep": b["keep"]} for b in blocks]}
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

