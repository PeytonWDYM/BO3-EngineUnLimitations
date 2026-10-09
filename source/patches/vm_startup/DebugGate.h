#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <cstdint>
#include <span>
#include <vector>

namespace vm_startup {
struct Edit {
    std::uint32_t rva;
    std::vector<unsigned char> original;
    std::vector<unsigned char> replacement;
};
struct Check {
    std::uint32_t rva;
    std::vector<unsigned char> bytes;
};
struct Profile {
    std::uint32_t imageSize;
    std::uint32_t entryRva;
    std::uint32_t poolPointerRva;
    std::uint32_t hashPointerRva;
    std::vector<Check> checks;
    std::vector<Edit> edits;
};
struct AddressEdit {
    std::uintptr_t address;
    std::vector<unsigned char> original;
    std::vector<unsigned char> replacement;
};
struct Receipt {
    std::uintptr_t imageBase = 0;
    DWORD stoppedThread = 0;
    DWORD armedThreads = 0;
    DWORD retainedThreads = 0;
    DWORD restoredThreads = 0;
    DWORD editsWritten = 0;
    DWORD pendingTraps = 0;
    bool activated = false;
    bool rollbackCompleted = false;
    bool exited = false;
    DWORD exitCode = 0;
};
// The caller creates and owns a DEBUG_ONLY_THIS_PROCESS child, including failure termination.
// The readiness callback runs while the first allocation event still stops all threads.
// Preparation returns additional checked edits and performs no target writes.
// The debugger then remains attached through child exit to handle pending allocation traps.
// A refusal restores attempted byte/protection edits. The caller always terminates the rejected child.
void Activate(const PROCESS_INFORMATION& process, const Profile& profile, Receipt& receipt,
    void (*ready)(const Receipt&) = nullptr,
    std::vector<AddressEdit> (*prepare)(HANDLE, const Receipt&) = nullptr);
}
