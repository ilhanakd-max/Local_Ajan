import os
import json
from pydantic import BaseModel, Field
from .base import BaseTool
from .registry import registry
from lokal_ajan.safety.sandbox import get_safe_path

# --- Excel Tools ---

class ReadExcelArgs(BaseModel):
    path: str = Field(..., description="Path to the .xlsx file to read")
    sheet_name: str | None = Field(None, description="Name of the sheet to read. If null, reads the active sheet.")
    max_rows: int | None = Field(100, description="Maximum number of rows to return (default 100)")

def _df_to_markdown(df) -> str:
    try:
        import tabulate  # noqa: F401
        return df.to_markdown(index=False)
    except Exception:
        # Robust fallback if tabulate is missing or fails
        headers = [str(c) for c in df.columns]
        rows = [
            [str(val) if val is not None and str(val) != "nan" else "" for val in row]
            for row in df.values
        ]
        col_widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]
        header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
        sep_line = "| " + " | ".join("-" * max(col_widths[i], 3) for i in range(len(headers))) + " |"
        row_lines = [
            "| " + " | ".join(r[i].ljust(col_widths[i]) for i in range(len(headers))) + " |"
            for r in rows
        ]
        return "\n".join([header_line, sep_line] + row_lines)

class ReadExcelTool(BaseTool):
    name = "read_excel"
    description = "Reads content from an Excel file (.xlsx) and returns it as a Markdown table"
    args_schema = ReadExcelArgs
    requires_confirm = False

    def __init__(self, workdir: str | None = None):
        self.workdir = workdir

    def run(self, path: str, sheet_name: str | None = None, max_rows: int | None = 100) -> str:
        try:
            import pandas as pd
        except ImportError:
            return "Error: pandas is not installed. Please install pandas, openpyxl and tabulate."
            
        try:
            if self.workdir:
                path = get_safe_path(path, self.workdir)
                
            if not os.path.exists(path):
                return f"Error: File '{path}' does not exist."
                
            target_sheet = sheet_name if (sheet_name is not None and sheet_name != "") else 0
            df = pd.read_excel(path, sheet_name=target_sheet, engine='openpyxl')
            if isinstance(df, dict):
                outputs = []
                for s_name, s_df in df.items():
                    if s_df.empty:
                        outputs.append(f"### Sheet: {s_name}\n_Empty sheet_")
                        continue
                    total = len(s_df)
                    if max_rows and total > max_rows:
                        rendered = _df_to_markdown(s_df.head(max_rows)) + f"\n\n_... (ilk {max_rows} satır gösterildi, toplam {total} satır)_"
                    else:
                        rendered = _df_to_markdown(s_df)
                    outputs.append(f"### Sheet: {s_name}\n" + rendered)
                return "\n\n".join(outputs) if outputs else f"Excel file '{path}' is empty."

            if df.empty:
                return f"Excel file '{path}' is empty."

            total = len(df)
            if max_rows and total > max_rows:
                return _df_to_markdown(df.head(max_rows)) + f"\n\n_... (ilk {max_rows} satır gösterildi, toplam {total} satır)_"
                
            return _df_to_markdown(df)
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading excel file: {e}"

class WriteExcelArgs(BaseModel):
    path: str = Field(..., description="Path to the .xlsx file to write")
    data_json: str = Field(..., description="Data to write in JSON string format (should be a list of dictionaries)")
    sheet_name: str | None = Field(default="Sheet1", description="Name of the sheet to write to")

class WriteExcelTool(BaseTool):
    name = "write_excel"
    description = "Creates a new Excel file (.xlsx) from JSON data (list of objects)"
    args_schema = WriteExcelArgs
    requires_confirm = True

    def __init__(self, workdir: str | None = None):
        self.workdir = workdir

    def run(self, path: str, data_json: str, sheet_name: str = "Sheet1") -> str:
        try:
            import pandas as pd
        except ImportError:
            return "Error: pandas is not installed. Please install pandas and openpyxl."
            
        try:
            if self.workdir:
                path = get_safe_path(path, self.workdir)
                
            data = json.loads(data_json)
            if not isinstance(data, list):
                return "Error: data_json must be a JSON list of dictionaries."
                
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            
            df = pd.DataFrame(data)
            df.to_excel(path, sheet_name=sheet_name, index=False, engine='openpyxl')
            return f"Successfully wrote Excel data to {path}"
        except json.JSONDecodeError:
            return "Error: Invalid JSON data format."
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error writing excel file: {e}"

