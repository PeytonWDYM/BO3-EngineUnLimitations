"""Bounded owned thread-start cases. These do not reconstruct stock chronology."""
STOP_EXIT = 0xE0510001

def register(check, run, success, early, dependency):
    def created(trace):
        assert trace["creatorThread"] != 0 and trace["returnedThread"] != 0
        assert trace["creatorThread"] != trace["returnedThread"] == trace["workerThread"]
        assert trace["returnedHandle"] != 0
        assert trace["attributesPresent"] == trace["stackSize"] == 0 and trace["creationFlags"] == 4
        assert trace["nativeParameter"] == trace["originalParameter"]
        assert trace["priorityResult"] != 0 and trace["resumeResult"] == 1
        events = trace["events"]
        stages = [event["stage"] for event in events]
        assert stages.index("thread-create") < stages.index("thread-returned") < stages.index("suspended-checked")
        assert stages.index("suspended-checked") < stages.index("thread-priority") < stages.index("thread-resume")
        for event in events:
            if event["stage"] in ("thread-create", "thread-returned", "suspended-checked", "thread-priority", "thread-resume"):
                assert event["thread"] == trace["creatorThread"]
        return stages

    def matched():
        trace = success("startup-matched")
        stages = created(trace)
        assert trace["gateMatched"] == trace["constructors"] == trace["nativeSetups"] == 1
        assert trace["gateUnmatched"] == 0 and trace["nativeContext"] == trace["originalParameter"] == 14
        assert trace["nativeEntry"] != trace["originalEntry"]
        assert stages.index("hooks-ready") < stages.index("gate-matched") < stages.index("thread-create")
        assert stages.index("thread-resume") < stages.index("gate-enter") < stages.index("runtime-ready")
        assert stages.index("runtime-ready") < stages.index("native-setup") < stages.index("native-dispatch") < stages.index("root-enter")
        assert stages.index("native-exit") < stages.index("worker-joined") < stages.index("entry-probe")
        assert stages.index("removal-denied") < stages.index("native-exit")
        assert stages.index("worker-joined") < stages.index("references-released") < stages.index("runtime-destroyed") < stages.index("hooks-removed")
        assert all(event["thread"] == trace["workerThread"] for event in trace["events"]
                   if event["stage"] in ("gate-enter", "runtime-ready", "native-setup", "native-dispatch", "root-enter", "callback", "native-exit"))
        assert trace["callbackThread"] == trace["workerThread"]
        return trace

    def unmatched():
        results = []
        for scenario, context, setups, exit_code in (("startup-wrong-entry", 14, 0, 0x510e),
                                                    ("startup-wrong-context", 13, 1, 0x520d)):
            code, trace = run(scenario)
            stages = created(trace)
            assert code == trace["targetExit"] == 0
            assert trace["gateUnmatched"] == 1 and trace["gateMatched"] == trace["constructors"] == 0
            assert trace["providerCalls"] == trace["rawPublications"] == 0 and trace["nativeSetups"] == setups
            assert trace["nativeEntry"] == trace["originalEntry"] and trace["originalParameter"] == context
            assert not any(stage in ("gate-enter", "runtime-ready", "root-enter") for stage in stages)
            joined = next(event for event in trace["events"] if event["stage"] == "worker-joined")
            assert joined["value"] == exit_code
            results.append(trace)
        return results

    def denied():
        code, trace = run("startup-denied")
        stages = created(trace)
        assert code != 0 and trace["targetExit"] == STOP_EXIT and trace["abortHresult"] == -2147024891
        assert trace["gateMatched"] == 1 and trace["gateUnmatched"] == 0
        assert trace["constructors"] == trace["nativeSetups"] == trace["providerCalls"] == trace["rawPublications"] == 0
        assert stages.index("gate-enter") < stages.index("readiness-denied")
        assert not any(stage in ("runtime-ready", "native-setup", "native-dispatch", "entry-probe", "helper-detach") for stage in stages)
        return trace

    def cold():
        results = []
        for api in ("com", "sound"):
            code, trace = run("startup-cold-" + api)
            stages = created(trace)
            assert code != 0 and trace["targetExit"] == STOP_EXIT
            assert trace["gateUnmatched"] == trace["nativeSetups"] == 1 and trace["gateMatched"] == 0
            assert trace["constructors"] == trace["providerCalls"] == trace["rawPublications"] == 0
            assert trace["nativeEntry"] == trace["originalEntry"] and trace["originalParameter"] == 13
            assert stages.index("native-setup") < stages.index("root-enter") < stages.index("early-stop")
            assert not any(stage in ("gate-enter", "runtime-ready", "raw-factory", "consumer-after", "entry-probe", "helper-detach") for stage in stages)
            results.append(trace)
        return results

    check("exact owned startup thread warms runtime before original setup", matched)
    check("wrong entry or context preserves unmatched native behavior", unmatched)
    check("worker readiness denial stops before original setup", denied)
    check("cold unmatched worker factory still stops both families", cold)
    check("existing entry and post-entry worker preserve their contract", lambda: [success("entry"), success("worker")])
    check("existing imported and TLS factories still stop cold", lambda: [early("import", "imported"), early("tls", "tls")])
    check("earlier dependency remains uncovered", dependency)
