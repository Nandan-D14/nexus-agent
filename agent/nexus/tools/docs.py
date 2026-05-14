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

    dependency_check = textwrap.dedent(
        """
        import importlib.util
        import sys
        missing = [
            module
            for module in ("fpdf", "markdown2")
            if importlib.util.find_spec(module) is None
        ]
        if missing:
            print(",".join(missing))
            sys.exit(1)
        """
    ).strip()
    dependency_result = sandbox.run_command(
        f"python3 -c {shlex.quote(dependency_check)}",
        timeout=20,
    )
    if dependency_result.get("exit_code") != 0:
        missing = str(dependency_result.get("stdout") or dependency_result.get("stderr") or "").strip()
        return {
            "status": "error",
            "summary": (
                "PDF generation dependencies are missing in the sandbox"
                f"{': ' + missing if missing else ''}."
            ),
            "detail": dependency_result,
        }
        
    # We use a dedicated python script inside the sandbox to handle the PDF generation.
    # This script uses markdown2 to parse and fpdf2 to render.
    pdf_script = f"""
import json
import sys
from html.parser import HTMLParser
from fpdf import FPDF
import markdown2

class MarkdownTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._list_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4", "p", "div", "tr", "pre", "blockquote"):
            self._newline()
        elif tag == "br":
            self._newline()
        elif tag in ("ul", "ol"):
            self._list_depth += 1
            self._newline()
        elif tag == "li":
            self._newline()
            self.parts.append("  " * max(self._list_depth - 1, 0) + "- ")

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "p", "div", "li", "tr", "pre", "blockquote"):
            self._newline()
        elif tag in ("ul", "ol"):
            self._list_depth = max(0, self._list_depth - 1)
            self._newline()

    def handle_data(self, data):
        cleaned = " ".join((data or "").split())
        if cleaned:
            self.parts.append(cleaned + " ")

    def _newline(self):
        if self.parts and not self.parts[-1].endswith("\\n"):
            self.parts.append("\\n")

    def text(self):
        lines = []
        for raw in "".join(self.parts).splitlines():
            line = " ".join(raw.split()).strip()
            if line:
                lines.append(line)
        return "\\n".join(lines)

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, {repr(title)}, 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {{self.page_no()}}', 0, 0, 'C')

def markdown_to_plain_text(md_text):
    html = markdown2.markdown(md_text, extras=["fenced-code-blocks", "tables", "break-on-newline"])
    parser = MarkdownTextParser()
    parser.feed(html)
    return parser.text()

def safe_pdf_text(text):
    return (text or "").encode("latin-1", errors="replace").decode("latin-1")

def create_report(md_text, out_path):
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    clean_text = markdown_to_plain_text(md_text)
    for line in clean_text.splitlines():
        if not line.strip():
            pdf.ln(4)
            continue
        pdf.multi_cell(0, 7, safe_pdf_text(line))
    pdf.output(out_path)

if __name__ == "__main__":
    try:
        content = {repr(markdown_content)}
        create_report(content, {repr(output_path)})
        print(json.dumps({{"status": "success", "path": {repr(output_path)}}}))
    except Exception as e:
        print(json.dumps({{"status": "error", "message": str(e)}}))
        sys.exit(1)
"""
    
    script_path = f"/tmp/gen_pdf_{run_id}.py"
    sandbox.write_text_file(script_path, pdf_script)
    
    res = sandbox.run_command(f"python3 {script_path}", timeout=60)
    sandbox.run_command(f"rm -f {shlex.quote(script_path)}", timeout=10)
    
    if res.get("exit_code") != 0:
        return {
            "status": "error",
            "summary": f"PDF generation failed: {res.get('stderr')}",
            "detail": res
        }
        
    # Promote to artifact
    try:
        content = sandbox.read_binary_file(output_path)
        # Upload to GCS and update Firestore
        # This is a bit complex to do here, we'll use a helper if it exists.
        # For now, we'll manually trigger the artifact creation logic.
        
        # We assume upload_artifact_async exists in nexus.storage
        gcs_url = await upload_artifact_async(
            session_id=session_id,
            run_id=run_id,
            relative_path=output_relative_path,
            content=content
        )
        
        artifact = await history_repo.create_artifact(
            session_id=session_id,
            run_id=run_id,
            kind="pdf_report",
            title=title or filename,
            preview=f"Generated PDF report: {filename}",
            path=output_path,
            url=gcs_url,
            metadata=artifact_storage_metadata(session_id, run_id, output_relative_path),
        )
        
        return {
            "status": "success",
            "summary": f"Successfully generated report: {filename}",
            "detail": {
                "filename": filename,
                "path": output_path,
                "output_path": output_path,
                "relative_path": output_relative_path,
                "artifact_id": artifact.artifact_id,
                "url": gcs_url,
                "metadata": artifact.metadata or {},
            },
            "output_path": output_path,
            "path": output_path,
            "url": gcs_url,
            "artifact_id": artifact.artifact_id,
        }
    except Exception as e:
        logger.exception("Failed to promote PDF to artifact")
        return {
            "status": "success",
            "summary": f"PDF generated at {filename} but failed to upload to storage.",
            "detail": str(e)
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
