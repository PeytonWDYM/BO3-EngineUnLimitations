#pragma once
#include "Policy.h"
#include "../job_startup/Coordinator.h"

namespace bo3::bindings_control {
struct Receipt {
    job_startup::Receipt native{};
    Proof proof{};
    ULONGLONG releasedTick{},exitTick{};
    bool stockAdmitted=false,stockVerified=false,deadlineTerminated=false,persistFailed=false;
};
void Coordinate(late_startup::OwnedChild&,job_startup::OwnedJob&,late_startup::MappedGate&,
    enhanced::MappedHelper&,const std::filesystem::path&,Receipt&);
void WriteReceipt(std::ostream&,const Receipt&);
#ifdef BO3_JOB_OWNED_TEST
enum class Failure {None,AfterApply,Thaw,Release};
enum class Phase {Prepared,Published,RolledBack};
void SetOwnedFailure(Failure);
void SetOwnedSetup(std::function<std::uintptr_t(HANDLE,std::uintptr_t)>);
void SetOwnedObserver(std::function<void(HANDLE,const Selected&,Phase)>);
#endif
}
