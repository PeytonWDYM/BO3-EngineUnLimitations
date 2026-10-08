#pragma once
#include <Windows.h>
#include <cstdint>
enum class Scenario : DWORD { Entry, Tls, Worker, Concurrent, Mismatch, Existing, NoCall, Fault, ClientFirst, Foreign,
    SingleStep, TraceGate, Repeated, ExistingHash, HelperNoReady, HelperAbsent, HelperDirty,
    HookMismatch, ReadyDenied };
struct Shared {
    Scenario scenario;
    DWORD expectedTotal;
    volatile LONG calls;
    DWORD observedTotal;
    DWORD initTotal;
    DWORD beforeEntry;
    DWORD workerId;
    DWORD returnedId;
    DWORD resumeCount;
    LONG priority;
    DWORD clientTotal;
    DWORD visited;
    std::uint64_t allocationBytes;
    std::uint64_t idReceipt;
    DWORD errors;
    DWORD done;
    DWORD readyCalls;
    DWORD readyBeforeCount;
    DWORD debuggerPresent;
    DWORD forwarded;
    DWORD wantHelper;
    std::uintptr_t helperBase;
    DWORD helperLoaded;
    DWORD helperAtImport;
    DWORD helperAtTls;
    DWORD configZeroAtLoad;
    volatile LONG hookReads;
    volatile LONG hookWrites;
    volatile LONG originalReads;
    volatile LONG originalWrites;
    volatile LONG originalInserts;
};
