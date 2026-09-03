import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string


class ProviderFailure(Exception):
    def __init__(self, code, message, *, transient=False):
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.transient = transient


@dataclass(frozen=True)
class ProviderResult:
    structured_output: dict
    request_id: str = ""
    usage: dict | None = None


class OpenAIAnalysisProvider:
    def analyze(self, *, model, system_prompt, input_payload, schema, image_data_url=None):
        if not settings.OPENAI_API_KEY:
            raise ProviderFailure(
                "ai_configuration_missing",
                "AI provider configuration is not available.",
            )
        content = [{"type": "input_text", "text": json.dumps(input_payload)}]
        if image_data_url:
            content.append({"type": "input_image", "image_url": image_data_url})
        body = {
            "model": model,
            "store": False,
            "instructions": system_prompt,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "bb_builders_analysis",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as error:
            if error.code == 429:
                raise ProviderFailure(
                    "provider_rate_limited",
                    "The AI provider is temporarily rate limited.",
                    transient=True,
                ) from error
            if error.code >= 500:
                raise ProviderFailure(
                    "provider_unavailable",
                    "The AI provider is temporarily unavailable.",
                    transient=True,
                ) from error
            raise ProviderFailure(
                "analysis_failed", "The AI provider rejected the request."
            ) from error
        except TimeoutError as error:
            raise ProviderFailure(
                "provider_timeout", "The AI provider request timed out.", transient=True
            ) from error
        except (OSError, urllib.error.URLError) as error:
            raise ProviderFailure(
                "provider_unavailable",
                "The AI provider is temporarily unavailable.",
                transient=True,
            ) from error
        try:
            output_text = next(
                item["text"]
                for output in payload["output"]
                for item in output.get("content", [])
                if item.get("type") == "output_text"
            )
            structured = json.loads(output_text)
        except (KeyError, StopIteration, TypeError, json.JSONDecodeError) as error:
            raise ProviderFailure(
                "invalid_structured_response",
                "The AI provider returned an invalid structured response.",
            ) from error
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return ProviderResult(structured, str(payload.get("id", "")), usage)


class FakeAnalysisProvider:
    """Deterministic network-free provider used only when explicitly configured."""

    def analyze(self, *, model, system_prompt, input_payload, schema, image_data_url=None):
        del model, system_prompt, schema
        failures = {
            "timeout": ("provider_timeout", "The AI provider request timed out.", True),
            "rate_limit": (
                "provider_rate_limited",
                "The AI provider is temporarily rate limited.",
                True,
            ),
            "unavailable": (
                "provider_unavailable",
                "The AI provider is temporarily unavailable.",
                True,
            ),
            "permanent_failure": (
                "analysis_failed",
                "The AI provider rejected the request.",
                False,
            ),
        }
        if settings.AI_FAKE_MODE in failures:
            code, message, transient = failures[settings.AI_FAKE_MODE]
            raise ProviderFailure(code, message, transient=transient)
        if settings.AI_FAKE_MODE == "invalid_schema":
            return ProviderResult({"invalid": True}, "fake-invalid", None)
        usage = (
            {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
            if settings.AI_FAKE_INCLUDE_USAGE
            else None
        )
        if input_payload.get("task_type") == "document_synthesis":
            candidates = [
                candidate
                for page_result in input_payload.get("page_results", [])
                for candidate in page_result.get("result", {}).get("candidates", [])
            ]
            return ProviderResult(
                {
                    "document_type_candidate": "construction_document",
                    "document_summary": "Deterministic test synthesis.",
                    "candidates": candidates,
                    "unresolved_questions": [],
                },
                "fake-synthesis",
                usage,
            )
        page = input_payload["page"]
        excerpt = page.get("native_text", "")[:120]
        evidence = {
            "document_page_id": page["document_page_id"],
            "page_number": page["page_number"],
            "drawing_sheet_id": page.get("drawing_sheet_id"),
            "sheet_number": page.get("sheet_number", ""),
            "evidence_excerpt": excerpt,
            "visual_evidence_description": ""
            if excerpt
            else "The configured fake provider received this exact rendered page.",
        }
        return ProviderResult(
            {
                "page_type_candidate": "drawing_sheet"
                if page.get("sheet_number")
                else "document_page",
                "summary": "Deterministic test page analysis.",
                "candidates": [
                    {
                        "category": "open_question",
                        "subject": "Fake-provider validation candidate",
                        "value": "Deterministic fake output for pipeline validation only.",
                        "support": "uncertain",
                        "evidence": [evidence],
                    }
                ],
                "open_questions": [],
            },
            f"fake-page-{page['document_page_id']}",
            usage,
        )


def get_analysis_provider():
    return import_string(settings.AI_PROVIDER_CLASS)()
