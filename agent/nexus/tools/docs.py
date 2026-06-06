# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Document generation and artifact management tools."""

from __future__ import annotations

import logging
import os
import shlex
import textwrap
from typing import Any

from nexus.tools.base import normalized_tool
from nexus.tools._context import get_sandbox, get_session_id, get_run_id, get_history_repository, get_workspace_path
from nexus.storage import artifact_storage_metadata, upload_artifact_async

logger = logging.getLogger(__name__)


def _resolve_workspace_or_absolute_path(path: str) -> str:
    cleaned = (path or "").strip()
    if not cleaned:
        raise ValueError("path is required")
    if cleaned.startswith("/"):
        return cleaned
    return f"{get_workspace_path().rstrip('/')}/{cleaned.lstrip('/')}"


@normalized_tool
async def extract_pdf_text(path: str, max_chars: int = 12000) -> dict[str, Any]:
    """Extract readable text from a PDF upload or a base64 text file containing a PDF."""
    sandbox = get_sandbox()
    source_path = _resolve_workspace_or_absolute_path(path)
    max_chars = max(1000, min(int(max_chars or 12000), 30000))
    output_dir = f"{get_workspace_path().rstrip('/')}/sources/pdf_text"
    sandbox.ensure_directory(output_dir)
    base_name = os.path.basename(source_path).rsplit(".", 1)[0] or "document"
    output_path = f"{output_dir}/{base_name}.txt"

    script = f"""
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

source = Path({source_path!r})
out_path = Path({output_path!r})
max_chars = {max_chars!r}

def maybe_decode_pdf(path: Path) -> Path:
    raw = path.read_bytes()
    if raw.startswith(b"%PDF"):
        return path
    text = raw.decode("ascii", errors="ignore").strip()
    if text.startswith("JVBER"):
        decoded = base64.b64decode(text)
        tmp = Path(tempfile.gettempdir()) / (path.stem + "_decoded.pdf")
        tmp.write_bytes(decoded)
        return tmp
    return path

def extract_with_python(path: Path) -> str:
    errors = []
    for module_name in ("pypdf", "PyPDF2"):
        try:
            module = __import__(module_name)
            reader = module.PdfReader(str(path))
            pages = []
            for i, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(f"--- Page {{i}} ---\\n{{text.strip()}}")
            return "\\n\\n".join(pages)
        except Exception as exc:
            errors.append(f"{{module_name}}: {{exc}}")
    raise RuntimeError("; ".join(errors))

def extract_with_pdftotext(path: Path) -> str:
    proc = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        text=True,
        capture_output=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "pdftotext failed")
    return proc.stdout

try:
    pdf_path = maybe_decode_pdf(source)
    text = ""
    errors = []
    for extractor in (extract_with_python, extract_with_pdftotext):
        try:
            text = extractor(pdf_path)
            if text.strip():
                break
        except Exception as exc:
            errors.append(str(exc))
    if not text.strip():
        raise RuntimeError("; ".join(errors) or "No text could be extracted")
    full_text = text.strip()
    out_path.write_text(full_text, encoding="utf-8")
    print(json.dumps({{
        "status": "success",
        "source_path": str(source),
        "text_path": str(out_path),
        "char_count": len(full_text),
        "text_excerpt": full_text[:max_chars],
        "truncated": len(full_text) > max_chars,
    }}))
except Exception as exc:
    print(json.dumps({{
        "status": "error",
        "message": str(exc),
        "source_path": str(source),
    }}))
    sys.exit(1)
"""

    script_path = f"/tmp/extract_pdf_text_{get_run_id()}.py"
    sandbox.write_text_file(script_path, script)
    result = sandbox.run_command(f"python3 {shlex.quote(script_path)}", timeout=90)
    stdout = str(result.get("stdout") or "").strip()
    decoded_path = f"/tmp/{base_name}_decoded.pdf"
    sandbox.run_command(
        f"rm -f {shlex.quote(script_path)} {shlex.quote(decoded_path)}",
        timeout=10,
    )
    if result.get("exit_code") != 0:
        return {
            "status": "error",
            "summary": f"PDF text extraction failed: {result.get('stderr') or stdout}",
            "detail": result,
        }
    try:
        import json

        payload = json.loads(stdout)
    except Exception:
        return {
            "status": "error",
            "summary": "PDF text extraction returned invalid output.",
            "detail": result,
        }
    if payload.get("status") != "success":
        return {
            "status": "error",
            "summary": payload.get("message") or "PDF text extraction failed.",
            "detail": payload,
        }
    return {
        "status": "success",
        "summary": f"Extracted PDF text to {payload.get('text_path')}",
        "detail": payload,
        "metadata": {
            "source_path": payload.get("source_path"),
            "text_path": payload.get("text_path"),
            "char_count": payload.get("char_count"),
            "truncated": payload.get("truncated"),
        },
    }

