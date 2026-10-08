#pragma once
#include "DebugGate.h"

namespace vm_startup {
std::vector<unsigned char> ReadStopped(HANDLE process, std::uintptr_t address, size_t length);
// All edits run while the debugger stops every target thread.
// An uncommitted patch restores every attempted edit before caller termination.
class PausedPatch {
    HANDLE process_;
    std::vector<AddressEdit> edits_;
    std::vector<DWORD> protections_;
    Receipt& receipt_;
    size_t attempted_ = 0;
    bool committed_ = false;
public:
    PausedPatch(HANDLE process, std::vector<AddressEdit> edits, Receipt& receipt);
    ~PausedPatch();
    void Apply();
    void Commit() { committed_ = true; }
    PausedPatch(const PausedPatch&) = delete;
    PausedPatch& operator=(const PausedPatch&) = delete;
};
}
