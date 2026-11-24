"""Pure-Python structured data converter: JSON <-> YAML <-> XML <-> CSV <-> XLSX."""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import openpyxl
import yaml


def _xml_element_to_obj(elem: ET.Element) -> Any:
    children = list(elem)
    if not children:
        text = (elem.text or "").strip()
        if elem.attrib:
            out = dict(elem.attrib)
            if text:
                out["_text"] = text
            return out
        return text

    result: dict[str, Any] = dict(elem.attrib)
    grouped: dict[str, list[Any]] = {}
    for child in children:
        grouped.setdefault(child.tag, []).append(_xml_element_to_obj(child))
    for tag, items in grouped.items():
        result[tag] = items[0] if len(items) == 1 else items
    return result


def _obj_to_xml_element(tag: str, value: Any) -> ET.Element:
    elem = ET.Element(str(tag))
    if isinstance(value, dict):
        for k, v in value.items():
            if isinstance(v, list):
                for item in v:
                    elem.append(_obj_to_xml_element(str(k), item))
            else:
                elem.append(_obj_to_xml_element(str(k), v))
    elif isinstance(value, list):
        for item in value:
            elem.append(_obj_to_xml_element("item", item))
    elif value is not None:
        elem.text = str(value)
    return elem


def _normalize_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        if not data:
            return []
        if all(isinstance(row, dict) for row in data):
            return data
        return [{"value": row} for row in data]
    if isinstance(data, dict):
        # Unwrap single list wrapper (e.g., XML root {"items": [...]})
        if len(data) == 1:
            only_val = next(iter(data.values()))
            if isinstance(only_val, list):
                return _normalize_rows(only_val)
            if isinstance(only_val, dict):
                return _normalize_rows(only_val)
        return [data]
    return [{"value": data}]


def load_structured_data(src_path: Path, src_format: str) -> Any:
    if src_format == "json":
        return json.loads(src_path.read_text(encoding="utf-8-sig"))
    if src_format == "yaml":
        return yaml.safe_load(src_path.read_text(encoding="utf-8-sig"))
    if src_format == "xml":
        root = ET.fromstring(src_path.read_text(encoding="utf-8-sig"))
        return {root.tag: _xml_element_to_obj(root)}
    if src_format == "csv":
        with src_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            return list(reader)
    if src_format == "xlsx":
        wb = openpyxl.load_workbook(src_path, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            headers = [str(h) if h is not None else f"col_{idx}" for idx, h in enumerate(next(rows_iter))]
        except StopIteration:
            return []
        records: list[dict[str, Any]] = []
        for row in rows_iter:
            records.append({headers[i]: row[i] if i < len(row) else None for i in range(len(headers))})
        return records
    raise ValueError(f"Unsupported structured input format: {src_format}")


def dump_structured_data(data: Any, dst_path: Path, dst_format: str) -> None:
    if dst_format == "json":
        dst_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return
    if dst_format == "yaml":
        dst_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return
    if dst_format == "xml":
        if isinstance(data, dict) and len(data) == 1:
            root_tag = next(iter(data.keys()))
            root_elem = _obj_to_xml_element(root_tag, data[root_tag])
        else:
            root_elem = _obj_to_xml_element("root", data)
        tree = ET.ElementTree(root_elem)
        ET.indent(tree, space="  ")
        tree.write(dst_path, encoding="utf-8", xml_declaration=True)
        return
    if dst_format in {"csv", "xlsx"}:
        rows = _normalize_rows(data)
        headers: list[str] = []
        for row in rows:
            for key in row.keys():
                skey = str(key)
                if skey not in headers:
                    headers.append(skey)
        if dst_format == "csv":
            with dst_path.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=headers)
                if headers:
                    writer.writeheader()
                for row in rows:
                    writer.writerow({str(k): (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in row.items()})
            return
        wb = openpyxl.Workbook()
        ws = wb.active
        if headers:
            ws.append(headers)
            for row in rows:
                ws.append([
                    json.dumps(row.get(h), ensure_ascii=False) if isinstance(row.get(h), (dict, list)) else row.get(h)
                    for h in headers
                ])
        wb.save(dst_path)
        return
    raise ValueError(f"Unsupported structured output format: {dst_format}")


def convert_structured_data(src_path: Path, src_format: str, dst_path: Path, dst_format: str) -> None:
    data = load_structured_data(src_path, src_format)
    dump_structured_data(data, dst_path, dst_format)
