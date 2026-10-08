#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <cstdint>
#include <filesystem>
#include <fstream>

namespace bo3::startup_control {
struct Profile {
    std::uint32_t imageSize, poolPointerRva, hashPointerRva, helperBootRva;
};
enum class Mode { Debugger, Passive };
struct Outcome { bool timedOut = false; DWORD exitCode = 0; bool debugExitSeen = false; };

// Private JSONL evidence. Observations are passive and provisional, never VM readiness.
class Timeline {
    std::ofstream file_;
    ULONGLONG start_;
public:
    explicit Timeline(const std::filesystem::path& path);
    void Event(const char* kind, const char* fields);
};

// Own only debugger event handling and deadline cleanup. Never writes target memory/context.
Outcome Observe(const PROCESS_INFORMATION& child, const Profile& profile, Timeline& trace, Mode mode=Mode::Debugger);
}
