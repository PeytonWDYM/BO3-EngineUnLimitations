"""Capture bounded, read-only script-variable diagnostics from a verified process."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from windows_process import ACCESS_MASK, VerifiedProcess
from profile import validate
from enhanced_session import resolve_enhanced_session, verify_code_evidence
from snapshot import sample
from latest_state import LatestState


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rate", type=float, default=10)
    parser.add_argument("--duration", type=float, default=30, help="Seconds. Zero runs until interruption or process exit.")
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--expected-start-ticks", type=int)
    parser.add_argument("--latest", type=Path, help="New private JSON file for the external overlay.")
    args = parser.parse_args()
    if not 0.1 <= args.rate <= 30 or not 0 <= args.duration <= 86400 or not 1 <= args.attempts <= 4:
        parser.error("Use rate 0.1..30, duration 0..86400, and attempts 1..4.")
    if not 0 < args.pid <= 0xFFFFFFFF:
        parser.error("Use a valid Windows process identifier.")
    output = args.output.resolve()
    repo = Path(__file__).resolve().parents[3]
    if output == repo or repo in output.parents:
        parser.error("Write VM capture output outside the repository.")
    if output.exists():
        parser.error("Choose a new output file.")
    latest_path = args.latest.resolve() if args.latest else None
    if latest_path and (latest_path == repo or repo in latest_path.parents or latest_path == output):
        parser.error("Choose a separate latest file outside the repository.")
    if latest_path and output == latest_path.with_suffix(latest_path.suffix + ".tmp"):
        parser.error("The log path conflicts with the latest file's temporary path.")
    if latest_path and (latest_path.exists() or latest_path.with_suffix(latest_path.suffix + ".tmp").exists()):
        parser.error("Choose a new latest file.")
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
        instances = validate(profile)
        expected_start = args.expected_start_ticks if args.expected_start_ticks is not None else profile.get("expectedProcessStartTicks")
        with VerifiedProcess(args.pid, profile, expected_start) as process:
            enrollment = resolve_enhanced_session(process, profile)
            verify_code_evidence(process, profile, enrollment)
            instances = validate(profile, enhanced_session=enrollment)
            output.parent.mkdir(parents=True, exist_ok=True)
            if latest_path:
                latest_path.parent.mkdir(parents=True, exist_ok=True)
            latest = LatestState(latest_path) if latest_path else None
            with output.open("x", encoding="utf-8") as stream:
                def emit(event, **values):
                    row = {"event": event, "utc": datetime.now(timezone.utc).isoformat(), **values}
                    stream.write(json.dumps(row, ensure_ascii=True) + "\n")
                    stream.flush()
                    if latest:
                        latest.publish(row)
                emit("attached", pid=process.pid, path=str(process.path), processStartTicks=process.started_ticks,
                     processStartUtc=process.started_utc, sha256=process.sha256,
                     moduleBase=hex(process.module.baseaddress), imageSize=process.module.size,
                     timestamp=process.module.timestamp, profile=str(args.profile.resolve()),
                     accessMask=hex(ACCESS_MASK), rate=args.rate, attempts=args.attempts,
                     enhancedSession=str(enrollment.receipt_path) if enrollment else None,
                     serverCapacity=next((item.capacity for item in instances if item.index == 0), None),
                     gameValidation=profile["status"],
                     validationScope=profile.get("liveValidation", "Owned fixture only."),
                     consistency="Repeated equal metadata, pools, and error text are not an atomic snapshot.",
                     interpretation="Numeric slot types and current function depth do not identify suspended threads or grenade owners.")
                started = time.monotonic()
                next_sample = started
                accepted = rejected = 0
                try:
                    while not args.duration or time.monotonic() - started < args.duration:
                        delay = next_sample - time.monotonic()
                        if delay > 0:
                            time.sleep(delay)
                        if args.duration and time.monotonic() - started >= args.duration:
                            break
                        if not process.alive():
                            emit("process-exited")
                            break
                        read_started = time.monotonic()
                        reports, error, used = sample(process, profile, instances, args.attempts,
                                                      enhanced_session=enrollment)
                        read_ms = round((time.monotonic() - read_started) * 1000, 2)
                        if reports is None:
                            if not process.alive():
                                emit("process-exited")
                                break
                            rejected += 1
                            emit("rejected", error=error, attemptsUsed=used, accepted=accepted, rejected=rejected, readMilliseconds=read_ms)
                        else:
                            accepted += 1
                            emit("sample", instances=reports, attemptsUsed=used, accepted=accepted, rejected=rejected, readMilliseconds=read_ms)
                        next_sample = max(next_sample + 1 / args.rate, time.monotonic() + 1 / args.rate)
                except KeyboardInterrupt:
                    emit("interrupted")
                emit("stopped", accepted=accepted, rejected=rejected)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"VM sampler: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
