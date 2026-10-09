#include "PausedPatch.h"
#include <algorithm>
#include <stdexcept>

namespace vm_startup {
namespace {
void Require(bool value, const char* message) {
    if (!value) throw std::runtime_error(message);
}
void Write(HANDLE process, std::uintptr_t address, std::span<const unsigned char> bytes, DWORD protection) {
    DWORD discarded = 0;
    Require(VirtualProtectEx(process, reinterpret_cast<void*>(address), bytes.size(), PAGE_EXECUTE_READWRITE,
        &discarded) != FALSE, "Cannot make stopped memory writable.");
    SIZE_T count = 0;
    const bool written = WriteProcessMemory(process, reinterpret_cast<void*>(address), bytes.data(), bytes.size(), &count)
        && count == bytes.size();
    const bool restored = VirtualProtectEx(process, reinterpret_cast<void*>(address), bytes.size(), protection, &discarded) != FALSE;
    Require(restored, "Cannot restore memory protection. Keep the child stopped.");
    Require(written, "Cannot write the complete edit. Keep the child stopped.");
    Require(FlushInstructionCache(process, reinterpret_cast<void*>(address), bytes.size()) != FALSE,
        "Cannot flush changed instructions.");
    const auto actual = ReadStopped(process, address, bytes.size());
    Require(std::equal(actual.begin(), actual.end(), bytes.begin()), "The edit readback differs.");
}
}
std::vector<unsigned char> ReadStopped(HANDLE process, std::uintptr_t address, size_t length) {
    std::vector<unsigned char> bytes(length);
    SIZE_T count = 0;
    Require(ReadProcessMemory(process, reinterpret_cast<void*>(address), bytes.data(), length, &count)
        && count == length, "Cannot read the stopped child.");
    return bytes;
}
PausedPatch::PausedPatch(HANDLE process, std::vector<AddressEdit> edits, Receipt& receipt)
    : process_(process), edits_(std::move(edits)), receipt_(receipt) {
    SYSTEM_INFO info{};
    GetSystemInfo(&info);
    for (size_t index = 0; index < edits_.size(); ++index) {
        const auto& edit = edits_[index];
        Require(!edit.original.empty() && edit.original.size() == edit.replacement.size()
            && edit.address <= UINTPTR_MAX - edit.original.size(), "Invalid stopped edit.");
        Require(edit.address / info.dwPageSize == (edit.address + edit.original.size() - 1) / info.dwPageSize,
            "An edit crosses a page. Split it into bounded records.");
        Require(ReadStopped(process_, edit.address, edit.original.size()) == edit.original,
            "A stopped edit differs from its expected original.");
        MEMORY_BASIC_INFORMATION memory{};
        Require(VirtualQueryEx(process_, reinterpret_cast<void*>(edit.address), &memory, sizeof(memory)) == sizeof(memory),
            "Cannot record original memory protection.");
        protections_.push_back(memory.Protect);
        for (size_t prior = 0; prior < index; ++prior)
            Require(edit.address + edit.original.size() <= edits_[prior].address
                || edits_[prior].address + edits_[prior].original.size() <= edit.address, "Stopped edits overlap.");
    }
}
void PausedPatch::Apply() {
    for (const auto& edit : edits_) {
        ++attempted_;
        Write(process_, edit.address, edit.replacement, protections_[attempted_-1]);
        ++receipt_.editsWritten;
    }
}
PausedPatch::~PausedPatch() {
    if (committed_ || attempted_ == 0) return;
    bool restored = true;
    while (attempted_ > 0) {
        const auto& edit = edits_[--attempted_];
        try { Write(process_, edit.address, edit.original, protections_[attempted_]); }
        catch (...) { restored = false; }
    }
    receipt_.rollbackCompleted = restored;
}
}
