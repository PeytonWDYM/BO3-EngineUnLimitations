#include "NativeJobFreeze.h"
#include <stdexcept>

namespace process_freeze {
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
}
