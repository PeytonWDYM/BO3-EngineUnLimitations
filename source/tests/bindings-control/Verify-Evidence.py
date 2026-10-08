"""Independently decode the fixed nine records and 33 stock hashes from owned receipts."""
import hashlib
import json
import struct
import sys
from pathlib import Path
import pefile

directory = Path(sys.argv[1])
inventory = json.loads((directory / "merged-inventory.json").read_text(encoding="utf-8-sig"))
exports = {e.name.decode(): e.address for e in pefile.PE(str(directory / "Bo3EnhancedHelper.dll")).DIRECTORY_ENTRY_EXPORT.symbols if e.name}
stock = [(r["rva"] + r["immediateOffset"], bytes.fromhex(r["bytes"])[r["immediateOffset"]:r["immediateOffset"]+4])
         for r in inventory["serverCountInstructions"]]
stock += [(r["rva"], bytes.fromhex(r["original5"])) for r in inventory["nativeHooks"]]
stock += [(rva, bytes.fromhex(raw)) for rva, raw in [
    (0x13619e0,"4889742410"),(0x13617f0,"4053554156"),(0x21f9aa0,"3b0d02d555157521"),
    (0x21fa750,"48895c2410"),(0x12e1c0,"48895c2408"),(0x2277a60,"40574883ec20"),
    (0x1361a50,"e8db080000"),(0x12e226,"83f803741f"),(0xb253f,"bf00002800"),(0x21fa7ae,"c744245c03000000")]]
assert len(stock) == 33
checks = []
for case in ["success","guard","allocated","helper","extra-thread","membership","rollback","rollback-failed","deadline","thaw","release","early-exit"]:
    evidence = json.loads((directory / f"{case}.json").read_text())
    r = evidence["receipt"]
    assert evidence["passed"] and r["startupMethod"] == "late-crt-job-freeze-bindings-control"
    assert r["serverTotal"] == 130000 and r["serverUsable"] == 129999 and r["clientRoots"] == 8
    assert not r["expandedPoolEnrollment"] and not r["liveAllocationValidated"] and r["gameInstructionEdits"] == 0
    assert r["debugRegisterWrites"] == 0 and not r["attached"] and not r["detached"]
    assert Path(evidence["receiptPath"]).name.endswith("-bindings-control.json")
    assert json.loads(Path(evidence["receiptPath"]).read_text()) == r
    assert Path(evidence["receiptPath"]).stat().st_size < 16384
    if r["editsWritten"]:
        assert r["editsWritten"] == 9 and len(r["publicationReadbacks"]) == 9 and len(r["stockSpanSha256"]) == 33
        assert r["helperBootBefore"] == r["helperBootAfter"] and r["stock33Verified"]
        # Fixture game addresses differ from the executable image. Recover the inert base from the first known span.
        image = r["stockSpanSha256"][0]["address"] - stock[0][0]
        for row, (rva, original) in zip(r["stockSpanSha256"], stock):
            assert row["address"] == image + rva
            assert row["before"] == row["after"] == hashlib.sha256(original).hexdigest()
        helper = lambda name: r["helperBase"] + exports[name]
        game = lambda rva: image + rva
        records = {
            helper("Bo3VmStateBindings"): struct.pack("<Q4I3Q", image,500001,18,8,1,helper("NativeOriginalReader"),helper("NativeOriginalWriter"),helper("NativeOriginalInsert")),
            helper("Bo3VmErrorBindings"): struct.pack("<4Q",game(0x20ec0b0),helper("NativeOriginalError"),helper("ReadNativeState"),helper("WriteNativeState")),
            helper("Bo3MigrationVersionBranches"): struct.pack("<2Q",game(0x12e24a),game(0x12e22b)),
            helper("Bo3MigrationLoadBindings"): struct.pack("<2Q",helper("MigrationLoadReentry"),game(0x20ec0b0)),
            helper("Bo3MigrationReentries"): struct.pack("<7Q",*(game(x) for x in [0x13619e5,0x13617f5,0x21f9aa8,0x17756fa8,0x21fa755,0x12e1c5,0x21f9ac9])),
            helper("Bo3MigrationFlushBindings"): struct.pack("<2Q",helper("MigrationFlushReentry"),game(0x2277a66)),
        }
        publications = {row["address"]: bytes.fromhex(row["after"]) for row in r["publicationReadbacks"]}
        for address, expected in records.items():
            assert publications[address] == expected
        migration = publications[helper("Bo3MigrationBindings")]
        assert struct.unpack_from("<2I", migration)[0:] == (0xc6000000 | (18 << 20) | 500001,33554432)
        assert struct.unpack_from("<7Q", migration, 8) == tuple([helper(x) for x in ["MigrationHeaderReentry","MigrationDataReentry","MigrationHeaderAckReentry","MigrationSendHeaderReentry"]] + [game(x) for x in [0x1362330,0x20fc7d0,0x20fc7c0]])
        for address, names in [(r["relay"],["ReadStateOrDrop","WriteStateOrDrop","InsertNativeStateKey","VmErrorPrelude"]),
                               (r["relay"]+64,["ReceiveMigrationHeader","ReceiveMigrationData","ReceiveMigrationHeaderAck","SendMigrationHeader","LoadMigrationState","FlushMigrationState","SendHeaderAck","MigrationVersionGate"])]:
            expected = b"".join(b"\xff\x25\0\0\0\0" + struct.pack("<Q",helper(name)) + b"\0\0" for name in names)
            assert publications[address] == expected
        assert all(not any(bytes.fromhex(row["before"])) for row in r["publicationReadbacks"])
    if case in ["success","deadline"]:
        assert r["committed"] and r["released"] and r["freezeStatus"] == r["thawStatus"] == 0
    elif case in ["guard","allocated","helper","extra-thread","membership","early-exit"]:
        assert r["editsWritten"] == 0 and not r["released"]
    checks.append({"case":case,"receiptBytes":Path(evidence["receiptPath"]).stat().st_size})
target = json.loads((directory / "success.json.target.json").read_text())
assert target["passed"] and target["helperBound"] and target["all19Counts"] and not target["debuggerAtReturn"]
(directory / "independent-evidence.json").write_text(json.dumps({"passed":True,"cases":checks,
    "scope":"Independent fixed-record decoding, stock33 hash proof, native receipts and resumed owned target. No game execution."},indent=2))

death=json.loads((directory / "parent-death.json").read_text())
assert death["passed"] and death["partialEdits"]==1 and not death["gateReturned"] and death["controllerExitCode"]==86 and death["targetExitCode"]==0
