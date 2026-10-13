"""Regression checks for the release contract gate (stdlib only)."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.verity_spec_gate import api_contract, canonical_sha, migration_head, run, schema_contract, trace_contract


ROOT = Path(__file__).resolve().parents[2]
OPENAPI = ROOT / "docs/verity/evidence/spec-driven-20261011/openapi.json"
SCHEMA = ROOT / "docs/verity/evidence/spec-driven-20261011/schema-catalog.json"


class SpecGateTests(unittest.TestCase):
    def test_current_trace_and_migrations(self):
        self.assertEqual(trace_contract(ROOT)["requirements"], 22)
        self.assertEqual(migration_head(ROOT), "20260929_0039")

    def test_route_contract_drift_is_rejected(self):
        original = json.loads(OPENAPI.read_text())
        changed = json.loads(OPENAPI.read_text())
        del changed["paths"]["/api/v1/ai/chat"]
        self.assertNotEqual(canonical_sha(api_contract(original)), canonical_sha(api_contract(changed)))
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "openapi.json"
            altered.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "unmapped public API path"):
                run(ROOT, altered, SCHEMA, False)

    def test_rls_or_column_drift_is_rejected(self):
        changed = json.loads(SCHEMA.read_text())
        changed["tables"][0]["rls_forced"] = not changed["tables"][0]["rls_forced"]
        self.assertNotEqual(
            canonical_sha(schema_contract(changed)),
            canonical_sha(schema_contract(json.loads(SCHEMA.read_text()))),
        )
        with tempfile.TemporaryDirectory() as directory:
            altered = Path(directory) / "schema.json"
            altered.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, "API/schema/migration drift"):
                run(ROOT, OPENAPI, altered, False)

    def test_trace_file_absence_fails_closed(self):
        current = json.loads((ROOT / "docs/verity/specs/traceability.json").read_text())
        self.assertTrue(current["rows"])
        with tempfile.TemporaryDirectory() as directory:
            temp_root = Path(directory)
            (temp_root / "docs/verity/specs").mkdir(parents=True)
            for name in ("01-PRD.md", "02-TRD.md", "03-APPFLOW.md", "04-UI-UX-DESIGN-BRIEF.md", "05-BACKEND-SCHEMA.md", "06-IMPLEMENTATION-PLAN.md"):
                (temp_root / "docs/verity/specs" / name).symlink_to(ROOT / "docs/verity/specs" / name)
            current["rows"].pop()
            (temp_root / "docs/verity/specs/traceability.json").write_text(json.dumps(current))
            with self.assertRaisesRegex(ValueError, "traceability PRD coverage mismatch"):
                trace_contract(temp_root)


if __name__ == "__main__":
    unittest.main()
