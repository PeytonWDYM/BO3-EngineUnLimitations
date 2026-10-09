# Failure cases written before implementation

1. A missing, duplicate, or ambiguous site leaves the production profile refused.
2. A transported predecessor loses the computed value, frame, index, flags, or stack position.
3. A relay reads a cached expected value after the live expected DWORD changes.
4. A relay changes a live register, flags, stack pointer, or unrelated frame byte.
5. A relay corrects the image chain without correcting the computed local DWORD.
6. An upstream edit changes an AAE store, intact admission word, or split transport scan.
7. An AAE installer changes the upstream correction or receives the wrong chain destination.
8. A wrong executable digest, PE identity, image ownership, protection, pointer, or guard passes admission.
9. An existing edit overlaps a guard, source hook, expected DWORD, or chain destination.
10. Preparation allocates a relay before it checks every original guard and overlap.
11. A source jump or replay LEA exceeds its signed displacement range.
12. A transaction publishes a source jump without its complete RX relay page.
13. Rollback frees the relay before it restores the source hooks.
14. Destruction frees a committed relay while the child can still execute it.
15. Preparation exceeds the caller's 30-second stopped-child budget.

The native proof uses an owned child and authored instructions. Captured game code remains private.
The proof must retain JSON receipts, executable hashes, source hashes, and a repeatable build command.
