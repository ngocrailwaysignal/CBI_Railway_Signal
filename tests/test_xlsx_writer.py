from __future__ import annotations

from zipfile import ZipFile

from ui.exporters import write_xlsx_table


def test_write_xlsx_table_creates_required_workbook_parts(tmp_path) -> None:
    output_path = tmp_path / "interlocking.xlsx"

    write_xlsx_table(
        output_path,
        "Interlocking Table",
        ["NO", "Route", "Signal", "Normal", "Reverse"],
        [["1", "ENTRY->EXIT", "ENTRY", "P1", "P2"]],
        column_widths=[7, 18, 12, 12, 12],
        merged_headers=[("POINTS", 3, 4)],
    )

    with ZipFile(output_path) as workbook:
        names = set(workbook.namelist())
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        workbook_xml = workbook.read("xl/workbook.xml").decode("utf-8")

    assert "[Content_Types].xml" in names
    assert "xl/workbook.xml" in names
    assert "xl/worksheets/sheet1.xml" in names
    assert "xl/styles.xml" in names
    assert 'name="Interlocking Table"' in workbook_xml
    assert '<mergeCell ref="D1:E1"/>' in sheet_xml
    assert "<t>Route</t>" in sheet_xml
    assert "<t>ENTRY-&gt;EXIT</t>" in sheet_xml


def test_write_xlsx_table_exports_interlocking_ui_shape(tmp_path) -> None:
    output_path = tmp_path / "interlocking_ui.xlsx"
    headers = [
        "NO",
        "Route",
        "Signal",
        "Signal Aspect",
        "NORMAL",
        "REVERSE",
        "Reverse Route",
        "Calling-on Route",
        "Opposing Signal",
        "Track",
        "Approach Locking\nTrack",
        "Approach Locking\nRelease Time",
        "Destination Track",
        "NORMAL",
        "REVERSE",
        "Overlap",
        "Overlap\nRelease Time",
    ]
    rows = [
        [
            "1",
            "ENTRY->EXIT",
            "ENTRY",
            "GREEN",
            "P1",
            "P2",
            "",
            "",
            "-",
            "N1 -> S2",
            "N0",
            "30s",
            "S2",
            "P3",
            "P4",
            "-",
            "10s",
        ]
    ]

    write_xlsx_table(
        output_path,
        "Interlocking Table",
        headers,
        rows,
        merged_headers=[("POINTS", 4, 5), ("Flank Point", 13, 14)],
    )

    with ZipFile(output_path) as workbook:
        sheet_xml = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")

    assert len(headers) == 17
    assert '<mergeCell ref="E1:F1"/>' in sheet_xml
    assert '<mergeCell ref="N1:O1"/>' in sheet_xml
    assert "<t>P1</t>" in sheet_xml
    assert "<t>P2</t>" in sheet_xml
    assert "<t>P3</t>" in sheet_xml
    assert "<t>P4</t>" in sheet_xml
