import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from lokal_ajan.tools.registry import registry
from lokal_ajan.tools.office_tools import ReadExcelTool, WriteExcelTool, ReadPdfTool, WritePdfTool
from lokal_ajan.tools.fs_tools import ReadFileTool, WriteFileTool

def test_office_tools_registration():
    schemas = registry.get_all_schemas()
    tool_names = [t["name"] for t in schemas]
    assert "read_excel" in tool_names
    assert "write_excel" in tool_names
    assert "read_pdf" in tool_names
    assert "write_pdf" in tool_names

def test_excel_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        w_excel = WriteExcelTool(workdir=tmpdir)
        r_excel = ReadExcelTool(workdir=tmpdir)
        excel_path = os.path.join(tmpdir, "test.xlsx")

        data = [
            {"Ders": "Matematik", "Saat": "09:00", "Öğretmen": "Ahmet"},
            {"Ders": "Fizik", "Saat": "10:30", "Öğretmen": "Ayşe"}
        ]
        
        # Write
        res_write = w_excel.run(path=excel_path, data_json=json.dumps(data))
        assert "Successfully wrote" in res_write
        assert os.path.exists(excel_path)

        # Read
        res_read = r_excel.run(path=excel_path)
        assert "Matematik" in res_read
        assert "Fizik" in res_read
        assert "Ayşe" in res_read

def test_pdf_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        w_pdf = WritePdfTool(workdir=tmpdir)
        r_pdf = ReadPdfTool(workdir=tmpdir)
        pdf_path = os.path.join(tmpdir, "test.pdf")

        content = "Çakabey Kültür Merkezi\n2026-2027 Ders Programı\nPazartesi: Matematik"

        # Write
        res_write = w_pdf.run(path=pdf_path, content=content)
        assert "Successfully wrote" in res_write
        assert os.path.exists(pdf_path)

        # Read
        res_read = r_pdf.run(path=pdf_path)
        assert "Çakabey" in res_read or "Matematik" in res_read

def test_fs_tools_binary_hints():
    with tempfile.TemporaryDirectory() as tmpdir:
        r_tool = ReadFileTool(workdir=tmpdir)
        w_tool = WriteFileTool(workdir=tmpdir)

        pdf_path = os.path.join(tmpdir, "document.pdf")
        xlsx_path = os.path.join(tmpdir, "sheet.xlsx")

        # read_file hints
        read_pdf_err = r_tool.run(path=pdf_path)
        assert "Cannot read PDF with 'read_file'" in read_pdf_err
        assert "'read_pdf'" in read_pdf_err

        read_xlsx_err = r_tool.run(path=xlsx_path)
        assert "Cannot read Excel with 'read_file'" in read_xlsx_err
        assert "'read_excel'" in read_xlsx_err

        # write_file hints
        write_pdf_err = w_tool.run(path=pdf_path, content="test")
        assert "Cannot write PDF with 'write_file'" in write_pdf_err
        assert "'write_pdf'" in write_pdf_err

        write_xlsx_err = w_tool.run(path=xlsx_path, content="test")
        assert "Cannot write Excel with 'write_file'" in write_xlsx_err
        assert "'write_excel'" in write_xlsx_err
