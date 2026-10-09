#pragma once
#include "OwnedJob.h"
#include "../late_startup/Coordinator.h"
#include <string_view>

namespace bo3::job_startup {
struct ThreadObservation {DWORD id;std::uintptr_t pc,start;};
struct Receipt {
    vm_startup::Receipt patch{};
    std::uint64_t created{},generation{};
    DWORD processId{},primaryThreadId{},threadsObserved{};
    std::uintptr_t gateBase{},helperBase{},primaryPc{},relay{};
    LONG freezeStatus{},thawStatus{};
    bool jobAssigned=false,freezeAttempted=false,frozen=false,membershipVerified=false;
    bool primaryAdmitted=false,thawAttempted=false,thawed=false;
    bool committed=false,debuggerAbsent=false,released=false,terminated=false,relayFreed=false;
    bool cleanupFailed=false;
    std::string stage="created",refusalReason,unwindReason;
    std::uintptr_t unwindLookupPc{};
    unsigned int runtimeMetadataReads{},runtimeMetadataMask{};
    std::wstring image;
    std::vector<std::uintptr_t> frames;
    std::vector<ThreadObservation> threads;
};
void Coordinate(late_startup::OwnedChild&,OwnedJob&,late_startup::MappedGate&,const late_startup::PreparePlan&,Receipt&,std::size_t expectedEdits=42);
void WriteReceipt(std::ostream&,const Receipt&,std::string_view method="late-crt-job-freeze");
#ifdef BO3_JOB_OWNED_TEST
enum class Failure {None,AfterApply,Thaw,Release};
void SetOwnedFailure(Failure);
void SetOwnedObserver(std::function<void(HANDLE,bool)>);
void SetOwnedPrimarySetup(std::function<void(HANDLE,std::uintptr_t)>);
void SetOwnedBeforeApply(std::function<void(HANDLE)>);
#endif
}
