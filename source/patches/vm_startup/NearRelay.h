#pragma once
#include "NativePlan.h"

namespace vm_startup {
// Allocated while the caller keeps every target thread stopped. Starts zeroed/RX.
// Commit retains the relay for process lifetime; refusal frees it while still stopped.
class NearRelay {
    HANDLE process_;
    std::uintptr_t address_=0;
    bool committed_=false;
public:
    NearRelay(HANDLE process,ImageRange image,std::span<const NativeEntry> entries);
    ~NearRelay();
    std::uintptr_t Address() const { return address_; }
    void Commit() { committed_=true; }
    NearRelay(const NearRelay&)=delete;
    NearRelay& operator=(const NearRelay&)=delete;
};
}
