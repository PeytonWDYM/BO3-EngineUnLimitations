# Contributor instructions

Keep changes simple and focused. Split code where it helps readers.
This repository contains only the 500K Zombies engine patch and its installer.
Read README.md for installation and build instructions.
Use a private game copy for patch tests. Do not change a player's working installation without permission.
Keep game files, dumps, account data, and backups out of Git.
Keep README.md and AGENTS.md tracked. Other Markdown notes are ignored.
Write failure cases before changing patch logic. Use focused E2E tests with repeatable results outside Git.
Check exact executable identity, native code guards, complete allocations, save data, and migration for each supported build.
Refuse unknown versions before patch writes. Do not remove guards to admit a new build.
Verify game and peer behavior before claiming compatibility, including Proton support.
Create a descriptive branch. Commit verified work with a short, clear message.
Open a pull request that states the problem, change, and test results. Include the model and harness used.
Merge only when the owner requests it.
