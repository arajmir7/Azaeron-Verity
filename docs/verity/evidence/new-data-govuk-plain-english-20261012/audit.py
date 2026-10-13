"""Reproduce a bounded, review-only sample from one GOV.UK publication pair."""

from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BASE = (
    "https://www.gov.uk/api/content/government/publications/"
    "code-of-practice-for-the-remediation-of-residential-buildings/"
)
DOCUMENTS = {
    "code": (
        "code-of-practice-for-the-remediation-of-residential-buildings",
        "293031ce-fb33-4181-b331-f9befa35f880",
    ),
    "guide": (
        "plain-english-guide-to-the-code-of-practice-for-the-remediation-of-"
        "residential-buildings",
        "a15c3e68-1529-4b38-9f2a-34e5d3859f0c",
    ),
}
EXPECTED_BODY_SHA256 = {
    "code": "9660554ce17980abe1451bb1c03a9b3bd05f6a4396806f143e98ce2c98016a72",
    "guide": "563b866128332cce074a1c94b9143f3c911224b858cb0cf1c7b173dbf0e7f5f1",
}
SAMPLE_IDS = ("1.1", "2.1", "2.2", "3.3")
PAIR_PATTERN = re.compile(r"<p><strong>([1-4]\.\d)(?: -)?</strong>\s*-?\s*(.*?)</p>", re.S)


def get_document(kind: str) -> tuple[dict, dict[str, str], str]:
    slug, content_id = DOCUMENTS[kind]
    request = urllib.request.Request(BASE + slug, headers={"User-Agent": "AzaeronRightsReview/1.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read(262145)
    if len(raw) > 262144:
        raise ValueError("publisher response exceeded audit bound")
    document = json.loads(raw)
    if document["content_id"] != content_id:
        raise ValueError("publisher content ID changed")
    body = document["details"]["body"]
    body_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if body_sha256 != EXPECTED_BODY_SHA256[kind]:
        raise ValueError(f"{kind} body changed; review a new revision before extracting")
    pairs = {
        identifier: html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
        for identifier, value in PAIR_PATTERN.findall(body)
    }
    if len(pairs) != 14:
        raise ValueError("expected fourteen numbered passages")
    return document, pairs, body_sha256


def main() -> None:
    code_doc, code, code_sha = get_document("code")
    guide_doc, guide, guide_sha = get_document("guide")
    if code.keys() != guide.keys():
        raise ValueError("source and guide passage IDs differ")
    if code_doc["public_updated_at"] != guide_doc["public_updated_at"]:
        raise ValueError("source and guide revision timestamps differ")
    rows = []
    for identifier in SAMPLE_IDS:
        source = code[identifier]
        target = guide[identifier]
        row = {
            "id": f"govuk-mhclg-remediation-{identifier}",
            "source_group": "govuk-mhclg-remediation-code-2025-12-12",
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "target_sha256": hashlib.sha256(target.encode()).hexdigest(),
            "source_character_count": len(source),
            "target_character_count": len(target),
            "source_content_id": code_doc["content_id"],
            "target_content_id": guide_doc["content_id"],
            "publisher_updated_at": code_doc["public_updated_at"],
            "rights_status": "OWNER_LEGAL_REVIEW_PENDING",
            "training_allowed": False,
            "semantic_review": "PENDING",
            "target_human_authorship": "UNKNOWN",
            "qualifier_lead": "reasonable" in source.lower() and "reasonable" not in target.lower(),
        }
        rows.append(row)
    sample = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    (ROOT / "review-sample.jsonl").write_text(sample, encoding="utf-8")
    result = {
        "status": "QUARANTINED_REVIEW_ONLY",
        "sample_rows": len(rows),
        "candidate_numbered_pairs": 14,
        "source_group_count": 1,
        "dataset_splits": "NONE",
        "source_group_split_policy": "KEEP_ALL_14_TOGETHER_IF_EVER_REVIEWED",
        "task_coverage": "ONE_NARROW_PLAIN_ENGLISH_SUMMARIZATION_SOURCE_ONLY",
        "target_human_authorship": "UNKNOWN",
        "qualifier_leads_among_all_pairs": sum(
            "reasonable" in code[identifier].lower()
            and "reasonable" not in guide[identifier].lower()
            for identifier in code
        ),
        "sample_sha256": hashlib.sha256(sample.encode()).hexdigest(),
        "email_pattern_leads_among_all_pairs": sum(
            bool(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", code[identifier] + guide[identifier]))
            for identifier in code
        ),
        "license_evidence": {
            "page_notice": "Crown copyright 2025; OGL v3.0 except where otherwise stated; identified third-party copyright needs permission",
            "license_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
            "observed_license_html_sha256": "f5b2b9f2af63647cde889fa6c3508f5705925295b74912c68caa28dd37e64aa5",
            "license_scope": "permits adaptation and commercial exploitation of covered information; excludes personal data and unauthorized third-party rights",
            "ai_training_permission": "OWNER_LEGAL_REVIEW_PENDING",
            "copyright_ai_context_url": "https://www.gov.uk/government/publications/report-and-impact-assessment-on-copyright-and-artificial-intelligence/report-on-copyright-and-artificial-intelligence",
        },
        "documents": {
            kind: {
                "content_id": doc["content_id"],
                "title": doc["title"],
                "public_updated_at": doc["public_updated_at"],
                "body_sha256": body_sha,
                "api_url": BASE + DOCUMENTS[kind][0],
                "page_url": "https://www.gov.uk" + doc["base_path"],
            }
            for kind, doc, body_sha in (
                ("code", code_doc, code_sha),
                ("guide", guide_doc, guide_sha),
            )
        },
        "training_allowed": False,
        "owner_admission": "PENDING",
        "legal_privacy_review": "PENDING",
        "blockers": [
            "OGL does not expressly resolve this commercial AI-training use; owner/legal review required",
            "Third-party rights and personal-data exclusions require passage-level review",
            "Published guide does not establish human target authorship or independent editorial process",
            "Eight of fourteen source summary passages use 'reasonable' where aligned guide passages omit it",
            "One source group cannot yield isolated TRAIN/VAL/CAL/TEST/OOD splits or broad Writer task coverage",
        ],
    }
    (ROOT / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
