#pragma once
#include "../job_startup/Coordinator.h"
#include "../preentry/Identity.h"

namespace bo3::early_startup {
// Keep the owned child alive through its session, then publish its actual final state.
template<class WriteReceipt>
DWORD RecordGameExit(HANDLE process,job_startup::Receipt& receipt,WriteReceipt&& write) {
    Require(WaitForSingleObject(process,INFINITE)==WAIT_OBJECT_0,"Cannot retain the owned game lifetime.");
    DWORD exit{};Require(GetExitCodeProcess(process,&exit),"Cannot read the owned game exit code.");
    receipt.patch.exited=true;receipt.patch.exitCode=exit;receipt.stage="exited";
    write();
    return exit;
}
}
