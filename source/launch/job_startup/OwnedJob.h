#pragma once
#include "../process_freeze/NativeJobFreeze.h"
#include "../late_startup/OwnedChild.h"

namespace bo3::job_startup {
// Only the parent owns this handle. Last close kills every member, including frozen members.
class OwnedJob {
    process_freeze::NativeJobApi api_;
    HANDLE job_{};
    process_freeze::Identity identity_{};
    // Used only when Wine reports the job freeze as not implemented.
    process_freeze::ProcessSuspend suspend_;
#ifdef BO3_JOB_OWNED_TEST
    NTSTATUS ownedFreezeStatus_{};
#endif
public:
    OwnedJob();
    ~OwnedJob();
    void Assign(const late_startup::OwnedChild&);
    void Verify(HANDLE process) const;
    NTSTATUS Freeze(HANDLE process,bool freeze);
    void Kill();
    bool ProcessSuspended() const {return suspend_.Active();}
#ifdef BO3_JOB_OWNED_TEST
    void AddOwnedMember(HANDLE process);
    void SetOwnedFreezeStatus(NTSTATUS status){ownedFreezeStatus_=status;}
#endif
    const process_freeze::Identity& Identity() const {return identity_;}
    OwnedJob(const OwnedJob&)=delete;
    OwnedJob& operator=(const OwnedJob&)=delete;
};
}
