#pragma once
#include <windows.h>
#include <winternl.h>
#include <string>

namespace process_freeze {
using CreateState = NTSTATUS(NTAPI*)(PHANDLE, ACCESS_MASK, const OBJECT_ATTRIBUTES*, HANDLE, ULONG);
using ChangeState = NTSTATUS(NTAPI*)(HANDLE, HANDLE, ULONG, PVOID, SIZE_T, ULONG);
using CreateThread = NTSTATUS(NTAPI*)(PHANDLE, ACCESS_MASK, const OBJECT_ATTRIBUTES*, HANDLE,
    PVOID, PVOID, ULONG, SIZE_T, SIZE_T, SIZE_T, PVOID);
struct NativeApi {
    CreateState create;
    ChangeState change;
    CreateThread thread;
    NativeApi();
};
struct Identity {
    DWORD pid;
    unsigned long long created;
    std::wstring image;
};
Identity ReadIdentity(HANDLE process);
void RequireIdentity(HANDLE process, const Identity& expected);

// One state reference and one exact target identity. Destruction closes the reference.
// Closing the last suspended reference can resume the process. This is not rollback.
class State final {
public:
    State(const NativeApi& api, HANDLE process, Identity identity);
    ~State();
    State(const State&) = delete;
    State& operator=(const State&) = delete;
    NTSTATUS Change(ULONG action);
    void Close();
    HANDLE Handle() const { return state_; }
private:
    const NativeApi& api_;
    HANDLE process_;
    Identity identity_;
    HANDLE state_ = nullptr;
};
}
