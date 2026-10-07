#include "Internal.h"

namespace {
LPTHREAD_START_ROUTINE ownedEntry;
DWORD WINAPI StartOwned(LPVOID parameter) {
    auto* trace = SdkTrace(); trace->phase = static_cast<LONG>(Phase::Worker);
    trace->workerTid = static_cast<LONG>(GetCurrentThreadId());
    SdkRecord(Stage::Gate, Api::Thread, 0, 14, nullptr, nullptr);
    RequireSdk(InitializeSdk(Phase::Worker) != FALSE);
    return ownedEntry(parameter);
}
}
// Resolve the fixed owned export from its already-loaded module. Never load or wait in this hook.
HANDLE WINAPI InterceptThread(LPSECURITY_ATTRIBUTES attributes, SIZE_T stack, LPTHREAD_START_ROUTINE entry,
    LPVOID parameter, DWORD flags, LPDWORD id) noexcept {
    const auto module = GetModuleHandleW(L"SdkInterceptConsumer.dll");
    const auto candidate = module ? reinterpret_cast<LPTHREAD_START_ROUTINE>(GetProcAddress(module, "SdkOwnedWorker")) : nullptr;
    const bool matched = candidate && entry == candidate
        && parameter == reinterpret_cast<LPVOID>(static_cast<std::uintptr_t>(14));
    if (matched) {
        ownedEntry = candidate;
        InterlockedIncrement(&SdkTrace()->matched);
        SdkRecord(Stage::Match, Api::Thread, 0, 14, nullptr, nullptr);
    } else {
        InterlockedIncrement(&SdkTrace()->unmatched);
        SdkRecord(Stage::Unmatched, Api::Thread, 0, 0, nullptr, nullptr);
    }
    return OriginalThread(attributes, stack, matched ? StartOwned : entry, parameter, flags, id);
}
