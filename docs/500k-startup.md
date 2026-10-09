The optional 500K launcher is built and reviewed. It remains a candidate for manual game validation.
It applies the complete VM, client-root and migration plan before the first native allocation.
Early checksum relays repair computed values before their chained stores and preserve AAE's later hook sites.
The game executable and Workshop assets stay unchanged.

Steam must start the launcher so the game inherits its normal Steam environment.
After setup, use Steam Play, load full All-around Enhancement, then select Zombies.
The parent launcher stays open until BO3 exits. Closing that parent also ends its owned game process.
The patch exists only in that process. Removal of the launch route restores stock Steam Play.

Setup and removal require Steam, BO3 and every earlier BO3 launcher to be closed:

```powershell
python -B source/launch/early_startup/SteamSetup.py setup --native-build <reviewed-build-folder> --game "<game-folder>/BlackOps3.exe"
python -B source/launch/early_startup/SteamSetup.py remove
```

Setup saves the original BO3 launch-options field, preserves existing arguments and stages four verified files privately.
It refuses changed payloads, unsupported executables, an existing wrapper or another active launch transaction.
Removal preserves unrelated Steam configuration and refuses an externally changed launch field.
The supported executable SHA-256 is `0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0`.

The fixed candidate has 500,000 usable server script slots, 18 client roots and a 32 MiB migration buffer.
Client VM capacity stays at 64,999 usable slots. This does not expand the actor pool.
Peer compatibility requires a match test. Friends may use the same candidate, but matching patches alone do not prove compatibility.

Nineteen checksum groups, ten combined transaction groups and five Steam transport groups passed independent review.
The checksum proof covers 1,069 sites, 3,207 saved-code scenarios and 6,414 authored native executions.
The read-only monitor verifies the exact process receipt, all source hooks, the complete relay arena,
the helper boot/configuration and nineteen capacity instructions before it reads the expanded pool.
Owned native enrollment and earlier job enrollment passed fresh review.

Receipts distinguish patch publication from allocation and gameplay validation.
Actual Steam startup, full AAE loading, live allocation, complete host migration, hosting and joining remain unvalidated.
Do not describe this candidate as unlimited play or a finished compatibility result.
