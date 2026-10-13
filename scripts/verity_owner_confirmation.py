"""Verify a personally posted GitHub owner comment for one exact base packet.

This is an account-authentication receipt, not dataset, technical, or release
approval. The owner must post the comment in GitHub themselves; this program
only reads GitHub's API and fails closed on missing or altered evidence.
"""

import argparse
import hashlib
import http.client
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKET = (
    ROOT
    / "docs/verity/evidence/qwen-controlled-conversion-20261011"
    / "base-owner-decision-pending.json"
)
PACKET_SHA256 = "eb6f3f0615628abedd9baecd5eab2b5595e1841f844157e35a8449963c6a2314"
CANDIDATE_SHA256 = "19fe23dd9302d4cb73e8cf9866f42b6a73399c9ec9398c28a340cda1acf1b8ce"
OWNER_LOGIN = "arajmir7"
OWNER_GITHUB_ID = 236520801
REPOSITORY = "arajmir7/Azaeron-Verity"
PR_NUMBER = 2
COMMENT_BODY = "\n".join(
    (
        "AZAERON_OWNER_CONFIRMATION_V1",
        "Decision: APPROVE_WITHIN_SCOPE",
        f"Packet-SHA256: {PACKET_SHA256}",
        f"Candidate-SHA256: {CANDIDATE_SHA256}",
        "Permitted-use: commercial_derivative_training",
        "Scope: exact controlled third-party Qwen3-4B base only",
        "Excludes: dataset admission, human technical acceptance, production release",
    )
)


def verify_packet() -> None:
    if hashlib.sha256(PACKET.read_bytes()).hexdigest() != PACKET_SHA256:
        raise ValueError("Reviewed base packet bytes changed")
    packet = json.loads(PACKET.read_bytes())
    if (
        packet["decision"] != "PENDING"
        or len(packet["subjects"]) != 1
        or packet["subjects"][0]["kind"] != "BASE_MODEL"
        or packet["subjects"][0]["sha256"] != CANDIDATE_SHA256
        or packet["subjects"][0]["permitted_uses"] != ["commercial_derivative_training"]
    ):
        raise ValueError("Base-only packet scope changed")


def fetch_comment(comment_id: int) -> dict:
    """Read only the fixed GitHub API host/path, with a strict response cap."""
    if comment_id <= 0:
        raise ValueError("A positive GitHub issue-comment ID is required")
    connection = http.client.HTTPSConnection("api.github.com", timeout=10)
    try:
        connection.request(
            "GET",
            f"/repos/{REPOSITORY}/issues/comments/{comment_id}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "azaeron-verity-owner-confirmation/1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"GitHub comment lookup failed: HTTP {response.status}")
        body = response.read(65_537)
        if len(body) > 65_536:
            raise ValueError("GitHub comment response exceeds limit")
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError("GitHub comment response is not an object")
        return result
    finally:
        connection.close()


def verify_comment(comment: dict, comment_id: int) -> dict:
    expected_api = f"https://api.github.com/repos/{REPOSITORY}/issues/{PR_NUMBER}"
    expected_html = (
        f"https://github.com/{REPOSITORY}/pull/{PR_NUMBER}#issuecomment-{comment_id}"
    )
    user = comment.get("user")
    if (
        comment.get("id") != comment_id
        or comment.get("issue_url") != expected_api
        or comment.get("html_url") != expected_html
        or not isinstance(user, dict)
        or user.get("login") != OWNER_LOGIN
        or user.get("id") != OWNER_GITHUB_ID
        or user.get("type") != "User"
        or comment.get("author_association") != "OWNER"
        or not isinstance(comment.get("body"), str)
        or comment["body"].replace("\r\n", "\n") != COMMENT_BODY
        or not comment.get("created_at")
        or comment.get("updated_at") != comment.get("created_at")
    ):
        raise ValueError("Owner, PR, exact decision, or unedited-comment check failed")
    body_sha256 = hashlib.sha256(COMMENT_BODY.encode()).hexdigest()
    return {
        "schema_version": 1,
        "mechanism": "GITHUB_PR_ISSUE_COMMENT_ACCOUNT_AUTHENTICATION",
        "repository": REPOSITORY,
        "pr_number": PR_NUMBER,
        "owner_login": OWNER_LOGIN,
        "owner_github_id": OWNER_GITHUB_ID,
        "comment_id": comment_id,
        "comment_url": expected_html,
        "created_at": comment["created_at"],
        "reviewed_packet_sha256": PACKET_SHA256,
        "candidate_sha256": CANDIDATE_SHA256,
        "decision": "APPROVE_WITHIN_SCOPE",
        "permitted_use": "commercial_derivative_training",
        "comment_body_sha256": body_sha256,
        "confirmation_reference": f"github-issue-comment:{comment_id}:sha256:{body_sha256}",
        "limitations": [
            "Authenticates control of the repository-owner GitHub account, not physical identity or third-party rights.",
            "Dataset admission, human technical acceptance and release require separate evidence and decisions.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--instructions", action="store_true")
    group.add_argument("--comment-id", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    verify_packet()
    if args.instructions:
        if args.output:
            parser.error("--output requires --comment-id")
        print(
            f"Post this exact comment personally at https://github.com/{REPOSITORY}/pull/{PR_NUMBER}:"
        )
        print(COMMENT_BODY)
        return
    if args.output is None:
        parser.error("--comment-id requires --output")
    receipt = verify_comment(fetch_comment(args.comment_id), args.comment_id)
    if args.output.exists():
        parser.error("Refusing to overwrite an existing confirmation receipt")
    args.output.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(receipt["confirmation_reference"])


if __name__ == "__main__":
    main()
