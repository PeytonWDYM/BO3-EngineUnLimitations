"""Check focused owned artifacts, including unchanged originals and bounded trace semantics."""
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
proof = []
for name in ["success", "changed"]:
    case = json.loads((root / f"{name}.json").read_text(encoding="utf-8-sig"))
    r = case["receipt"]
    assert case["passed"] and r["runtimeMetadataMask"] == 3 and r["runtimeMetadataReads"] > 0
    assert len(r["frames"]) >= 7 and len(r["threadObservations"]) == 1 and r["stockOriginalsObserved"] == 40
    assert r["transactionRemoteWrites"] == r["editsWritten"] == r["relayAllocations"] == 0
    assert not r["committed"] and not r["expandedPoolEnrollment"] and not r["terminated"]
    assert r["exited"] and r["exitCode"] == 0
    ticks = [x["tick"] for x in r["phases"]]
    assert ticks == sorted(ticks)
    release = next(x["tick"] for x in r["phases"] if x["name"] == "released")
    rows = [json.loads(x) for x in Path(case["receiptPath"] + ".observations.jsonl").read_text().splitlines()]
    frozen = [x for x in rows if x["phase"] == "frozen"]
    originals = [x for x in frozen if x["name"] in ["server-count", "vm-entry", "migration-original", "helper-binding"]]
    assert len(originals) == 40 and all(x["error"] == 0 and x["queryError"] == 0 for x in originals)
    assert all(x["regionBase"] <= x["address"] and x["address"] + len(bytes.fromhex(x["bytes"])) <= x["regionBase"] + x["regionSize"] for x in originals)
    baseline = {x["address"]: x["bytes"] for x in originals}
    assert all(x["tick"] >= release for x in rows if x["phase"] == "running")
    assert all(x["bytes"] == baseline[x["address"]] for x in rows if x["phase"] == "running" and x["address"] in baseline)
    assert any(x["error"] != 0 for x in frozen)  # Optional gaps are present without weakening admission.
    if name == "changed":
        assert any(x["phase"] == "running" and x["name"] == "verified-forward" and x["error"] != 0 for x in rows)
        assert any(x["phase"] == "running" and x["address"] in baseline and x["protect"] == 2 for x in rows)
    proof.append({"case": name, "all40Unchanged": True, "frozenOptionalGaps": True, "traceRows": len(rows)})
collision = json.loads((root / "trace-collision.json").read_text())["receiptPath"]
assert Path(collision + ".observations.jsonl").read_text() == "preserved"
cap = json.loads((root / "trace-cap.json").read_text())
assert cap["traceCapStopped"] and cap["receipt"]["traceTruncated"]
assert Path(cap["receiptPath"] + ".cap.observations.jsonl").stat().st_size <= 8 * 1024 * 1024
(root / "evidence-verification.json").write_text(json.dumps({"passed": True, "cases": proof,
    "reusedProof": "Frozen job-final-03 last-close/death coverage and runtime-owned-final-01 exact runtime refusal/deadline coverage; no unrelated reruns."}, indent=2))
