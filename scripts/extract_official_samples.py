import json
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def excel_column_to_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    value = 0
    for char in letters:
        value = value * 26 + (ord(char.upper()) - 64)
    return value - 1


def load_shared_strings(archive: zipfile.ZipFile):
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    values = []
    for si in root.findall("main:si", NS):
        text_parts = [node.text or "" for node in si.findall(".//main:t", NS)]
        values.append("".join(text_parts))
    return values


def workbook_sheet_targets(archive: zipfile.ZipFile):
    workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
    rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

    rel_map = {}
    for rel in rels_root.findall("pkgrel:Relationship", NS):
        rel_map[rel.attrib["Id"]] = rel.attrib["Target"]

    targets = {}
    for sheet in workbook_root.findall("main:sheets/main:sheet", NS):
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[f"{{{NS['rel']}}}id"]
        targets[name] = f"xl/{rel_map[rel_id]}"
    return targets


def cell_text(cell, shared_strings):
    cell_type = cell.attrib.get("t")

    if cell_type == "s":
      value_node = cell.find("main:v", NS)
      if value_node is None or value_node.text is None:
          return ""
      return shared_strings[int(value_node.text)]

    if cell_type == "inlineStr":
        return "".join(
            (node.text or "") for node in cell.findall(".//main:t", NS)
        )

    value_node = cell.find("main:v", NS)
    if value_node is None or value_node.text is None:
        return ""
    return value_node.text


def sheet_rows(archive: zipfile.ZipFile, target: str, shared_strings):
    root = ET.fromstring(archive.read(target))
    rows = []
    for row in root.findall("main:sheetData/main:row", NS):
        values = {}
        for cell in row.findall("main:c", NS):
            ref = cell.attrib.get("r", "")
            values[excel_column_to_index(ref)] = cell_text(cell, shared_strings)
        rows.append(values)
    return rows


def rows_to_dicts(rows):
    if not rows:
        return []
    header_row = rows[0]
    max_col = max(header_row.keys()) if header_row else -1
    headers = [header_row.get(index, "").strip() for index in range(max_col + 1)]

    data = []
    for row in rows[1:]:
        item = {}
        for index, header in enumerate(headers):
            if not header:
                continue
            item[header] = row.get(index, "").strip()
        data.append(item)
    return data


def normalize_samples(workbook_path: Path):
    with zipfile.ZipFile(workbook_path) as archive:
        shared_strings = load_shared_strings(archive)
        targets = workbook_sheet_targets(archive)

        hand_rows = rows_to_dicts(
            sheet_rows(archive, targets["手图"], shared_strings)
        )
        style_rows = rows_to_dicts(
            sheet_rows(archive, targets["款式图"], shared_strings)
        )

    hand_samples = []
    for index, row in enumerate(hand_rows, start=1):
        hand_url = row.get("手图URL", "")
        if not hand_url:
            continue
        hand_samples.append(
            {
                "id": index,
                "label": f"官方手图 {index}",
                "handUrl": hand_url,
                "linkedEnhancedStyleUrl": row.get("款式图URL", ""),
            }
        )

    style_samples = []
    for index, row in enumerate(style_rows, start=1):
        style_samples.append(
            {
                "id": index,
                "label": f"官方款式 {index}",
                "originalStyleUrl": row.get("原始款式图URL", ""),
                "enhancedStyleUrl": row.get("增强后款式图URL", ""),
            }
        )

    return {
        "workbookPath": str(workbook_path),
        "counts": {
            "handSamples": len(hand_samples),
            "styleSamples": len(style_samples),
        },
        "handSamples": hand_samples,
        "styleSamples": style_samples,
    }


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: extract_official_samples.py <workbook_path>")

    workbook_path = Path(sys.argv[1])
    if not workbook_path.exists():
        raise SystemExit(f"Workbook not found: {workbook_path}")

    payload = normalize_samples(workbook_path)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
