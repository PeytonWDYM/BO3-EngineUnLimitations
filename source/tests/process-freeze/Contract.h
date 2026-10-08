#pragma once
#include <windows.h>
#include <cstdint>

constexpr size_t kCounters = 11;
struct Shared;
struct WorkerArgument { Shared* shared; size_t index; };
struct Shared {
    DWORD pid;
    unsigned long long created;
    uintptr_t remoteMapping;
    uintptr_t worker;
    HANDLE wake;
    volatile LONG ready;
    volatile LONG controllerReady;
    volatile LONG markerA;
    volatile LONG markerB;
    volatile LONG64 partialObserved;
    volatile LONG64 counters[kCounters];
    volatile LONG started[kCounters];
    DWORD tids[kCounters];
    WorkerArgument args[kCounters];
    LONG hiddenStatus;
    LONG bypassStatus;
    LONG controllerCreateStatus;
    LONG controllerSuspendStatus;
    DWORD controllerAssignError;
    uintptr_t childStateReference;
    DWORD observedExitCode;
    LONG exitObserved;
};
DWORD WINAPI Worker(void* argument);
int RunTarget(HANDLE mapping, HANDLE wake, int mode);
int RunController(HANDLE mapping, DWORD pid, unsigned long long created, int protection, bool stateFirst);