@normalized_tool
async def generate_pdf_report(
    title: str,
    markdown_content: str,
    filename: str | None = None
) -> dict[str, Any]:
    """
    Generate a professional PDF report from Markdown content.

    Args:
        title: The title of the report (will appear at the top).
        markdown_content: The body of the report in Markdown format.
        filename: Optional desired filename (e.g., 'analysis.pdf').
    """
    sandbox = get_sandbox()
    session_id = get_session_id()
    run_id = get_run_id()
    history_repo = get_history_repository()

    if not filename:
        filename = f"report_{run_id[:8]}.pdf"
    if not filename.endswith(".pdf"):
        filename += ".pdf"
    filename = os.path.basename(filename)
    output_relative_path = f"outputs/{filename}"
    output_path = f"{get_workspace_path().rstrip('/')}/{output_relative_path}"

    # Write the markdown content to a temp file to avoid shell quoting issues
    md_temp = f"/tmp/_pdf_md_{run_id}.md"
    sandbox.write_text_file(md_temp, markdown_content)

    # Write the PDF generation script
    pdf_script = textwrap.dedent(f"""\
import json, os, sys, pathlib

title = {repr(title)}
md_path = {repr(md_temp)}
out_path = {repr(output_path)}

os.makedirs(os.path.dirname(out_path), exist_ok=True)
md_text = pathlib.Path(md_path).read_text(encoding="utf-8")

CSS_TEMPLATE = \"\"\"
@page {{
    size: A4;
    margin: 2.5cm 2cm;
    @bottom-center {{
        content: "Page " counter(page) " of " counter(pages);
        font-size: 9pt;
        color: #888;
    }}
}}
body {{
    font-family: 'DejaVu Sans', 'Liberation Sans', Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    color: #1a1a1a;
}}
h1 {{
    font-size: 22pt;
    color: #111;
    border-bottom: 2px solid #333;
    padding-bottom: 8px;
    margin-bottom: 16px;
}}
h2 {{
    font-size: 16pt;
    color: #222;
    border-bottom: 1px solid #ccc;
    padding-bottom: 4px;
    margin-top: 24px;
}}
h3 {{ font-size: 13pt; color: #333; margin-top: 18px; }}
table {{
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
}}
th, td {{
    border: 1px solid #ccc;
    padding: 6px 10px;
    text-align: left;
    font-size: 10pt;
}}
th {{ background-color: #f0f0f0; font-weight: bold; }}
code {{
    background-color: #f4f4f4;
    padding: 2px 5px;
    border-radius: 3px;
    font-size: 10pt;
}}
pre {{
    background-color: #f4f4f4;
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 10pt;
    line-height: 1.4;
}}
blockquote {{
    border-left: 3px solid #ccc;
    margin: 12px 0;
    padding: 8px 16px;
    color: #555;
}}
ul, ol {{ padding-left: 24px; }}
li {{ margin-bottom: 4px; }}
\"\"\"

def try_weasyprint(md_text, title, out_path):
    import markdown2
    from weasyprint import HTML, CSS
    html_body = markdown2.markdown(
        md_text,
        extras=["fenced-code-blocks", "tables", "break-on-newline",
                "header-ids", "strike", "task_list"]
    )
    full_html = f\"\"\"<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{{title}}</title></head>
<body><h1>{{title}}</h1>{{html_body}}</body></html>\"\"\"
    HTML(string=full_html).write_pdf(out_path, stylesheets=[CSS(string=CSS_TEMPLATE)])
    return True

def try_fpdf(md_text, title, out_path):
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, title.encode("latin-1", errors="replace").decode("latin-1"), ln=True, align="C")
    pdf.ln(8)
    pdf.set_font("Helvetica", size=11)
    for line in md_text.splitlines():
        safe = line.encode("latin-1", errors="replace").decode("latin-1")
        if line.startswith("## "):
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 14)
            pdf.multi_cell(0, 7, safe[3:])
            pdf.set_font("Helvetica", size=11)
        elif line.startswith("# "):
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 16)
            pdf.multi_cell(0, 8, safe[2:])
            pdf.set_font("Helvetica", size=11)
        elif line.strip():
            pdf.multi_cell(0, 6, safe)
        else:
            pdf.ln(3)
    pdf.output(out_path)
    return True

errors = []
for gen_fn in (try_weasyprint, try_fpdf):
    try:
        gen_fn(md_text, title, out_path)
        size = os.path.getsize(out_path)
        print(json.dumps({{"status": "success", "path": out_path, "size": size,
                           "engine": gen_fn.__name__}}))
        sys.exit(0)
    except Exception as exc:
        errors.append(f"{{gen_fn.__name__}}: {{exc}}")

print(json.dumps({{"status": "error", "message": "; ".join(errors)}}))
sys.exit(1)
""")

    script_path = f"/tmp/gen_pdf_{run_id}.py"
    sandbox.write_text_file(script_path, pdf_script)

    res = sandbox.run_command(f"python3 {script_path}", timeout=120)
    sandbox.run_command(f"rm -f {shlex.quote(script_path)} {shlex.quote(md_temp)}", timeout=10)

    if res.get("exit_code") != 0:
        return {
            "status": "error",
            "summary": f"PDF generation failed: {res.get('stderr') or res.get('stdout')}",
            "detail": res,
        }

    try:
        import json as _json
        payload = _json.loads(str(res.get("stdout") or "").strip())
    except Exception:
        payload = {}

    if payload.get("status") != "success":
        return {
            "status": "error",
            "summary": payload.get("message") or "PDF generation returned unexpected output.",
            "detail": res,
        }

    # Upload to GCS
    try:
        content = sandbox.read_binary_file(output_path)
        gcs_url = await upload_artifact_async(
            session_id=session_id,
            run_id=run_id,
            relative_path=output_relative_path,
            content=content,
        )

        artifact = await history_repo.create_artifact(
            session_id=session_id,
            run_id=run_id,
            kind="pdf_report",
            title=title or filename,
            preview=f"Generated PDF report: {filename} ({payload.get('engine', 'unknown')} engine, {payload.get('size', 0)} bytes)",
            path=output_path,
            url=gcs_url,
            metadata={
                **artifact_storage_metadata(session_id, run_id, output_relative_path),
                "content_type": "application/pdf",
                "size": payload.get("size", 0),
                "engine": payload.get("engine", "unknown"),
            },
        )

        return {
            "status": "success",
            "summary": f"Generated PDF report: {filename}",
            "detail": {
                "filename": filename,
                "path": output_path,
                "relative_path": output_relative_path,
                "artifact_id": artifact.artifact_id,
                "url": gcs_url,
                "engine": payload.get("engine"),
                "size": payload.get("size"),
            },
        }
    except Exception as e:
        logger.exception("Failed to promote PDF to artifact")
        return {
            "status": "success",
            "summary": f"PDF generated at {filename} but failed to upload to storage: {e}",
            "detail": {"filename": filename, "path": output_path},
        }

