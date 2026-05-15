"""Pydantic models for meeting templates."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


_OTHER_SECTION_ID = "other"


class NotebookSection(BaseModel):
    id: str
    label: str
    description: str
    repeated: bool = True


class Phase(BaseModel):
    id: str
    label: str
    goal: str
    target_fraction: float = Field(gt=0.0, le=1.0)
    sections_in_focus: list[str] = Field(default_factory=list)


class Template(BaseModel):
    name: str
    description: str
    sections: list[NotebookSection]
    phases: list[Phase] = Field(min_length=1)

    @model_validator(mode="after")
    def _append_other_section(self) -> "Template":
        if not any(s.id == _OTHER_SECTION_ID for s in self.sections):
            self.sections.append(
                NotebookSection(
                    id=_OTHER_SECTION_ID,
                    label="Other",
                    description=(
                        "Anything material that doesn't fit a declared section. "
                        "Prefer declared sections; use this only when nothing else fits."
                    ),
                    repeated=True,
                )
            )
        return self

    def section_ids(self) -> list[str]:
        return [s.id for s in self.sections]

    def phase_ids(self) -> list[str]:
        return [p.id for p in self.phases]

    def get_phase(self, phase_id: str) -> Phase | None:
        for p in self.phases:
            if p.id == phase_id:
                return p
        return None
