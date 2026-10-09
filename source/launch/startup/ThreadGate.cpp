#include "ThreadGate.h"
#include "RuntimeOwner.h"

ThreadFactory OriginalThread = OwnedCreateThread;
namespace {
DWORD WINAPI StartOwnedWorker(LPVOID parameter) {
    auto* state = StartupState();
    state->phase = static_cast<LONG>(Phase::Worker);
    state->workerThread = static_cast<LONG>(GetCurrentThreadId());
    StartupEvent(Stage::GateEnter, Api::None, 0, 14, nullptr);
    if (state->scenario == Scenario::StartupReadinessDenied) StopOwned(E_ACCESSDENIED, Stage::ReadinessDenied);
    CheckOwned(InitializeWorkerRuntime() != FALSE);
    return OwnedGenericThread(parameter);
}
}

// The exact owned entry and complete parameter must match. The creator path allocates no gate context.
HANDLE WINAPI InterceptOwnedThread(LPSECURITY_ATTRIBUTES attributes, SIZE_T stack, LPTHREAD_START_ROUTINE entry,
    LPVOID parameter, DWORD flags, LPDWORD id) noexcept {
    const bool matched = entry == OwnedGenericThread
        && parameter == reinterpret_cast<LPVOID>(static_cast<std::uintptr_t>(14));
    auto* state = StartupState();
    if (matched) {
        InterlockedIncrement(&state->gateMatched);
        StartupEvent(Stage::GateMatched, Api::None, 0, 14, nullptr);
    } else {
        InterlockedIncrement(&state->gateUnmatched);
        StartupEvent(Stage::GateUnmatched, Api::None, 0, 0, nullptr);
    }
    return OriginalThread(attributes, stack, matched ? StartOwnedWorker : entry, parameter, flags, id);
}