@normalized_tool
async def save_as_artifact(path: str, title: str | None = None) -> dict[str, Any]:
    """
    Take any file created in the workspace and promote it to an artifact for the user to view.
    
    Args:
        path: Relative path to the file in the workspace (e.g., 'outputs/chart.png').
        title: Optional display title for the artifact.
    """
    sandbox = get_sandbox()
    session_id = get_session_id()
    run_id = get_run_id()
    history_repo = get_history_repository()
    
    if not sandbox.path_exists(path):
        return {
            "status": "error",
            "summary": f"File not found: {path}",
            "detail": None
        }
        
    kind = "file"
    if path.endswith((".png", ".jpg", ".jpeg")):
        kind = "image"
    elif path.endswith(".pdf"):
        kind = "pdf"
    elif path.endswith((".csv", ".json")):
        kind = "data"
        
    try:
        content = sandbox.read_binary_file(path)
        gcs_url = await upload_artifact_async(
            session_id=session_id,
            run_id=run_id,
            relative_path=path,
            content=content
        )
        
        artifact = await history_repo.create_artifact(
            session_id=session_id,
            run_id=run_id,
            kind=kind,
            title=title or os.path.basename(path),
            preview=f"Promoted {kind}: {path}",
            path=path,
            url=gcs_url,
            metadata=artifact_storage_metadata(session_id, run_id, path),
        )
        
        return {
            "status": "success",
            "summary": f"Promoted {path} to artifact.",
            "detail": {
                "artifact_id": artifact.artifact_id,
                "url": gcs_url,
                "metadata": artifact.metadata or {},
            }
        }
    except Exception as e:
        logger.exception("Failed to promote file to artifact")
        return {
            "status": "error",
            "summary": f"Failed to promote {path} to artifact: {str(e)}",
            "detail": None
        }

