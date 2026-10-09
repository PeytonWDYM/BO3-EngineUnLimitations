#pragma once
#include "../startup_gate/GateContract.h"
#include <filesystem>
#include <span>
#include <string>

namespace bo3::late_startup {
// Owns one suspended-create child and its process-bound handshake. No debugger flags.
class OwnedChild {
    HANDLE ready_{},release_{};
    bool resumed_=false;
public:
    PROCESS_INFORMATION process{};
    startup_gate::Payload payload{};
    explicit OwnedChild(const std::filesystem::path& game,std::wstring command,
        std::span<const std::filesystem::path> helpers,DWORD deadlineMs=30000);
    ~OwnedChild();
    void Resume();
    void WaitReady(ULONGLONG deadline);
    void Release();
    void Terminate();
    bool Exited() const;
    OwnedChild(const OwnedChild&)=delete;
    OwnedChild& operator=(const OwnedChild&)=delete;
};
std::uint64_t Created(HANDLE process);
std::wstring QuoteArgument(std::wstring_view argument);
}
