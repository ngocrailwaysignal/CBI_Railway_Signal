"""Minimal XLSX table writer backed only by the Python standard library."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

MergedHeader = tuple[str, int, int]

_INVALID_SHEET_NAME_CHARS = set("[]:*?/\\")


def write_xlsx_table(
    path: str | Path,
    sheet_name: str,
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    *,
    column_widths: Sequence[float] | None = None,
    merged_headers: Sequence[MergedHeader] | None = None,
) -> None:
    """Write one worksheet table to an XLSX workbook."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_headers = [str(header) for header in headers]
    if not normalized_headers:
        raise ValueError("headers must not be empty")

    header_rows, merge_refs = _build_header_rows(normalized_headers, merged_headers or [])
    normalized_rows = [
        _normalize_row(row, len(normalized_headers))
        for row in rows
    ]
    widths = _normalize_widths(column_widths, len(normalized_headers))
    safe_sheet_name = _safe_sheet_name(sheet_name)

    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", _content_types_xml())
        workbook.writestr("_rels/.rels", _root_relationships_xml())
        workbook.writestr("xl/workbook.xml", _workbook_xml(safe_sheet_name))
        workbook.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships_xml())
        workbook.writestr("xl/styles.xml", _styles_xml())
        workbook.writestr(
            "xl/worksheets/sheet1.xml",
            _worksheet_xml(
                header_rows=header_rows,
                rows=normalized_rows,
                column_widths=widths,
                merge_refs=merge_refs,
            ),
        )


def _build_header_rows(
    headers: Sequence[str],
    merged_headers: Sequence[MergedHeader],
) -> tuple[list[list[str]], list[str]]:
    if not merged_headers:
        return [list(headers)], []

    column_count = len(headers)
    top_row = [""] * column_count
    bottom_row = list(headers)
    grouped_columns: set[int] = set()
    merge_refs: list[str] = []

    for label, first_column, last_column in merged_headers:
        if first_column < 0 or last_column < first_column or last_column >= column_count:
            raise ValueError("merged header range is outside header columns")
        overlap = grouped_columns.intersection(range(first_column, last_column + 1))
        if overlap:
            raise ValueError("merged header ranges must not overlap")
        grouped_columns.update(range(first_column, last_column + 1))
        top_row[first_column] = str(label)
        if first_column != last_column:
            merge_refs.append(f"{_cell_ref(1, first_column + 1)}:{_cell_ref(1, last_column + 1)}")

    for column_index, header in enumerate(headers):
        if column_index in grouped_columns:
            continue
        top_row[column_index] = header
        bottom_row[column_index] = ""
        merge_refs.append(f"{_cell_ref(1, column_index + 1)}:{_cell_ref(2, column_index + 1)}")

    return [top_row, bottom_row], merge_refs


def _normalize_row(row: Sequence[object], column_count: int) -> list[str]:
    values = ["" if value is None else str(value) for value in row]
    if len(values) < column_count:
        values.extend([""] * (column_count - len(values)))
    return values[:column_count]


def _normalize_widths(
    column_widths: Sequence[float] | None,
    column_count: int,
) -> list[float]:
    if column_widths is None:
        return [14.0] * column_count
    widths = [max(4.0, min(float(width), 80.0)) for width in column_widths[:column_count]]
    if len(widths) < column_count:
        widths.extend([14.0] * (column_count - len(widths)))
    return widths


def _safe_sheet_name(sheet_name: str) -> str:
    name = "".join("_" if char in _INVALID_SHEET_NAME_CHARS else char for char in sheet_name)
    name = name.strip("' ") or "Sheet1"
    return name[:31]


def _worksheet_xml(
    *,
    header_rows: Sequence[Sequence[str]],
    rows: Sequence[Sequence[str]],
    column_widths: Sequence[float],
    merge_refs: Sequence[str],
) -> str:
    row_count = len(header_rows) + len(rows)
    column_count = len(column_widths)
    dimension = f"A1:{_cell_ref(max(row_count, 1), column_count)}"
    col_xml = "".join(
        (
            f'<col min="{index}" max="{index}" width="{width:.2f}" '
            'customWidth="1"/>'
        )
        for index, width in enumerate(column_widths, start=1)
    )

    sheet_rows: list[str] = []
    for row_index, row in enumerate(header_rows, start=1):
        sheet_rows.append(_row_xml(row_index, row, style_id=1))
    data_start = len(header_rows) + 1
    for row_index, row in enumerate(rows, start=data_start):
        sheet_rows.append(_row_xml(row_index, row, style_id=0))

    merge_xml = ""
    if merge_refs:
        merge_cells = "".join(f'<mergeCell ref="{escape(ref)}"/>' for ref in merge_refs)
        merge_xml = f'<mergeCells count="{len(merge_refs)}">{merge_cells}</mergeCells>'

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<dimension ref="{dimension}"/>'
        "<sheetViews><sheetView workbookViewId=\"0\"><pane ySplit=\""
        f"{len(header_rows)}\" topLeftCell=\"A{len(header_rows) + 1}\" "
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        f"<cols>{col_xml}</cols>"
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        f"{merge_xml}"
        "</worksheet>"
    )


def _row_xml(row_index: int, values: Sequence[str], *, style_id: int) -> str:
    cells = [
        _cell_xml(row_index, column_index, value, style_id=style_id)
        for column_index, value in enumerate(values, start=1)
    ]
    return f'<row r="{row_index}">{"".join(cells)}</row>'


def _cell_xml(row_index: int, column_index: int, value: str, *, style_id: int) -> str:
    ref = _cell_ref(row_index, column_index)
    style_attr = f' s="{style_id}"' if style_id else ""
    text_attr = ' xml:space="preserve"' if value != value.strip() or "\n" in value else ""
    return (
        f'<c r="{ref}" t="inlineStr"{style_attr}>'
        f"<is><t{text_attr}>{escape(value)}</t></is>"
        "</c>"
    )


def _cell_ref(row_index: int, column_index: int) -> str:
    return f"{_column_name(column_index)}{row_index}"


def _column_name(column_index: int) -> str:
    if column_index < 1:
        raise ValueError("column_index must be 1 or greater")
    name = ""
    while column_index:
        column_index, remainder = divmod(column_index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )


def _root_relationships_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook_xml(sheet_name: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        f'<sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )


def _workbook_relationships_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        "</Relationships>"
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FFEAF2F8"/>'
        '<bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        "</cellStyleXfs>"
        '<cellXfs count="2">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
        '<alignment vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0" applyFont="1" '
        'applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center" '
        'wrapText="1"/></xf>'
        "</cellXfs>"
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )
