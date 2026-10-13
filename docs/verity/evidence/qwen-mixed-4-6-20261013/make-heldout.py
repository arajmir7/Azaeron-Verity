#!/usr/bin/env python3
"""Create original technical probes before the mixed checkpoint is evaluated on them."""

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "qwen-technical-32case-20261013/fixtures.json"


def exact(case_id: str, prompt: str, expected: str) -> dict:
    return {"id": case_id, "kind": "exact", "prompt": prompt, "expected": expected}


def invariant(case_id: str, prompt: str, required: list[str], forbidden: list[str] | None = None) -> dict:
    return {"id": case_id, "kind": "invariants", "prompt": prompt, "required": required, "forbidden": forbidden or []}


tasks = [
    exact("H-E01", "Use only the note. The amended lease begins 9 February 2027; the superseded draft said 2025. State only the amended start date.", "9 February 2027"),
    exact("H-E02", "Use only the ledger. Depot R holds 31 filters; Depot S holds 13. How many are in Depot R? Return the number alone.", "31"),
    exact("H-E03", "From this notice, answer with the name only: Priya Bose chairs the final panel; Tala Noor chaired the preliminary panel. Who chairs the final panel?", "Priya Bose"),
    exact("H-E04", "Read the record and return just the code: Shipment code XR-915 is current; XR-815 was voided. What is the current shipment code?", "XR-915"),
    exact("H-E05", "Use the schedule only. Hall Cedar closes at 21:10; Hall Birch closes at 20:05. Which hall closes earlier? Answer with the hall name.", "Hall Birch"),
    exact("H-E06", "The final exhibit was filed on Thursday, after a draft had been filed on Monday. On which weekday was the final exhibit filed? One word.", "Thursday"),
    exact("H-E07", "From the source only: Zone A contains 22 valves; Zone B contains 17. Which zone contains fewer? Return the zone letter.", "B"),
    exact("H-E08", "Read only this record: The revised inspection time is 08:45, replacing 07:30. Give only the revised inspection time.", "08:45"),
    exact("H-A01", "Compute 28 + 15. Respond with the integer only.", "43"),
    exact("H-A02", "Compute 92 - 37. Respond with the integer only.", "55"),
    exact("H-A03", "Compute 9 multiplied by 6. Respond with the integer only.", "54"),
    exact("H-A04", "Compute 96 divided by 8. Respond with the integer only.", "12"),
    exact("H-A05", "A tray has 16 ceramic cups and 11 steel cups. How many cups in all? Respond with the integer only.", "27"),
    exact("H-A06", "There are 70 lockers and 24 are occupied. How many are unoccupied? Answer with digits only.", "46"),
    exact("H-A07", "Four teams each inspect 13 units. How many units do they inspect in total? Digits only.", "52"),
    exact("H-A08", "A truck carries 7 cases on each of 8 trips. How many cases altogether? Digits only.", "56"),
    exact("H-Q01", "Source: The silver token is in drawer 4. The copper token is in drawer 7. Which drawer contains the copper token? Number only.", "7"),
    exact("H-Q02", "Source: Permit L was deferred, whereas Permit M was granted. What happened to Permit L? One word.", "deferred"),
    exact("H-Q03", "Source: The ferry departs in August, and the tram begins in December. Which vehicle begins in December? One word.", "tram"),
    exact("H-Q04", "Source: Clause C applies to visitors. Clause D applies to employees. Which clause applies to employees? Letter only.", "D"),
    exact("H-Q05", "Source: Farah authored the letter. Dev witnessed the signature. Who witnessed the signature? Name only.", "Dev"),
    exact("H-Q06", "Source: Bus 23 serves the clinic. Bus 32 serves the school. Which bus serves the school? Number only.", "32"),
    exact("H-Q07", "Source: The alloy was cooled to 5 C, then tested at 11 C. At what temperature was it tested? Number only.", "11"),
    exact("H-Q08", "Source: The parcel was scanned on 4 July and signed for on 10 July. On which July day was it signed for? Day number only.", "10"),
    invariant("H-P01", "Rewrite as one clear sentence, retaining every fact: Leena did not sign form FR-922 on 9 February 2027.", ["Leena", "not", "FR-922", "9 February 2027"], ["did sign"]),
    invariant("H-P02", "Rewrite as one clear sentence without strengthening the claim: The grant might arrive by 18 August 2027, although timing remains uncertain.", ["might", "18 August 2027", "uncertain"], ["will arrive"]),
    invariant("H-P03", "Rewrite clearly without changing counts or negation: Dev measured 26 panels, not 62, under protocol PX-53.", ["Dev", "26", "not", "62", "PX-53"]),
    invariant("H-P04", "Rewrite in one sentence without changing attribution: Citation [37] supports only the 2022 baseline, not the 2028 projection.", ["[37]", "only", "2022", "not", "2028"]),
    invariant("H-P05", "Rewrite in one sentence, preserving the quotation exactly: Farah wrote, 'The valve remains shut,' on 11 June 2027.", ["Farah", "The valve remains shut", "11 June 2027"]),
    invariant("H-P06", "Rewrite clearly without swapping locations or times: The upper desk opens at 06:20; the lower desk opens at 09:40.", ["upper", "06:20", "lower", "09:40"]),
    invariant("H-P07", "Rewrite in one sentence without changing permission or limit: Under rule C-9, Priya may postpone for up to 4 days, not 14.", ["C-9", "Priya", "may", "4", "not", "14"]),
    invariant("H-P08", "Rewrite clearly without changing the document status: Dev's 27 January 2027 memo cites Clause 6.4 and labels the estimate provisional.", ["Dev", "27 January 2027", "Clause 6.4", "provisional"]),
]

