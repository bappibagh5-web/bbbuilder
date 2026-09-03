from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SupportLevel = Literal["explicit", "strongly_supported", "inferred", "uncertain"]
CandidateCategory = Literal[
    "project_fact",
    "date_deadline",
    "bid_condition",
    "scope_trade",
    "responsibility",
    "permit_inspection",
    "landlord_requirement",
    "owner_third_party_item",
    "commercial",
    "submittal_closeout",
    "open_question",
]


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_page_id: int
    page_number: int = Field(ge=1)
    drawing_sheet_id: int | None
    sheet_number: str
    evidence_excerpt: str = Field(max_length=500)
    visual_evidence_description: str = Field(max_length=500)


class MachineCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: CandidateCategory
    subject: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=2000)
    support: SupportLevel
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=10)


class PageAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_type_candidate: str = Field(max_length=100)
    summary: str = Field(max_length=1500)
    candidates: list[MachineCandidate] = Field(max_length=100)
    open_questions: list[str] = Field(max_length=30)


class DocumentAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type_candidate: str = Field(max_length=100)
    document_summary: str = Field(max_length=3000)
    candidates: list[MachineCandidate] = Field(max_length=500)
    unresolved_questions: list[str] = Field(max_length=100)


PAGE_SCHEMA_VERSION = "page-analysis.v1"
DOCUMENT_SCHEMA_VERSION = "document-analysis.v1"


def json_schema_for(task_type):
    model = PageAnalysisResult if task_type == "page_analysis" else DocumentAnalysisResult
    return model.model_json_schema()


def validate_result(task_type, value):
    model = PageAnalysisResult if task_type == "page_analysis" else DocumentAnalysisResult
    return model.model_validate(value).model_dump(mode="json")
