# Owned code-integrity failure cases

These cases precede implementation. No game or Steam process runs in this proof.

- Refuse a missing or incorrect locked executable identity, wrong PE timestamp,
  machine or image size, and overflowing image addresses before returning edits.
- Refuse a missing evaluator, changed original instruction, changed nearby guard,
  unexpected region layout or protection, private rather than image memory,
  partial read, duplicate record, overlap, and overlap with any existing game edit.
- Refuse unsupported input-transform records and unproved flag consumers. Counts
  alone do not establish complete evaluator coverage.
- Execute authored endpoint snippets with equal, unequal, zero, high-bit and
  boundary operands. Compare registers and all *live* flags with the original
  equal-input computation. CMP must preserve both table loads and resulting
  EAX/EDX, including unequal inputs. XOR and NEG/ADD preserve the matched ECX=0
  outcome; only ZF is admitted live for those records. Their removed second load
  is an explicit semantic limitation, not a claim of identical memory access.
- A mismatch must produce zero edits. In an owned frozen job, all admitted edits
  must read back, retain original protection, and commit together. An injected
  later transaction failure must restore every attempted byte and protection.
  Failed rollback must keep the owned child frozen until it is terminated.
- Preserve unrelated code bytes, helper/gate files, and the 33 game instructions.
  No maintenance loop, debugger, PSS, context or hardware-register write is used.
- Produce source/artifact hashes and machine-readable case receipts in a new
  private directory. The proof establishes authored fixture behavior, not BO3
  startup, mod loading, 500k allocation, or multiplayer compatibility.
