#include "RuntimeOwner.h"
#include <intrin.h>

// Termination cannot return through a loader or COM frame. The parent retains the trace mapping.
[[noreturn]] void StopOwned(HRESULT code, Stage stage) {
    auto* trace = StartupState();
    if (trace->runtimeReady) SnapshotMemory();
    trace->aborted = 1;
    trace->abortHresult = code;
    StartupEvent(stage, Api::None, 0, code, nullptr);
    TerminateProcess(GetCurrentProcess(), kControlledStop);
    __fastfail(FAST_FAIL_FATAL_APP_EXIT);
}
