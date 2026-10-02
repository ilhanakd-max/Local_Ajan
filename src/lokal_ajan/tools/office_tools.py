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

def _df_to_markdown(df) -> str:
    try:
        return df.to_markdown(index=False)
    except Exception:
        # Fallback if tabulate is not installed
        headers = [str(c) for c in df.columns]
        rows = [[str(val) if val is not None else "" for val in row] for row in df.values]
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

    def run(self, path: str, sheet_name: str | None = None) -> str:
        try:
            import pandas as pd
        except ImportError:
            return "Error: pandas is not installed. Please install pandas and openpyxl."
            
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
                    outputs.append(f"### Sheet: {s_name}\n" + (_df_to_markdown(s_df) if not s_df.empty else "_Empty sheet_"))
                return "\n\n".join(outputs) if outputs else f"Excel file '{path}' is empty."

            if df.empty:
                return f"Excel file '{path}' is empty."
                
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
registry.register(ReadPdfTool())
registry.register(WritePdfTool())
