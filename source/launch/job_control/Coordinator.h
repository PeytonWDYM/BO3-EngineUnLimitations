#pragma once
#include "Observation.h"
#include "../late_startup/ControlAdmission.h"
namespace bo3::job_control {
struct Admitted {std::vector<Original> originals;Snapshot frozen;std::uintptr_t guardImage;};
Admitted Coordinate(late_startup::OwnedChild&,job_startup::OwnedJob&,late_startup::MappedGate&,
    enhanced::MappedHelper&,const std::filesystem::path&,Receipt&);
#ifdef BO3_JOB_OWNED_TEST
enum class Failure {None,Thaw,Release};
void SetOwnedFailure(Failure);
void SetOwnedSetup(std::function<std::uintptr_t(HANDLE,std::uintptr_t)>);
#endif
}