class AppendExcelArgs(BaseModel):
    path: str = Field(..., description="Path to the existing .xlsx file")
    rows_json: str = Field(..., description="JSON list of rows to append (e.g. [['val1', 10], ['val2', 20]] or [{'Header1': 'val1', ...}])")
    sheet_name: str | None = Field(None, description="Sheet name. If null, appends to the active sheet.")
    copy_style: bool | None = Field(True, description="Whether to copy formatting, colors, and fonts from the preceding row")

class AppendExcelTool(BaseTool):
    name = "append_excel"
    description = "Appends new rows to an existing Excel (.xlsx) file while preserving all existing styles, formulas, colors, and fonts"
    args_schema = AppendExcelArgs
    requires_confirm = True

    def __init__(self, workdir: str | None = None):
        self.workdir = workdir

    def run(self, path: str, rows_json: str, sheet_name: str | None = None, copy_style: bool = True) -> str:
        try:
            import openpyxl
            from copy import copy
        except ImportError:
            return "Error: openpyxl is not installed."

        try:
            if self.workdir:
                path = get_safe_path(path, self.workdir)

            if not os.path.exists(path):
                return f"Error: File '{path}' does not exist. Use 'write_excel' to create a new file first."

            try:
                rows_data = json.loads(rows_json)
            except json.JSONDecodeError:
                return "Error: rows_json must be valid JSON."

            if not isinstance(rows_data, list):
                return "Error: rows_json must be a list of rows."

            if not rows_data:
                return "No rows provided to append."

            wb = openpyxl.load_workbook(path, data_only=False)
            if sheet_name and sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
            else:
                ws = wb.active

            # Convert dict rows to ordered list if dicts are provided
            sample = rows_data[0]
            if isinstance(sample, dict):
                header_row = [cell.value for cell in ws[1]]
                converted_rows = []
                for item in rows_data:
                    if isinstance(item, dict):
                        row = [item.get(h, "") for h in header_row]
                        converted_rows.append(row)
                    else:
                        converted_rows.append(item)
                rows_data = converted_rows

            added_count = 0
            for r_data in rows_data:
                if not isinstance(r_data, (list, tuple)):
                    r_data = [r_data]

                prev_row_idx = ws.max_row
                ws.append(list(r_data))
                new_row_idx = ws.max_row
                added_count += 1

                if copy_style and prev_row_idx >= 1:
                    for col_idx in range(1, len(r_data) + 1):
                        prev_cell = ws.cell(row=prev_row_idx, column=col_idx)
                        new_cell = ws.cell(row=new_row_idx, column=col_idx)
                        if prev_cell.has_style:
                            if prev_cell.font: new_cell.font = copy(prev_cell.font)
                            if prev_cell.border: new_cell.border = copy(prev_cell.border)
                            if prev_cell.fill: new_cell.fill = copy(prev_cell.fill)
                            if prev_cell.number_format: new_cell.number_format = copy(prev_cell.number_format)
                            if prev_cell.alignment: new_cell.alignment = copy(prev_cell.alignment)

            wb.save(path)
            return f"Successfully appended {added_count} row(s) to '{path}' (sheet: {ws.title}) preserving styles and formulas."
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error appending to excel file: {e}"

class EditExcelCellsArgs(BaseModel):
    path: str = Field(..., description="Path to the existing .xlsx file")
    updates_json: str = Field(..., description="JSON object mapping cell coordinates to values/formulas, e.g. {'B5': 150, 'C5': '=A5*B5'}")
    sheet_name: str | None = Field(None, description="Sheet name. If null, uses the active sheet.")

