#pragma once
#include "OwnedChild.h"

namespace bo3::late_startup {
// Reads the exact locked gate DLL. It never executes the local DLL entry.
class MappedGate {
    std::filesystem::path file_;
    HMODULE local_{};
    DWORD stateRva_{},bootRva_{};
    DWORD size_{};
    std::uintptr_t remote_{};
public:
    explicit MappedGate(const std::filesystem::path&);
    ~MappedGate();
    void Admit(HANDLE process);
    startup_gate::State Read(HANDLE process) const;
    std::uintptr_t Base() const {return remote_;}
    void VerifyWaiting(HANDLE process,const startup_gate::Payload&,std::uint64_t generation) const;
    MappedGate(const MappedGate&)=delete;
    MappedGate& operator=(const MappedGate&)=delete;
};
}
