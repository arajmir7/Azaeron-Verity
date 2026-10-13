#!/usr/bin/env python3
"""Create original, objective non-training probes for controlled Qwen comparison."""

from __future__ import annotations

import json
from pathlib import Path

EXTRACT = [
    ("E01", "The permit was signed on 14 April 2025; the draft was filed in 2023. What is the signing date?", "14 April 2025"),
    ("E02", "Warehouse K received 18 crates; Warehouse J received 27. How many crates did Warehouse K receive?", "18"),
    ("E03", "The northern room closes at 16:30 and the southern room closes at 18:15. Which room closes later?", "southern room"),
    ("E04", "The final reviewer is Nira Sen. An earlier draft names Raj Mehta. Who is the final reviewer?", "Nira Sen"),
    ("E05", "The invoice reference is AX-407, while the purchase order is PO-82. Give only the invoice reference.", "AX-407"),
    ("E06", "The training session moved from Tuesday to Friday. Which day is current?", "Friday"),
    ("E07", "Blue team scored 6 and amber team scored 9. Which team scored fewer points?", "Blue team"),
    ("E08", "Memo revision C is effective on 3 November 2026; revision B was effective in 2024. Give the current effective date.", "3 November 2026"),
]

ARITHMETIC = [
    ("A01", "Add 17 and 26. Return only the integer.", "43"),
    ("A02", "Subtract 19 from 63. Return only the integer.", "44"),
    ("A03", "Multiply 8 by 7. Return only the integer.", "56"),
    ("A04", "Divide 84 by 7. Return only the integer.", "12"),
    ("A05", "A box has 12 red pens and 9 black pens. How many pens total? Return only the integer.", "21"),
    ("A06", "There are 45 seats; 18 are occupied. How many seats are empty? Return only the integer.", "27"),
    ("A07", "Three groups each have 14 members. How many members total? Return only the integer.", "42"),
    ("A08", "A train travels 6 km in each of 5 segments. How many km total? Return only the integer.", "30"),
]

GROUNDED = [
    ("Q01", "Source: The red folder is in cabinet 2. The green folder is in cabinet 5. Where is the green folder? Answer with only the cabinet number.", "5"),
    ("Q02", "Source: Item P was approved; item Q was rejected. What happened to item Q? Answer with one word.", "rejected"),
    ("Q03", "Source: The bridge opens in June, but the tunnel opens in September. Which structure opens in September? Answer with one word.", "tunnel"),
    ("Q04", "Source: Policy M covers interns. Policy N covers contractors. Which policy covers contractors? Answer with the policy letter.", "N"),
    ("Q05", "Source: Liya signed the note, and Omar witnessed it. Who witnessed the note? Answer with the name only.", "Omar"),
    ("Q06", "Source: Route 12 serves the museum; Route 21 serves the library. Which route serves the museum? Answer with the number only.", "12"),
    ("Q07", "Source: The sample was chilled to 4 C, then warmed to 9 C before testing. What temperature was used for testing? Answer as a number only.", "9"),
    ("Q08", "Source: The order was placed on 2 March and delivered on 8 March. On which March day was it delivered? Answer with the day number only.", "8"),
]

PRESERVE = [
    ("P01", "Rewrite clearly in one sentence without changing the facts: Mira did not approve invoice AX-407 on 14 April 2025.", ["Mira", "not", "AX-407", "14 April 2025"], ["approved"]),
    ("P02", "Rewrite clearly in one sentence without changing the facts: The report may arrive by 6 June 2026, but that date is uncertain.", ["may", "6 June 2026", "uncertain"], ["will arrive"]),
    ("P03", "Rewrite clearly in one sentence without changing the facts: Raj listed 18 units, not 80, in memo R-27.", ["Raj", "18", "not", "80", "R-27"], []),
    ("P04", "Rewrite clearly in one sentence without changing the facts: The citation [12] supports only the 2024 estimate, not the 2025 forecast.", ["[12]", "only", "2024", "not", "2025"], []),
    ("P05", "Rewrite clearly in one sentence without changing the facts: Nira said, 'The gate is closed,' on 3 May 2023.", ["Nira", "The gate is closed", "3 May 2023"], []),
    ("P06", "Rewrite clearly in one sentence without changing the facts: The east office closes at 17:00; the west office closes at 19:00.", ["east", "17:00", "west", "19:00"], []),
    ("P07", "Rewrite clearly in one sentence without changing the facts: Under rule B-4, Ana can defer up to 7 days, not 17 days.", ["B-4", "Ana", "can", "7", "not", "17"], []),
    ("P08", "Rewrite clearly in one sentence without changing the facts: Omar's 12 October 2026 note cites Section 5.2 and says the claim is unverified.", ["Omar", "12 October 2026", "Section 5.2", "unverified"], []),
]

STOPPING = [
    ("S01", "Reply with exactly: ACK", "ACK"),
    ("S02", "Reply with exactly: READY", "READY"),
    ("S03", "What is 2 plus 2? Return only the number.", "4"),
    ("S04", "Source: The key is blue. What color is the key? One word only.", "blue"),
    ("S05", "Return the single word FINAL and then stop.", "FINAL"),
    ("S06", "Choose the later date: 2 May 2023 or 3 May 2023. Return only the later date.", "3 May 2023"),
    ("S07", "The source says the answer is N. Return just the answer from the source.", "N"),
    ("S08", "Echo the reference code ZK-19 and then stop.", "ZK-19"),
]


def main() -> None:
    tasks = []
    for case_id, body, expected in EXTRACT + ARITHMETIC + GROUNDED:
        tasks.append({"id": case_id, "prompt": "Answer from the supplied text only. " + body, "kind": "exact", "expected": expected})
    for case_id, body, required, forbidden in PRESERVE:
        tasks.append({"id": case_id, "prompt": body, "kind": "invariants", "required": required, "forbidden": forbidden})
    stopping = [{"id": case_id, "prompt": prompt, "expected": expected} for case_id, prompt, expected in STOPPING]
    context = " ".join(f"Record {i}: marker L-{i:03d} is not the answer." for i in range(1, 33))
    resources = [{"id": "R01", "prompt": f"Read the records, then answer with only FINAL-OK. {context} Answer:", "minimum_tokens": 256}]
    result = {"classification": "ORIGINAL_SELF_AUTHORED_NON_TRAINING_TECHNICAL_PROBES", "tasks": tasks, "stopping": stopping, "resources": resources}
    target = Path(__file__).with_name("fixtures.json")
    if target.exists():
        raise SystemExit("fixtures already exist; refusing to overwrite")
    target.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
