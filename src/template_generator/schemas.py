"""Request, response, and critique schemas for the template generator service."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..templates.schema import Template


Severity = Literal["blocker", "major", "minor"]
IssueCategory = Literal[
    "structure",
    "section",
    "phase",
    "coverage",
    "naming",
    "pacing",
    "other",
]


class CritiqueIssue(BaseModel):
    """One specific, actionable problem with a proposed template."""

    category: IssueCategory
    severity: Severity
    description: str = Field(
        description=(
            "What is wrong, named specifically (e.g. 'section `risk` is too "
            "vague — split into compliance_risk and operational_risk')."
        )
    )
    suggested_fix: str = Field(
        description="Concrete change the implementation agent should make."
    )


class CritiqueResult(BaseModel):
    """Structured judgment of a proposed template."""

    approved: bool = Field(
        description=(
            "True iff there are zero blocker and zero major issues. Minor "
            "issues alone do not prevent approval."
        )
    )
    issues: list[CritiqueIssue] = Field(default_factory=list)
    missing_aspects: list[str] = Field(
        default_factory=list,
        description=(
            "Aspects implied by the user's description that the template does "
            "not yet capture (e.g. 'description mentions GDPR, but no "
            "compliance section exists')."
        ),
    )
    rationale: str = Field(
        description="Two or three sentences summarising the overall judgment.",
    )
    next_iteration_focus: str = Field(
        default="",
        description=(
            "If not approved, the single most important thing the next "
            "revision should focus on. Empty string if approved."
        ),
    )


class GenerationIteration(BaseModel):
    """One pass of the implementation + critique loop."""

    iteration: int
    template: Template
    critique: CritiqueResult


class SlideOutline(BaseModel):
    """One slide / page extracted from an uploaded document."""

    index: int = Field(ge=1, description="1-based position in the document.")
    title: str | None = Field(
        default=None, description="Slide title, or first line for PDFs."
    )
    content: str = Field(
        default="",
        description="Body text — bullets, paragraphs, whatever was on the slide.",
    )
    speaker_notes: str | None = Field(
        default=None,
        description="Speaker notes (PPTX only). Become `private_notes` on the topic.",
    )


class DocumentOutline(BaseModel):
    """Structured extraction of an uploaded .pptx / .pdf file."""

    source_name: str = Field(description="Original filename, for display.")
    kind: Literal["pptx", "pdf"]
    slides: list[SlideOutline]


class GenerateRequest(BaseModel):
    """POST /generate body."""

    description: str = Field(
        min_length=1,
        description="Free-form description of the meeting to design a template for.",
    )
    reference_template: str | None = Field(
        default=None,
        description=(
            "Optional name of an existing template to use as a structural "
            "reference. Must be one of the names in `templates.TEMPLATES`."
        ),
    )
    document_outline: DocumentOutline | None = Field(
        default=None,
        description=(
            "Optional structured extraction of an uploaded .pptx/.pdf. When "
            "present, the generator builds a presentation-driven template "
            "(one TOPIC per slide; speaker_notes become private_notes)."
        ),
    )
    max_iterations: int = Field(default=3, ge=1, le=8)
    name_hint: str | None = Field(
        default=None,
        description="Optional snake_case identifier suggestion for the template.",
    )


class GenerateResponse(BaseModel):
    """POST /generate response body."""

    template_id: str
    storage_path: str
    approved: bool
    iterations_used: int
    template: Template
    iterations: list[GenerationIteration]