@normalized_tool
async def generate_excel_report(
    title: str,
    headers: list[str],
    rows: list[list[str]],
    filename: str | None = None,
    sheet_name: str = "Report",
) -> dict[str, Any]:
    """
    Generate an Excel (.xlsx) spreadsheet from tabular data.

    Args:
        title: Report title (written as the first row in bold).
        headers: Column header names.
        rows: List of row data (each row is a list of cell values).
        filename: Optional desired filename (e.g., 'sales_data.xlsx').
        sheet_name: Name of the Excel worksheet.
    """
    sandbox = get_sandbox()
    session_id = get_session_id()
    run_id = get_run_id()
    history_repo = get_history_repository()

    if not filename:
        filename = f"report_{run_id[:8]}.xlsx"
    if not filename.endswith(".xlsx"):
        filename += ".xlsx"
    filename = os.path.basename(filename)
    output_relative_path = f"outputs/{filename}"
    output_path = f"{get_workspace_path().rstrip('/')}/{output_relative_path}"

    # Write data as JSON for the sandbox script to read
    import json as _json
    data_path = f"/tmp/_xlsx_data_{run_id}.json"
    sandbox.write_text_file(data_path, _json.dumps({
        "title": title,
        "headers": headers,
        "rows": rows,
        "sheet_name": sheet_name,
    }))

    xlsx_script = textwrap.dedent(f"""\
import json, os, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

data = json.loads(open({repr(data_path)}).read())
out_path = {repr(output_path)}
os.makedirs(os.path.dirname(out_path), exist_ok=True)

wb = Workbook()
ws = wb.active
ws.title = data["sheet_name"]

# Title row
ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(data["headers"]), 1))
title_cell = ws.cell(row=1, column=1, value=data["title"])
title_cell.font = Font(bold=True, size=14, color="1F4E79")
title_cell.alignment = Alignment(horizontal="center")

# Header row
header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
header_font = Font(bold=True, color="FFFFFF", size=11)
thin_border = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)
for col_idx, header in enumerate(data["headers"], 1):
    cell = ws.cell(row=3, column=col_idx, value=header)
    cell.font = header_font
    cell.fill = header_fill
    cell.alignment = Alignment(horizontal="center")
    cell.border = thin_border

# Data rows
for row_idx, row_data in enumerate(data["rows"], 4):
    for col_idx, value in enumerate(row_data, 1):
        cell = ws.cell(row=row_idx, column=col_idx, value=value)
        cell.border = thin_border
        if row_idx % 2 == 0:
            cell.fill = PatternFill(start_color="F2F7FB", end_color="F2F7FB", fill_type="solid")

# Auto-size columns
for col_idx in range(1, len(data["headers"]) + 1):
    max_len = max(
        (len(str(ws.cell(row=r, column=col_idx).value or "")) for r in range(3, ws.max_row + 1)),
        default=10,
    )
    ws.column_dimensions[ws.cell(row=3, column=col_idx).column_letter].width = min(max_len + 4, 50)

wb.save(out_path)
size = os.path.getsize(out_path)
print(json.dumps({{"status": "success", "path": out_path, "size": size}}))
""")

    script_path = f"/tmp/gen_xlsx_{run_id}.py"
    sandbox.write_text_file(script_path, xlsx_script)

    res = sandbox.run_command(f"python3 {script_path}", timeout=60)
    sandbox.run_command(f"rm -f {shlex.quote(script_path)} {shlex.quote(data_path)}", timeout=10)

    if res.get("exit_code") != 0:
        return {
            "status": "error",
            "summary": f"Excel generation failed: {res.get('stderr') or res.get('stdout')}",
            "detail": res,
        }

    try:
        import json as _json2
        payload = _json2.loads(str(res.get("stdout") or "").strip())
    except Exception:
        payload = {}

    try:
        content = sandbox.read_binary_file(output_path)
        gcs_url = await upload_artifact_async(
            session_id=session_id,
            run_id=run_id,
            relative_path=output_relative_path,
            content=content,
        )

        artifact = await history_repo.create_artifact(
            session_id=session_id,
            run_id=run_id,
            kind="spreadsheet",
            title=title or filename,
            preview=f"Generated Excel report: {filename} ({len(rows)} rows)",
            path=output_path,
            url=gcs_url,
            metadata={
                **artifact_storage_metadata(session_id, run_id, output_relative_path),
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size": payload.get("size", 0),
                "row_count": len(rows),
            },
        )

        return {
            "status": "success",
            "summary": f"Generated Excel report: {filename} ({len(rows)} rows)",
            "detail": {
                "filename": filename,
                "path": output_path,
                "relative_path": output_relative_path,
                "artifact_id": artifact.artifact_id,
                "url": gcs_url,
            },
        }
    except Exception as e:
        logger.exception("Failed to promote Excel to artifact")
        return {
            "status": "success",
            "summary": f"Excel generated at {filename} but failed to upload: {e}",
            "detail": {"filename": filename, "path": output_path},
        }


