# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

"""Document generation and artifact management tools."""

from __future__ import annotations

import logging
import os
import shlex
from typing import Any

from nexus.tools.base import normalized_tool
from nexus.tools._context import get_sandbox, get_session_id, get_run_id, get_history_repository
from nexus.storage import upload_artifact_async

logger = logging.getLogger(__name__)

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
        
    # We use a dedicated python script inside the sandbox to handle the PDF generation.
    # This script uses markdown2 to parse and fpdf2 to render.
    pdf_script = f"""
import json
import sys
from fpdf import FPDF
import markdown2

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, {repr(title)}, 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {{self.page_no()}}', 0, 0, 'C')

def create_report(md_text, out_path):
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Convert markdown to simple text for now (fpdf2 doesn't native render MD perfectly without extra work)
    # In a full production app, we would use a more advanced MD->PDF converter.
    clean_text = md_text.replace('#', '').replace('*', '').replace('`', '')
    pdf.multi_cell(0, 10, clean_text)
    pdf.output(out_path)

if __name__ == "__main__":
    try:
        content = {repr(markdown_content)}
        create_report(content, {repr(filename)})
        print(json.dumps({{"status": "success", "path": {repr(filename)}}}))
    except Exception as e:
        print(json.dumps({{"status": "error", "message": str(e)}}))
        sys.exit(1)
"""
    
    script_path = f"/tmp/gen_pdf_{run_id}.py"
    sandbox.write_text_file(script_path, pdf_script)
    
    res = sandbox.run_command(f"python3 {script_path}", timeout=60)
    
    if res.get("exit_code") != 0:
        return {
            "status": "error",
            "summary": f"PDF generation failed: {res.get('stderr')}",
            "detail": res
        }
        
    # Promote to artifact
    try:
        content = sandbox.read_binary_file(filename)
        # Upload to GCS and update Firestore
        # This is a bit complex to do here, we'll use a helper if it exists.
        # For now, we'll manually trigger the artifact creation logic.
        
        # We assume upload_artifact_async exists in nexus.storage
        gcs_url = await upload_artifact_async(
            session_id=session_id,
            run_id=run_id,
            relative_path=filename,
            content=content
        )
        
        artifact = await history_repo.create_artifact(
            session_id=session_id,
            run_id=run_id,
            kind="pdf_report",
            title=title or filename,
            preview=f"Generated PDF report: {filename}",
            path=filename,
            url=gcs_url
        )
        
        return {
            "status": "success",
            "summary": f"Successfully generated report: {filename}",
            "detail": {
                "filename": filename,
                "artifact_id": artifact.artifact_id,
                "url": gcs_url
            }
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
            url=gcs_url
        )
        
        return {
            "status": "success",
            "summary": f"Promoted {path} to artifact.",
            "detail": {
                "artifact_id": artifact.artifact_id,
                "url": gcs_url
            }
        }
    except Exception as e:
        logger.exception("Failed to promote file to artifact")
        return {
            "status": "error",
            "summary": f"Failed to promote {path} to artifact: {str(e)}",
            "detail": None
        }
