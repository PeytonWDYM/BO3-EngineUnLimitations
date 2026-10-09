#pragma once
#include "NativeState.h"
#include <vector>
#ifdef BO3_PROCESS_SUSPEND_TEST
#include <functional>
#endif

namespace process_freeze {
// PHNT JobObjectFreezeInformation (18). All filter, swap and reserved fields stay zero.
struct JobFreezeInformation {
    ULONG flags;
    BOOLEAN freeze;
    BOOLEAN swap;
    UCHAR reserved[2];
    ULONG wakeHigh;
    ULONG wakeLow;
};
static_assert(sizeof(JobFreezeInformation) == 16);
static_assert(offsetof(JobFreezeInformation, freeze) == 4);
using SetJobInformation = NTSTATUS(NTAPI*)(HANDLE, ULONG, PVOID, ULONG);
struct NativeJobApi {
    SetJobInformation set;
    NativeJobApi();
};
NTSTATUS ChangeOwnedJobFreeze(const NativeJobApi& api, HANDLE job, HANDLE process,
    const Identity& identity, bool freeze);

inline constexpr NTSTATUS kNotImplemented = static_cast<NTSTATUS>(0xC0000002);
// True when ntdll is Wine's, as under Proton.
bool WineNtdll();
std::vector<DWORD> ThreadIds(DWORD pid);
#ifdef BO3_PROCESS_SUSPEND_TEST
void SetSuspendInventoryObserver(std::function<void(HANDLE)> observer);
#endif
// Wine and Proton return STATUS_NOT_IMPLEMENTED for the job freeze. This fallback suspends the owned process.
// NtSuspendProcess stops only the threads that exist, so Verify refuses any thread added or ended since.
class ProcessSuspend {
public:
    NTSTATUS Suspend(HANDLE process, const Identity& identity);
    NTSTATUS Resume(HANDLE process);
    void Verify() const;
    bool Active() const { return active_; }
private:
    Identity identity_{};
    std::vector<DWORD> threads_;
    bool active_ = false;
};
}
