"""The owner confirmation accepts only an exact, unedited GitHub owner action."""

import unittest

from scripts.verity_owner_confirmation import (
    COMMENT_BODY,
    OWNER_GITHUB_ID,
    PR_NUMBER,
    REPOSITORY,
    verify_comment,
    verify_packet,
)


class OwnerConfirmationTests(unittest.TestCase):
    def test_current_packet_is_exactly_bound(self):
        verify_packet()

    def test_exact_owner_comment_produces_reference(self):
        comment_id = 12345
        comment = {
            "id": comment_id,
            "issue_url": f"https://api.github.com/repos/{REPOSITORY}/issues/{PR_NUMBER}",
            "html_url": f"https://github.com/{REPOSITORY}/pull/{PR_NUMBER}#issuecomment-{comment_id}",
            "user": {"login": "arajmir7", "id": OWNER_GITHUB_ID, "type": "User"},
            "author_association": "OWNER",
            "body": COMMENT_BODY,
            "created_at": "2026-10-12T10:00:00Z",
            "updated_at": "2026-10-12T10:00:00Z",
        }
        receipt = verify_comment(comment, comment_id)
        self.assertEqual(receipt["decision"], "APPROVE_WITHIN_SCOPE")
        self.assertIn(str(comment_id), receipt["confirmation_reference"])
        self.assertEqual(
            verify_comment(
                {**comment, "body": COMMENT_BODY.replace("\n", "\r\n")}, comment_id
            ),
            receipt,
        )
        for field, value in (
            ("id", 12346),
            ("issue_url", "https://api.github.com/repos/other/repo/issues/2"),
            ("html_url", "https://github.com/other/repo/pull/2#issuecomment-12345"),
            ("author_association", "COLLABORATOR"),
            ("body", COMMENT_BODY.replace("APPROVE_WITHIN_SCOPE", "REJECT")),
            ("body_lone_cr", COMMENT_BODY.replace("\n", "\r")),
            ("body_extra_newline", COMMENT_BODY + "\n"),
            ("updated_at", "2026-10-12T10:00:01Z"),
        ):
            changed = {**comment, "body" if field.startswith("body_") else field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_comment(changed, comment_id)
        for field, value in (("id", 1), ("login", "someone-else")):
            changed = {**comment, "user": {**comment["user"], field: value}}
            with self.subTest(user_field=field), self.assertRaises(ValueError):
                verify_comment(changed, comment_id)


if __name__ == "__main__":
    unittest.main()
