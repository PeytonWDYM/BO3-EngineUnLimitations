#include "Profile.h"
#include "Session.h"
#include "Target.h"
#include <iostream>
#include <limits>
#include <set>

int wmain(int argc, wchar_t* argv[]) {
    try {
        if (argc == 2 && std::wstring(argv[1]) == L"--help") {
            std::cout << "PatchLoader inspect|session --profile ABSOLUTE_PROFILE --pid PID [--hold-ms 1000]\n"
                         "inspect: Verify executable identity and original bytes without write access.\n"
                         "session: Apply at a fixture safe point, wait, then remove at a new safe point.\n"
                         "Supported write target: owned cooperative fixture. Stock BO3 is unsupported.\n";
            return 0;
        }
        if (argc < 6 || (argc % 2 != 0)) throw std::runtime_error("Use --help for command syntax.");
        const std::wstring command(argv[1]);
        if (command != L"inspect" && command != L"session") throw std::runtime_error("Unknown command. Use inspect or session.");
        std::filesystem::path profile_path;
        DWORD pid = 0, hold_ms = 1000;
        std::set<std::wstring> fields;
        for (int index = 2; index < argc; index += 2) {
            const std::wstring option(argv[index]);
            if (!fields.insert(option).second) throw std::runtime_error("Duplicate command option.");
            if (option == L"--profile") profile_path = argv[index + 1];
            else {
                const auto value = patch::parse_number(patch::narrow(argv[index + 1]));
                if (option == L"--pid") {
                    if (!value || value > std::numeric_limits<DWORD>::max()) throw std::runtime_error("Invalid process ID.");
                    pid = static_cast<DWORD>(value);
                } else if (option == L"--hold-ms") {
                    if (!value || value > 60000) throw std::runtime_error("Session duration must be 1 to 60000 milliseconds.");
                    hold_ms = static_cast<DWORD>(value);
                } else throw std::runtime_error("Unknown command option.");
            }
        }
        if (!pid || !profile_path.is_absolute()) throw std::runtime_error("Specify a process ID and an absolute profile path.");
        const auto profile = patch::load_profile(profile_path);
        const patch::Target target(pid, profile, command == L"session");
        std::cout << "profile id=" << profile.id << '\n';
        if (command == L"inspect") {
            target.verify_bytes(profile.records, false);
            std::cout << "original bytes verified records=" << profile.records.size() << '\n';
        } else patch::run_session(target, profile, hold_ms);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "ERROR: " << error.what() << '\n';
        return 1;
    }
}