class EditExcelCellsTool(BaseTool):
    name = "edit_excel_cells"
    description = "Updates specific cell values or formulas in an Excel (.xlsx) file without affecting formatting, colors, or formulas in other cells"
    args_schema = EditExcelCellsArgs
    requires_confirm = True

    def __init__(self, workdir: str | None = None):
        self.workdir = workdir

    def run(self, path: str, updates_json: str, sheet_name: str | None = None) -> str:
        try:
            import openpyxl
        except ImportError:
            return "Error: openpyxl is not installed."

        try:
            if self.workdir:
                path = get_safe_path(path, self.workdir)

            if not os.path.exists(path):
                return f"Error: File '{path}' does not exist."

            try:
                updates = json.loads(updates_json)
            except json.JSONDecodeError:
                return "Error: updates_json must be valid JSON."

            if not isinstance(updates, dict):
                return "Error: updates_json must be a JSON dictionary mapping coordinates (e.g. 'A1') to values."

            wb = openpyxl.load_workbook(path, data_only=False)
            if sheet_name and sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
            else:
                ws = wb.active

            for coord, val in updates.items():
                ws[coord] = val

            wb.save(path)
            return f"Successfully updated {len(updates)} cell(s) in '{path}' (sheet: {ws.title}) while preserving all existing formatting and formulas."
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error updating excel cells: {e}"

# --- PDF Tools ---

class ReadPdfArgs(BaseModel):
    path: str = Field(..., description="Path to the .pdf file to read")
    start_page: int | None = Field(None, description="Starting page number (1-indexed)")
    end_page: int | None = Field(None, description="Ending page number (1-indexed)")

class ReadPdfTool(BaseTool):
    name = "read_pdf"
    description = "Reads text content from a PDF file"
    args_schema = ReadPdfArgs
    requires_confirm = False

    def __init__(self, workdir: str | None = None):
        self.workdir = workdir

    def run(self, path: str, start_page: int | None = None, end_page: int | None = None) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            return "Error: pypdf is not installed. Please install pypdf."
            
        try:
            if self.workdir:
                path = get_safe_path(path, self.workdir)
                
            if not os.path.exists(path):
                return f"Error: File '{path}' does not exist."
                
            reader = PdfReader(path)
            num_pages = len(reader.pages)
            
            if num_pages == 0:
                return f"PDF file '{path}' is empty or contains no readable pages."
                
            s_idx = max(0, (start_page - 1)) if start_page is not None else 0
            e_idx = min(num_pages, end_page) if end_page is not None else num_pages
            
            if s_idx >= num_pages or s_idx >= e_idx:
                return f"Error: Invalid page range. Document has {num_pages} pages."
                
            text = []
            for i in range(s_idx, e_idx):
                page = reader.pages[i]
                page_text = page.extract_text()
                if page_text:
                    text.append(f"--- Page {i+1} ---\n{page_text}")
                    
            result = "\n".join(text)
            if not result.strip():
                return f"Could not extract text from the specified pages of '{path}'. It may be a scanned image."
            return result
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading PDF file: {e}"

class WritePdfArgs(BaseModel):
    path: str = Field(..., description="Path to the .pdf file to write")
    content: str = Field(..., description="Text content to write into the PDF")

class WritePdfTool(BaseTool):
    name = "write_pdf"
    description = "Creates a simple PDF file containing the provided text"
    args_schema = WritePdfArgs
    requires_confirm = True

    def __init__(self, workdir: str | None = None):
        self.workdir = workdir

    def run(self, path: str, content: str) -> str:
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.utils import simpleSplit
        except ImportError:
            return "Error: reportlab is not installed. Please install reportlab."
            
        try:
            if self.workdir:
                path = get_safe_path(path, self.workdir)
                
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            
            c = canvas.Canvas(path, pagesize=letter)
            width, height = letter
            margin = 40
            y_position = height - margin
            
            c.setFont("Helvetica", 12)
            
            lines = content.split('\n')
            for line in lines:
                # Basic wrapping
                wrapped_lines = simpleSplit(line, "Helvetica", 12, width - 2 * margin)
                for w_line in wrapped_lines:
                    if y_position < margin:
                        c.showPage()
                        c.setFont("Helvetica", 12)
                        y_position = height - margin
                    c.drawString(margin, y_position, w_line)
                    y_position -= 15
                    
            c.save()
            return f"Successfully wrote PDF to {path}"
        except ValueError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error writing PDF file: {e}"

# Register tools
registry.register(ReadExcelTool())
registry.register(WriteExcelTool())
registry.register(AppendExcelTool())
registry.register(EditExcelCellsTool())
registry.register(ReadPdfTool())
registry.register(WritePdfTool())
