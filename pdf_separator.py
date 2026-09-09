from __future__ import annotations

import io
import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from pypdf import PdfReader, PdfWriter

AC_PATTERNS = (
    re.compile(r"A\s*/\s*C\s*REG\s*\.?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\s\-]{3,12})", re.I),
    re.compile(r"(?:^|\n)\s*A\s*/\s*C\s*[:\-]?\s*([A-Z0-9][A-Z0-9\s\-]{3,12})", re.I),
)
WO_PATTERN = re.compile(r"W\s*/\s*O\s*[:#]?\s*([0-9]{4,12})", re.I)
TASK_PATTERN = re.compile(r"TASK\s*CARD\s*[:#]?\s*([^\n\r]{2,100})", re.I)


@dataclass
class SeparationResult:
    pdfs: dict[str, bytes]
    pages_by_registration: dict[str, list[int]]
    warnings: list[str]
    unassigned_pages: list[int]


def _bytes(source: bytes | bytearray | str | Path | BinaryIO) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    data = source.read()
    if hasattr(source, "seek"):
        source.seek(0)
    return data


def normalize_registration(raw: str) -> str | None:
    value = re.sub(r"[^A-Z0-9]", "", raw.upper())
    for marker in ("DESCRIPTION", "DESCRI", "DOC", "PRINTDATE", "SEQNO", "TASKCARD", "WO"):
        if marker in value:
            value = value.split(marker, 1)[0]
    if not 5 <= len(value) <= 8 or not re.fullmatch(r"[A-Z0-9]+", value):
        return None
    if re.fullmatch(r"X[ABC][A-Z0-9]{3}", value):
        return f"{value[:2]}-{value[2:]}"
    if re.fullmatch(r"N[0-9]{1,5}[A-Z]{0,2}", value):
        return value
    if any(c.isdigit() for c in value) and any(c.isalpha() for c in value):
        return value
    return None


def extract_registrations(text: str) -> tuple[str, ...]:
    found = []
    for pattern in AC_PATTERNS:
        for match in pattern.finditer(text.replace("\u00a0", " ")):
            reg = normalize_registration(match.group(1))
            if reg and reg not in found:
                found.append(reg)
    return tuple(found)


def _winner(values) -> str | None:
    counts = Counter(values)
    if not counts:
        return None
    ranked = counts.most_common()
    if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
        return ranked[0][0]
    return None


def _task_cards(text: str) -> tuple[str, ...]:
    cards = []
    for raw in TASK_PATTERN.findall(text):
        value = re.split(r"\s{2,}|\bA\s*/\s*C\b|\bDESCRIPTION\b", raw, 1, flags=re.I)[0]
        value = re.sub(r"\s+", " ", value).strip(" :-").upper()[:80]
        if value and value not in cards:
            cards.append(value)
    return tuple(cards)


def separate_pdf(source) -> SeparationResult:
    reader = PdfReader(io.BytesIO(_bytes(source)), strict=False)
    page_data = []
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        page_data.append({
            "index": index,
            "regs": extract_registrations(text),
            "wos": tuple(dict.fromkeys(WO_PATTERN.findall(text))),
            "tasks": _task_cards(text),
        })

    wo_votes = defaultdict(list)
    task_votes = defaultdict(list)
    for item in page_data:
        reg = _winner(item["regs"])
        if reg:
            for wo in item["wos"]:
                wo_votes[wo].append(reg)
                for task in item["tasks"]:
                    task_votes[(wo, task)].append(reg)
    wo_map = {key: value for key, votes in wo_votes.items() if (value := _winner(votes))}
    task_map = {key: value for key, votes in task_votes.items() if (value := _winner(votes))}

    assigned = [None] * len(page_data)
    for item in page_data:
        direct = _winner(item["regs"])
        if direct:
            assigned[item["index"]] = direct
            continue
        candidates = []
        for wo in item["wos"]:
            candidates.extend(task_map[(wo, task)] for task in item["tasks"] if (wo, task) in task_map)
            if wo in wo_map:
                candidates.append(wo_map[wo])
        assigned[item["index"]] = _winner(candidates)

    known = [i for i, reg in enumerate(assigned) if reg]
    for i, reg in enumerate(assigned):
        if reg or not known:
            continue
        left = next((j for j in reversed(known) if j < i), None)
        right = next((j for j in known if j > i), None)
        lreg = assigned[left] if left is not None else None
        rreg = assigned[right] if right is not None else None
        if lreg and lreg == rreg:
            assigned[i] = lreg
        elif left is None and rreg:
            assigned[i] = rreg
        elif right is None and lreg:
            assigned[i] = lreg

    groups = defaultdict(list)
    unassigned = []
    for index, reg in enumerate(assigned):
        (groups[reg].append(index) if reg else unassigned.append(index + 1))

    outputs = {}
    for reg, indices in sorted(groups.items()):
        writer = PdfWriter()
        for index in indices:
            writer.add_page(reader.pages[index])
        buffer = io.BytesIO()
        writer.write(buffer)
        outputs[f"{reg}.pdf"] = buffer.getvalue()

    warnings = []
    if unassigned:
        warnings.append(f"No fue posible asignar {len(unassigned)} pagina(s).")
    return SeparationResult(
        outputs,
        {reg: [i + 1 for i in indices] for reg, indices in sorted(groups.items())},
        warnings,
        unassigned,
    )


def build_zip(result: SeparationResult) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(result.pdfs.items()):
            archive.writestr(name, data)
        lines = ["REPORTE DE SEPARACION", ""]
        for reg, pages in result.pages_by_registration.items():
            lines.append(f"{reg}: {len(pages)} paginas (origen: {', '.join(map(str, pages))})")
        if result.unassigned_pages:
            lines.extend(["", "PAGINAS NO ASIGNADAS:", ", ".join(map(str, result.unassigned_pages))])
        archive.writestr("REPORTE.txt", "\n".join(lines).encode("utf-8"))
    return buffer.getvalue()
