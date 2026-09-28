from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.modules.aegiswrite.engine import (
    analyze_editorial_changes,
    apply_editorial_changes,
)
from app.modules.aegiswrite.models import EditType
from app.modules.aegiswrite.schemas import AegisRefineRequest


@pytest.mark.parametrize(
    "protected",
    [
        '"the the result is due to the fact that it works"',
        "“In order to improve the the result”",
        "'the the result'",
        "`a  =  2`",
        "```python\na  =  2\n```",
        "```python\na  =  2",
        "> In order to protect the the quote",
        "[In order to cite]",
        "https://example.com/query?why=the!!",
        "10.1234/in-order-to!!",
        "$x  +  y$",
        "The The",
        "References\nIn order to cite the the result.",
    ],
)
def test_protected_text_survives_an_editorial_pass(protected):
    source = "In order to help, the the author writes.\n" + protected
    changes = analyze_editorial_changes(source, set(EditType))
    revised = apply_editorial_changes(source, changes)
    assert revised.startswith("To help, the author writes.")
    assert revised.endswith(protected)


def test_user_locked_clause_and_numeric_values_survive():
    source = "In order to help, the the clause requires 12.5% and ₹200 on 2026-09-19."
    start, end = source.index("the the"), source.index(" requires")
    changes = analyze_editorial_changes(
        source, set(EditType), locked_spans=[(start, end)]
    )
    assert (
        apply_editorial_changes(source, changes, [(start, end)])
        == "To help, the the clause requires 12.5% and ₹200 on 2026-09-19."
    )


def test_stale_and_overlapping_edits_fail_before_acceptance():
    source = "In order to help."
    change = analyze_editorial_changes(source, set(EditType))[0]
    with pytest.raises(ValueError, match="original text"):
        apply_editorial_changes(source, [replace(change, original="stale")])
    with pytest.raises(ValueError, match="original text"):
        apply_editorial_changes(source, [change, change])
    with pytest.raises(ValueError, match="protected material"):
        apply_editorial_changes(source, [change], [(0, len(source))])


def test_invalid_locks_are_rejected_by_request_schema():
    with pytest.raises(ValidationError, match="outside"):
        AegisRefineRequest(document_id="doc", text="Text", locked_spans=[(0, 50)])
