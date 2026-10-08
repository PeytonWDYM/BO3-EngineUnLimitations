#include "Contract.h"
#include "../../launch/process_freeze/NativeState.h"
#include "../../launch/process_freeze/NativeJobFreeze.h"
#include <stdexcept>

DWORD WINAPI Worker(void* argument) {
    auto& arg = *static_cast<WorkerArgument*>(argument);
    auto& shared = *arg.shared;
    shared.tids[arg.index] = GetCurrentThreadId();
    InterlockedExchange(&shared.started[arg.index], 1);
    if (arg.index == 10) { InterlockedIncrement64(&shared.counters[10]); return 0; }
    for (;;) {
        if (arg.index == 5) WaitForSingleObject(shared.wake, 50);
        if (InterlockedCompareExchange(&shared.markerA, 0, 0) == 1 &&
            InterlockedCompareExchange(&shared.markerB, 0, 0) == 0)
            InterlockedIncrement64(&shared.partialObserved);
        InterlockedIncrement64(&shared.counters[arg.index]);
        // Worker zero is a tight user-mode loop. It never waits or yields.
        if (arg.index != 0) Sleep(1);
    }
}
int RunTarget(HANDLE mapping, HANDLE wake, int mode) {
    auto* shared = static_cast<Shared*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(Shared)));
    if (!shared) throw std::runtime_error("Target mapping failed.");
    process_freeze::NativeApi api;
    const auto identity = process_freeze::ReadIdentity(GetCurrentProcess());
    shared->pid = identity.pid; shared->created = identity.created;
    shared->remoteMapping = reinterpret_cast<uintptr_t>(shared);
    shared->worker = reinterpret_cast<uintptr_t>(&Worker); shared->wake = wake;
    for (size_t i = 0; i < kCounters; ++i) shared->args[i] = {shared, i};
    for (size_t i = 0; mode != 2 && i < 4; ++i) {
        const auto thread = CreateThread(nullptr, 0, Worker, &shared->args[i], 0, nullptr);
        if (!thread) throw std::runtime_error("Ordinary worker creation failed.");
        CloseHandle(thread);
    }
    if (mode != 2) {
    HANDLE hidden = nullptr;
    shared->hiddenStatus = api.thread(&hidden, THREAD_ALL_ACCESS, nullptr, GetCurrentProcess(),
        reinterpret_cast<void*>(&Worker), &shared->args[4], 4, 0, 0, 0, nullptr);
    if (shared->hiddenStatus < 0) throw std::runtime_error("Hidden worker creation failed.");
    CloseHandle(hidden);
    const auto waiting = CreateThread(nullptr, 0, Worker, &shared->args[5], 0, nullptr);
    if (!waiting) throw std::runtime_error("Waiting worker creation failed.");
    CloseHandle(waiting);
    if (mode == 1) {
        HANDLE thread = nullptr;
        shared->bypassStatus = api.thread(&thread, THREAD_ALL_ACCESS, nullptr, GetCurrentProcess(),
            reinterpret_cast<void*>(&Worker), &shared->args[7], 0x40, 0, 0, 0, nullptr);
        if (shared->bypassStatus < 0) throw std::runtime_error("Bypass worker creation failed.");
        CloseHandle(thread);
    }
    }
    InterlockedExchange(&shared->ready, 1);
    const auto deadline = GetTickCount64() + 30000;
    while (GetTickCount64() < deadline) {
        if (shared->markerA == 1 && shared->markerB == 0) InterlockedIncrement64(&shared->partialObserved);
        InterlockedIncrement64(&shared->counters[6]);
        if (mode != 2) {
            const auto transient = CreateThread(nullptr, 0, Worker, &shared->args[10], 0, nullptr);
            if (!transient) return 21;
            CloseHandle(transient);
        }
        Sleep(4);
    }
    return 22;
}

int RunController(HANDLE mapping, DWORD pid, unsigned long long created, int protection, bool stateFirst) {
    auto* shared = static_cast<Shared*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(Shared)));
    if (!shared) throw std::runtime_error("Controller mapping failed.");
    const auto process = OpenProcess(PROCESS_ALL_ACCESS, FALSE, pid);
    if (!process) throw std::runtime_error("Controller owned process open failed.");
    auto identity = process_freeze::ReadIdentity(process);
    if (identity.pid != pid || identity.created != created || shared->pid != pid || shared->created != created)
        throw std::runtime_error("Controller target identity differs.");
    process_freeze::NativeApi api;
    const bool safe = protection != 0;
    const bool pureJob = protection == 2;
    HANDLE state = nullptr, job = nullptr;
    auto createState = [&] {
        shared->controllerCreateStatus = api.create(&state, 1, nullptr, process, 0);
        if (shared->controllerCreateStatus < 0) throw std::runtime_error("Controller state creation failed.");
    };
    if (!pureJob && stateFirst) createState();
    if (safe) {
        job = CreateJobObjectW(nullptr, nullptr);
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if (!job || !SetInformationJobObject(job, JobObjectExtendedLimitInformation, &limits, sizeof(limits)))
            throw std::runtime_error("Controller death job creation failed.");
        if (!AssignProcessToJobObject(job, process)) {
            shared->controllerAssignError = GetLastError();
            throw std::runtime_error("Controller death job admission failed.");
        }
        DWORD flags = HANDLE_FLAG_INHERIT;
        if (!GetHandleInformation(job, &flags) || (flags & HANDLE_FLAG_INHERIT))
            throw std::runtime_error("Controller death job can inherit.");
    }
    if (!pureJob && !stateFirst) createState();
    if (safe && !pureJob) {
        HANDLE childReference = nullptr;
        if (!DuplicateHandle(GetCurrentProcess(), state, process, &childReference, 0, FALSE, DUPLICATE_SAME_ACCESS))
            throw std::runtime_error("Controller child state duplicate failed.");
        shared->childStateReference = reinterpret_cast<uintptr_t>(childReference);
    }
    if (pureJob) {
        process_freeze::NativeJobApi jobApi;
        shared->controllerSuspendStatus = process_freeze::ChangeOwnedJobFreeze(jobApi, job, process, identity, true);
    } else shared->controllerSuspendStatus = api.change(state, process, 0, nullptr, 0, 0);
    if (shared->controllerSuspendStatus < 0) throw std::runtime_error("Controller freeze failed.");
    Sleep(100);
    InterlockedExchange(&shared->markerA, 1);
    InterlockedExchange(&shared->controllerReady, 1);
    // Abrupt process termination closes the controller's handles without C++ cleanup.
    TerminateProcess(GetCurrentProcess(), 73);
    return 74;
}
