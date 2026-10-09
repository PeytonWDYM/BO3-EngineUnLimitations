#include "OwnedJob.h"
#include "../preentry/Identity.h"

namespace bo3::job_startup {
OwnedJob::OwnedJob():job_(CreateJobObjectW(nullptr,nullptr)) {
    Require(job_!=nullptr,"Cannot create the owned startup job.");
    try {
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        Require(SetInformationJobObject(job_,JobObjectExtendedLimitInformation,&limits,sizeof(limits))!=FALSE,
            "Cannot set the owned job lifetime.");
        DWORD flags{};
        Require(GetHandleInformation(job_,&flags)!=FALSE && !(flags&HANDLE_FLAG_INHERIT),
            "The startup job must remain parent-only.");
    }catch(...) {CloseHandle(job_);job_=nullptr;throw;}
}
OwnedJob::~OwnedJob(){if(job_)CloseHandle(job_);}
void OwnedJob::Assign(const late_startup::OwnedChild& child) {
    Require(identity_.pid==0,"The startup job already owns a child.");
    identity_=process_freeze::ReadIdentity(child.process.hProcess);
    Require(identity_.image.size()<=1024,"The owned image path exceeds the bounded receipt contract.");
    Require(identity_.pid==child.process.dwProcessId && identity_.created==child.payload.processCreatedFileTime,
        "The suspended child identity differs.");
    Require(AssignProcessToJobObject(job_,child.process.hProcess)!=FALSE,"Cannot assign the suspended child to its startup job.");
    Verify(child.process.hProcess);
}
void OwnedJob::Verify(HANDLE process) const {
    process_freeze::RequireIdentity(process,identity_);
    BOOL member=FALSE;
    Require(IsProcessInJob(process,job_,&member)!=FALSE && member,"The child is outside its startup job.");
    struct Members {DWORD assigned,listed;ULONG_PTR pids[2];} members{};
    Require(QueryInformationJobObject(job_,JobObjectBasicProcessIdList,&members,sizeof(members),nullptr)!=FALSE
        && members.assigned==1 && members.listed==1 && members.pids[0]==identity_.pid,
        "The startup job must contain exactly its owned child.");
}
NTSTATUS OwnedJob::Freeze(HANDLE process,bool freeze) {
    Verify(process);
#ifdef BO3_JOB_OWNED_TEST
    if(freeze && ownedFreezeStatus_)return ownedFreezeStatus_;
#endif
    return process_freeze::ChangeOwnedJobFreeze(api_,job_,process,identity_,freeze);
}
void OwnedJob::Kill(){Require(TerminateJobObject(job_,97)!=FALSE,"Cannot stop the owned startup job.");}
#ifdef BO3_JOB_OWNED_TEST
void OwnedJob::AddOwnedMember(HANDLE process) {
    Require(AssignProcessToJobObject(job_,process)!=FALSE,"Cannot assign the extra owned membership fixture.");
}
#endif
}
