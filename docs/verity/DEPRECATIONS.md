# Deprecation cleanup

The previous backend test run reported twelve Pydantic v1-style warnings:
one `@validator` and eleven class-based `Config` declarations. All originated
in Azaeron schema files, rather than a direct or transitive dependency. R14
converted the password validator to `@field_validator` and the response-model
configuration to `ConfigDict(from_attributes=True)`, preserving the existing
field and ORM serialization behavior. The affected modules are auth, audit,
organizations, documents, jobs, evidence, and assignments.

The [rerun](evidence/remediation/r14/unit-correct-origin.log) passed all 249
backend unit/security/worker/contract tests with **no warnings summary**.
Ruff and mypy also passed for the seven changed schema files. An earlier R14
attempt used the review stack's port-4700 CORS setting, causing 19 expected
test-origin rejections from tests that use port 3000; its
[log](evidence/remediation/r14/unit.log) is retained. The successful rerun used
the port-3000 origin, as `scripts/verity_gate.py` does. No warning filter or
global suppression was added.
