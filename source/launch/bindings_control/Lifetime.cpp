#include "Lifetime.h"
#include "../preentry/Identity.h"
#include <iostream>

namespace bo3::bindings_control {
void Retain(late_startup::OwnedChild& child,job_startup::OwnedJob& job,late_startup::PrivateReceipt& report,Receipt& r) {
    // Persistence follows release. An optional I/O failure does not shorten the resumed child's lifetime.
    const auto persist=[&]{try{report.Write(r);}catch(const std::exception& error){r.persistFailed=true;std::cerr<<error.what()<<'\n';}};
    persist();
    const auto deadline=r.releasedTick+120000;
    const auto now=GetTickCount64();const auto remaining=now<deadline?static_cast<DWORD>(deadline-now):0;
    const auto wait=WaitForSingleObject(child.process.hProcess,remaining);
    Require(wait==WAIT_OBJECT_0 || wait==WAIT_TIMEOUT,"Cannot retain the bindings diagnostic child.");
    if(wait==WAIT_TIMEOUT && !child.Exited()) {
        process_freeze::RequireIdentity(child.process.hProcess,job.Identity());job.Kill();r.native.terminated=true;r.deadlineTerminated=true;
        Require(WaitForSingleObject(child.process.hProcess,5000)==WAIT_OBJECT_0,"Cannot drain the owned diagnostic deadline.");
    }
    Require(GetExitCodeProcess(child.process.hProcess,&r.native.patch.exitCode)!=FALSE,"Cannot read the owned diagnostic exit.");
    r.native.patch.exited=true;r.exitTick=GetTickCount64();r.native.stage="exited";persist();
}
}
