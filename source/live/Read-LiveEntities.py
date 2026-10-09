"""Sample entity counts from a verified process without modifying target memory."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from entity_sample import sample
from windows_process import ACCESS_MASK, LiveProcess


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rate", type=float, default=10)
    parser.add_argument("--duration", type=float, default=0, help="Seconds. Zero runs until process exit or Ctrl+C.")
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--expected-start-ticks", type=int)
    args = parser.parse_args()
    if not (0.1 <= args.rate <= 30 and 0 <= args.duration <= 86400 and 1 <= args.attempts <= 4):
        raise ValueError("Use rate 0.1 to 30 Hz, duration 0 to 86400 seconds, and one to four attempts.")
    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    if output == repo or repo in output.parents:
        raise ValueError("Write game-derived reports outside the repository.")
    if output.exists():
        raise FileExistsError("Choose a new report path.")
    profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
    with LiveProcess(args.pid, profile, args.expected_start_ticks) as process:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", buffering=1) as stream:
            def emit(event: str, **fields) -> None:
                stream.write(json.dumps({"utc": utc(), "event": event, **fields}) + "\n")

            emit("attached", pid=process.pid, startedUtc=process.started_utc,
                 startedTicks=process.started_ticks, executable=str(process.path), sha256=process.sha256,
                 moduleBase=hex(process.module.baseaddress), imageSize=process.module.size,
                 timestamp=process.module.timestamp, profile=str(args.profile.resolve()),
                 accessMask=ACCESS_MASK, rateHz=args.rate, attempts=args.attempts,
                 consistency="Equal metadata and two equal pool reads. This is not an atomic game snapshot.")
            started = time.monotonic()
            next_sample = started
            sequence = accepted = rejected = maximum = max_high_water = 0
            reason = "duration"
            try:
                while not args.duration or time.monotonic() - started < args.duration:
                    if not process.alive():
                        emit("process_exit", pid=process.pid)
                        reason = "process_exit"
                        break
                    began = time.perf_counter()
                    report, error, attempts = sample(process, profile, args.attempts)
                    elapsed = (time.perf_counter() - began) * 1000
                    if report is None:
                        rejected += 1
                        emit("rejected", sequence=sequence, reason=error, attempts=attempts, readMs=elapsed)
                    else:
                        accepted += 1
                        maximum = max(maximum, report.get("normalActive", 0))
                        max_high_water = max(max_high_water, report.get("highWater", 0))
                        emit("sample", sequence=sequence, pool=report, attempts=attempts,
                             readMs=elapsed, maxNormalActive=maximum, maxHighWater=max_high_water)
                    sequence += 1
                    next_sample += 1 / args.rate
                    now = time.monotonic()
                    if next_sample <= now:
                        next_sample = now + 1 / args.rate
                    delay = next_sample - now
                    if args.duration:
                        delay = min(delay, max(0, started + args.duration - now))
                    time.sleep(delay)
            except KeyboardInterrupt:
                reason = "interrupted"
            emit("stopped", reason=reason, accepted=accepted, rejected=rejected,
                 elapsedSeconds=time.monotonic() - started, maxNormalActive=maximum, maxHighWater=max_high_water)
    print(json.dumps({"output": str(output), "accepted": accepted, "rejected": rejected, "reason": reason}))


if __name__ == "__main__":
    main()