stopping = [
    {"id": "H-S01", "prompt": "Write precisely this single token and stop: RECEIVED", "expected": "RECEIVED"},
    {"id": "H-S02", "prompt": "Respond with just the word CONFIRMED.", "expected": "CONFIRMED"},
    {"id": "H-S03", "prompt": "What is 3 plus 4? Give only the digit.", "expected": "7"},
    {"id": "H-S04", "prompt": "Source: The latch is green. Which color is the latch? One word, with no explanation.", "expected": "green"},
    {"id": "H-S05", "prompt": "Return only the word DONE. End immediately after it.", "expected": "DONE"},
    {"id": "H-S06", "prompt": "Which date is later: 16 June 2027 or 17 June 2027? Return the date alone.", "expected": "17 June 2027"},
    {"id": "H-S07", "prompt": "The supplied record says the answer is V. Copy only that answer.", "expected": "V"},
    {"id": "H-S08", "prompt": "Copy this reference exactly, then stop: MN-58", "expected": "MN-58"},
]

resources = [{"id": "H-R01", "prompt": "Read these non-answer records and then answer only with FINAL-READY. " + " ".join(f"Record {i}: code T-{i:03d} is not the answer." for i in range(1, 38))}]


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def main() -> None:
    old = json.loads(OLD.read_text())
    old_prompts = {normalized(c["prompt"]) for group in ("tasks", "stopping", "resources") for c in old[group]}
    cases = tasks + stopping + resources
    assert len(tasks) == 32 and len(stopping) == 8 and len(resources) == 1
    assert len({c["id"] for c in cases}) == len(cases)
    assert len({normalized(c["prompt"]) for c in cases}) == len(cases)
    assert not old_prompts.intersection(normalized(c["prompt"]) for c in cases)
    fixture = {"classification": "ORIGINAL_SELF_AUTHORED_HELDOUT_TECHNICAL_PROBES_NOT_TRAINING_DATA", "tasks": tasks, "stopping": stopping, "resources": resources}
    target = HERE / "heldout-fixtures.json"
    with target.open("x") as stream:
        json.dump(fixture, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
