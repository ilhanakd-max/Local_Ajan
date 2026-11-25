"""Claim verification tool (report_finding) and cross-session refuted claim memory."""

import json
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field

from lokal_ajan.safety.sandbox import get_safe_path
from lokal_ajan.tools.base import BaseTool
from lokal_ajan.tools.registry import registry


def get_claim_memory_path() -> Path:
    custom = os.environ.get("LOCAI_CLAIM_MEMORY")
    if custom:
        return Path(custom).expanduser()
    return Path.home() / ".lokal_ajan" / "claim_memory.json"


def load_claim_memory() -> list[dict]:
    path = get_claim_memory_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_refuted_claim(entry: dict) -> None:
    path = get_claim_memory_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    items = load_claim_memory()
    # Avoid duplicate title+file_path entries
    key = (entry.get("title", ""), entry.get("file_path", ""))
    items = [it for it in items if (it.get("title", ""), it.get("file_path", "")) != key]
    items.append(entry)
    path.write_text(json.dumps(items[-50:], ensure_ascii=False, indent=2), encoding="utf-8")


def format_claim_memory_for_prompt() -> str:
    items = load_claim_memory()
    if not items:
        return ""
    lines = ["PREVIOUSLY REFUTED CLAIMS (do not repeat these false positives):"]
    for it in items[-10:]:
        lines.append(f"- {it.get('title')} ({it.get('file_path')}): {it.get('refuted_by')}")
    return "\n".join(lines)


class ReportFindingArgs(BaseModel):
    title: str = Field(..., description="Short title of the bug or code review finding")
    file_path: str = Field(..., description="Path to the cited source file")
    line_start: int = Field(..., ge=1, description="1-indexed starting line number")
    quoted_source: str = Field(..., description="Exact verbatim source lines copied from file_path")
    failure_scenario: str = Field(..., description="Concrete failing input and step-by-step trace")
    refutation_attempt: str = Field(..., description="Where you checked for a guard/mechanism that would prevent this")
    refuted_by: str | None = Field(None, description="If a defeating guard was found, describe it here")
    confidence: Literal["confirmed", "likely", "unverified"] = Field(..., description="Verification confidence level")
    severity: Literal["high", "medium", "low", "none"] = Field("none", description="Severity (must be 'none' if unverified)")
    verified_by: str | None = Field(None, description="Command executed to verify runtime/library behavior, if applicable")


class ReportFindingTool(BaseTool):
    name = "report_finding"
    description = "Reports a verified code review or bug finding with mandatory source quote, trace, and refutation check"
    args_schema = ReportFindingArgs
    requires_confirm = False

    def __init__(self, workdir: str | None = None):
        self.workdir = workdir

    def run(
        self,
        title: str,
        file_path: str,
        line_start: int,
        quoted_source: str,
        failure_scenario: str,
        refutation_attempt: str,
        confidence: Literal["confirmed", "likely", "unverified"],
        severity: Literal["high", "medium", "low", "none"] = "none",
        refuted_by: str | None = None,
        verified_by: str | None = None,
    ) -> str:
        try:
            resolved = get_safe_path(file_path, self.workdir) if self.workdir else file_path
        except ValueError as e:
            return f"Error: {e}"

        if not os.path.isfile(resolved):
            return f"Error: Cited file '{file_path}' does not exist."

        try:
            content = Path(resolved).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading cited file '{file_path}': {e}"

        norm_content = " ".join(content.split())
        norm_quote = " ".join(quoted_source.split())
        if not norm_quote or norm_quote not in norm_content:
            return (
                f"Error: quoted_source was not found verbatim in '{file_path}'. "
                "Read the file with 'read_file' and quote the exact source lines."
            )

        if not refutation_attempt or len(refutation_attempt.strip()) < 10:
            return "Error: refutation_attempt must describe where you looked for a guard that prevents the bug."

        if refuted_by and refuted_by.strip():
            lower_ref = refuted_by.lower()
            if "comment says" in lower_ref or "docstring says" in lower_ref:
                return "Error: A comment or docstring is not a valid refutation; verify against actual code."
            save_refuted_claim({
                "title": title.strip(),
                "file_path": file_path,
                "line_start": line_start,
                "refuted_by": refuted_by.strip(),
            })
            return f"Finding DISPROVED and recorded in claim memory (dropped): {title}"

        if confidence == "unverified" and severity != "none":
            return "Error: unverified findings cannot carry a severity; set severity='none'."

        if confidence == "confirmed" and len(failure_scenario.strip()) < 20:
            return "Error: 'confirmed' findings require a concrete step-by-step failure_scenario."

        ver_note = f" | verified_by: {verified_by}" if verified_by else ""
        return (
            f"Finding RECORDED [{confidence.upper()} | severity={severity}]: {title} "
            f"({file_path}:{line_start}){ver_note}"
        )


registry.register(ReportFindingTool())
