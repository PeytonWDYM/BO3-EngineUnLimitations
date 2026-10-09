#pragma once
#include "../job_startup/Coordinator.h"

namespace bo3::job_control {
struct Phase {const char* name;ULONGLONG tick;};
struct Receipt {
    job_startup::Receipt native;
    bool stockAdmitted=false,originalsVerified=false,bindingsUnchanged=false;
    bool traceFailed=false,traceTruncated=false,exited=false;
    DWORD exitCode{},originalsObserved{};
    std::string observationReason;
    std::vector<Phase> phases;
};
void WriteReceipt(std::ostream&,const Receipt&);
}