@normalized_tool
async def generate_docx_report(
    title: str,
    markdown_content: str,
    filename: str | None = None
) -> dict[str, Any]:
    """
    Generate a Word (.docx) document from Markdown content.

    Args:
        title: The title of the document.
        markdown_content: The body in Markdown format.
        filename: Optional desired filename (e.g., 'summary.docx').
    """
    sandbox = get_sandbox()
    session_id = get_session_id()
    run_id = get_run_id()
    history_repo = get_history_repository()

    if not filename:
        filename = f"report_{run_id[:8]}.docx"
    if not filename.endswith(".docx"):
        filename += ".docx"
    filename = os.path.basename(filename)
    output_relative_path = f"outputs/{filename}"
    output_path = f"{get_workspace_path().rstrip('/')}/{output_relative_path}"

    md_temp = f"/tmp/_docx_md_{run_id}.md"
    sandbox.write_text_file(md_temp, markdown_content)

    docx_script = textwrap.dedent(f"""\
import json, os, sys, pathlib, re
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

title = {repr(title)}
md_path = {repr(md_temp)}
out_path = {repr(output_path)}

os.makedirs(os.path.dirname(out_path), exist_ok=True)
md_text = pathlib.Path(md_path).read_text(encoding="utf-8")

doc = Document()

# Style the title
title_para = doc.add_heading(title, level=0)
title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
for run in title_para.runs:
    run.font.color.rgb = RGBColor(31, 78, 121)

# Parse markdown line by line
for line in md_text.splitlines():
    stripped = line.strip()
    if not stripped:
        doc.add_paragraph("")
    elif stripped.startswith("### "):
        doc.add_heading(stripped[4:], level=3)
    elif stripped.startswith("## "):
        doc.add_heading(stripped[3:], level=2)
    elif stripped.startswith("# "):
        doc.add_heading(stripped[2:], level=1)
    elif stripped.startswith("- ") or stripped.startswith("* "):
        doc.add_paragraph(stripped[2:], style="List Bullet")
    elif re.match(r"^\\d+\\.\\s", stripped):
        text = re.sub(r"^\\d+\\.\\s", "", stripped)
        doc.add_paragraph(text, style="List Number")
    elif stripped.startswith("> "):
        p = doc.add_paragraph(stripped[2:])
        p.style = doc.styles["Intense Quote"] if "Intense Quote" in [s.name for s in doc.styles] else doc.styles["Quote"] if "Quote" in [s.name for s in doc.styles] else p.style
    elif stripped.startswith("```"):
        pass  # skip code fence markers
    else:
        p = doc.add_paragraph()
        # Handle inline bold/italic
        parts = re.split(r"(\\*\\*.*?\\*\\*|\\*.*?\\*)", stripped)
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                run = p.add_run(part[2:-2])
                run.bold = True
            elif part.startswith("*") and part.endswith("*"):
                run = p.add_run(part[1:-1])
                run.italic = True
            else:
                p.add_run(part)

doc.save(out_path)
size = os.path.getsize(out_path)
print(json.dumps({{"status": "success", "path": out_path, "size": size}}))
""")

    script_path = f"/tmp/gen_docx_{run_id}.py"
    sandbox.write_text_file(script_path, docx_script)

    res = sandbox.run_command(f"python3 {script_path}", timeout=60)
    sandbox.run_command(f"rm -f {shlex.quote(script_path)} {shlex.quote(md_temp)}", timeout=10)

    if res.get("exit_code") != 0:
        return {
            "status": "error",
            "summary": f"DOCX generation failed: {res.get('stderr') or res.get('stdout')}",
            "detail": res,
        }

    try:
        import json as _json3
        payload = _json3.loads(str(res.get("stdout") or "").strip())
    except Exception:
        payload = {}

    try:
        content = sandbox.read_binary_file(output_path)
        gcs_url = await upload_artifact_async(
            session_id=session_id,
            run_id=run_id,
            relative_path=output_relative_path,
            content=content,
        )

        artifact = await history_repo.create_artifact(
            session_id=session_id,
            run_id=run_id,
            kind="document",
            title=title or filename,
            preview=f"Generated Word document: {filename}",
            path=output_path,
            url=gcs_url,
            metadata={
                **artifact_storage_metadata(session_id, run_id, output_relative_path),
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size": payload.get("size", 0),
            },
        )

        return {
            "status": "success",
            "summary": f"Generated Word document: {filename}",
            "detail": {
                "filename": filename,
                "path": output_path,
                "relative_path": output_relative_path,
                "artifact_id": artifact.artifact_id,
                "url": gcs_url,
            },
        }
    except Exception as e:
        logger.exception("Failed to promote DOCX to artifact")
        return {
            "status": "success",
            "summary": f"DOCX generated at {filename} but failed to upload: {e}",
            "detail": {"filename": filename, "path": output_path},
        }
