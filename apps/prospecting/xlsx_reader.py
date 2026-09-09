from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import BinaryIO


MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


class ProspectingSpreadsheetError(ValueError):
    pass


@dataclass(frozen=True)
class _CellValue:
    kind: str
    value: str


def _column_letters(cell_ref: str) -> str:
    match = re.match(r"[A-Z]+", cell_ref or "")
    return match.group(0) if match else ""


def _normalize_header(value: str) -> str:
    normalized = (value or "").strip().casefold()
    normalized = normalized.replace("á", "a").replace("à", "a").replace("ã", "a")
    normalized = normalized.replace("â", "a").replace("é", "e").replace("ê", "e")
    normalized = normalized.replace("í", "i").replace("ó", "o").replace("ô", "o")
    normalized = normalized.replace("õ", "o").replace("ú", "u").replace("ç", "c")
    return re.sub(r"[^a-z0-9]", "", normalized)


def _worksheet_path(zf: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    sheets = workbook.find(f"{MAIN_NS}sheets")
    if sheets is None or not list(sheets):
        raise ProspectingSpreadsheetError("A planilha não possui abas.")

    chosen = None
    for sheet in sheets:
        if (sheet.attrib.get("name") or "").strip().casefold() == "leads":
            chosen = sheet
            break
    if chosen is None:
        chosen = list(sheets)[0]

    rel_id = chosen.attrib.get(f"{REL_NS}id")
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels:
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib.get("Target", "")
            if target.startswith("/"):
                return target.lstrip("/")
            return f"xl/{target}"
    raise ProspectingSpreadsheetError("Não foi possível localizar a aba da planilha.")


def _cell_descriptor(cell) -> _CellValue | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        text = "".join((node.text or "") for node in cell.iter(f"{MAIN_NS}t"))
        return _CellValue("inline", text)

    value_node = cell.find(f"{MAIN_NS}v")
    if value_node is None or value_node.text is None:
        return None
    if cell_type == "s":
        return _CellValue("shared", value_node.text)
    return _CellValue("raw", value_node.text)


def _resolve_shared_strings(zf: zipfile.ZipFile, wanted: set[int]) -> dict[int, str]:
    if not wanted or "xl/sharedStrings.xml" not in zf.namelist():
        return {}

    resolved: dict[int, str] = {}
    index = -1
    with zf.open("xl/sharedStrings.xml") as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag == f"{MAIN_NS}si":
                index += 1
                if index in wanted:
                    resolved[index] = "".join((node.text or "") for node in elem.iter(f"{MAIN_NS}t"))
                elem.clear()
                if len(resolved) == len(wanted):
                    break
    return resolved


def _resolve(desc: _CellValue | None, shared: dict[int, str]) -> str:
    if desc is None:
        return ""
    if desc.kind == "shared":
        try:
            return shared.get(int(desc.value), "")
        except (TypeError, ValueError):
            return ""
    return desc.value


def read_prospecting_rows(file_obj: BinaryIO) -> list[tuple[str, str]]:
    """Lê apenas Nome da loja/Estabelecimento + WhatsApp."""

    try:
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
        with zipfile.ZipFile(file_obj) as zf:
            sheet_path = _worksheet_path(zf)

            header_cells: dict[str, _CellValue] = {}
            header_shared: set[int] = set()
            with zf.open(sheet_path) as fh:
                for _, elem in ET.iterparse(fh, events=("end",)):
                    if elem.tag == f"{MAIN_NS}row":
                        if int(elem.attrib.get("r", "0")) == 1:
                            for cell in elem.findall(f"{MAIN_NS}c"):
                                col = _column_letters(cell.attrib.get("r", ""))
                                desc = _cell_descriptor(cell)
                                if col and desc:
                                    header_cells[col] = desc
                                    if desc.kind == "shared":
                                        header_shared.add(int(desc.value))
                            elem.clear()
                            break
                        elem.clear()

            header_strings = _resolve_shared_strings(zf, header_shared)
            by_name = {
                _normalize_header(_resolve(desc, header_strings)): col
                for col, desc in header_cells.items()
            }
            establishment_col = by_name.get("nomedaloja") or by_name.get("estabelecimento")
            whatsapp_col = by_name.get("whatsapp")
            if not establishment_col or not whatsapp_col:
                raise ProspectingSpreadsheetError(
                    "A planilha precisa ter as colunas 'Nome da loja' e 'WhatsApp'."
                )

            row_descriptors: list[tuple[_CellValue | None, _CellValue | None]] = []
            wanted_shared: set[int] = set()
            with zf.open(sheet_path) as fh:
                for _, elem in ET.iterparse(fh, events=("end",)):
                    if elem.tag != f"{MAIN_NS}row":
                        continue
                    row_num = int(elem.attrib.get("r", "0"))
                    if row_num <= 1:
                        elem.clear()
                        continue

                    name_desc = None
                    phone_desc = None
                    for cell in elem.findall(f"{MAIN_NS}c"):
                        col = _column_letters(cell.attrib.get("r", ""))
                        if col == establishment_col:
                            name_desc = _cell_descriptor(cell)
                        elif col == whatsapp_col:
                            phone_desc = _cell_descriptor(cell)
                    for desc in (name_desc, phone_desc):
                        if desc and desc.kind == "shared":
                            wanted_shared.add(int(desc.value))
                    row_descriptors.append((name_desc, phone_desc))
                    elem.clear()

            shared = _resolve_shared_strings(zf, wanted_shared)
            rows = []
            for name_desc, phone_desc in row_descriptors:
                name = _resolve(name_desc, shared).strip()
                phone = _resolve(phone_desc, shared).strip()
                if name or phone:
                    rows.append((name, phone))
            return rows
    except zipfile.BadZipFile as exc:
        raise ProspectingSpreadsheetError("Arquivo XLSX inválido.") from exc
    except KeyError as exc:
        raise ProspectingSpreadsheetError("Estrutura interna do XLSX inválida.") from exc
