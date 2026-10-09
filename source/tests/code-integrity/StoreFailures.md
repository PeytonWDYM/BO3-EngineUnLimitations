# Fixed computed-store failures

Written before store-correction implementation. The comparison-only proof is
frozen privately; its production path remains refused.

- Refuse any missing descriptor among the exact 1,069 sites, duplicate or
  overlapping source span, unknown instruction form, wrong expected/local/index/
  chain mapping, unsupported frame offset, incomplete instruction stealing,
  unproved branch target, incorrect code digest, or declared ASLR pointer mismatch.
- Refuse executable identity, PE, memory type/protection, existing-hook and engine
  edit overlap mismatches before allocating a relay or returning edits. Preserve
  all 1,353 original comparisons and the 12 input transforms.
- Execute authored intact and split store shapes. For equal and unequal raw
  DWORDs, zero, high-bit and boundary values, read the *current* expected DWORD,
  correct the exact stack DWORD, replay the original chain store/index operation,
  and resume. Compare every observable register, live flags, stack pointer, local
  value, chain value and sentinel bytes with the original healthy operation.
- Change the expected DWORD after preparing code and before executing it. The
  result must use the new value, never a checksum frozen into a relay.
- Exercise every admitted descriptor shape and frame offset. Stolen flag-neutral
  stack operations must replay exactly; intact decrement flags must match the
  original healthy operation. No generic callback, hidden thread, scratch register
  clobber, forced branch, cookie/debug/license edit or captured code execution.
- Apply source hooks and page-bounded relay publications as one owned frozen-job
  transaction. Verify every readback and original protection. Inject failure after
  publication: rollback every source/relay byte before freeing the owned arena
  while frozen. A failed rollback keeps the child frozen until containment.
- Successful commit retains the arena through child exit. Failed admission frees
  nothing it does not own. Unknown/existing external store hooks remain refused;
  do not overwrite T7Overcharged's existing captured hooks.
- Report runtime preparation time against the unchanged 30-second startup gate.
  Produce immutable source/fixture/receipt hashes. No real game or Steam writes.
