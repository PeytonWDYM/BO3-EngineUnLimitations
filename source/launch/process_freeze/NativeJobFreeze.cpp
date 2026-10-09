#include "NativeJobFreeze.h"
#include <TlHelp32.h>
#include <algorithm>
#include <stdexcept>

namespace process_freeze {
#ifdef BO3_PROCESS_SUSPEND_TEST
namespace {std::function<void(HANDLE)> inventoryObserver;}
void SetSuspendInventoryObserver(std::function<void(HANDLE)> observer) {inventoryObserver=std::move(observer);}
#endif
NativeJobApi::NativeJobApi() {
    set = reinterpret_cast<SetJobInformation>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "NtSetInformationJobObject"));
    if (!set) throw std::runtime_error("Required native job export is absent.");
}
NTSTATUS ChangeOwnedJobFreeze(const NativeJobApi& api, HANDLE job, HANDLE process,
    const Identity& identity, bool freeze) {
    RequireIdentity(process, identity);
    BOOL member = FALSE;
    if (!IsProcessInJob(process, job, &member) || !member)
        throw std::runtime_error("Owned process is outside the freeze job.");
    struct OneProcessList { DWORD assigned; DWORD listed; ULONG_PTR pid[2]; } members{};
    const auto queried = QueryInformationJobObject(job, JobObjectBasicProcessIdList, &members, sizeof(members), nullptr);
    const auto error = queried ? ERROR_SUCCESS : GetLastError();
    if (!queried || members.assigned != 1 || members.listed != 1 || members.pid[0] != identity.pid)
        throw std::runtime_error("Freeze job does not contain exactly the owned process. Error " +
            std::to_string(error) + ", assigned " + std::to_string(members.assigned) + ", listed " + std::to_string(members.listed) +
            ", first " + std::to_string(members.pid[0]) + ", second " + std::to_string(members.pid[1]) + ", expected " + std::to_string(identity.pid));
    JobFreezeInformation information{};
    information.flags = 1;
    information.freeze = freeze ? TRUE : FALSE;
    return api.set(job, 18, &information, sizeof(information));
}
bool WineNtdll() {
    return GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "wine_get_version") != nullptr;
}
std::vector<DWORD> ThreadIds(DWORD pid) {
    const HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (snapshot == INVALID_HANDLE_VALUE) throw std::runtime_error("Cannot enumerate owned threads.");
    std::vector<DWORD> ids;
    THREADENTRY32 entry{sizeof(entry)};
    for (auto found = Thread32First(snapshot, &entry); found; found = Thread32Next(snapshot, &entry))
        if (entry.th32OwnerProcessID == pid) ids.push_back(entry.th32ThreadID);
    const auto error = GetLastError();
    CloseHandle(snapshot);
    if (error != ERROR_NO_MORE_FILES || ids.empty()) throw std::runtime_error("Cannot read the owned thread inventory.");
    std::sort(ids.begin(), ids.end());
    return ids;
}
NTSTATUS ProcessSuspend::Suspend(HANDLE process, const Identity& identity) {
    if (active_) throw std::runtime_error("The owned process is already suspended.");
    RequireIdentity(process, identity);
    using Change = NTSTATUS(NTAPI*)(HANDLE);
    const auto suspend = reinterpret_cast<Change>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "NtSuspendProcess"));
    if (!suspend) throw std::runtime_error("The process suspend export is absent.");
    threads_ = ThreadIds(identity.pid);
#ifdef BO3_PROCESS_SUSPEND_TEST
    if(inventoryObserver)inventoryObserver(process);
#endif
    const auto status = suspend(process);
    if (status < 0) return status;
    identity_ = identity;
    active_ = true;
    // Wine stops threads asynchronously. Reading a suspended thread's context waits until it has stopped.
    Verify();
    for (const auto id : threads_) {
        const HANDLE thread = OpenThread(THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, id);
        CONTEXT context{};
        context.ContextFlags = CONTEXT_CONTROL;
        const bool stopped = thread && GetProcessIdOfThread(thread) == identity.pid && GetThreadContext(thread, &context);
        if (thread) CloseHandle(thread);
        if (!stopped) throw std::runtime_error("Cannot confirm that an owned thread stopped.");
    }
    Verify();
    return status;
}
void ProcessSuspend::Verify() const {
    if (!active_) throw std::runtime_error("The owned process is not suspended.");
    if (ThreadIds(identity_.pid) != threads_)
        throw std::runtime_error("An owned thread started or ended while the process was suspended.");
}
NTSTATUS ProcessSuspend::Resume(HANDLE process) {
    Verify();
    RequireIdentity(process, identity_);
    using Change = NTSTATUS(NTAPI*)(HANDLE);
    const auto resume = reinterpret_cast<Change>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "NtResumeProcess"));
    if (!resume) throw std::runtime_error("The process resume export is absent.");
    const auto status = resume(process);
    if (status >= 0) active_ = false;
    return status;
}
}
