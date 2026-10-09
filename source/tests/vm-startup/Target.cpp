#include "Contract.h"
#include <cstdlib>
#include <cstring>
#include <intrin.h>
#include <initializer_list>

extern "C" {
__declspec(dllexport) __declspec(align(4096)) unsigned char GateCode[4096]{};
__declspec(dllexport) std::uintptr_t PoolPointer = 0;
__declspec(dllexport) std::uintptr_t HashPointer = 0;
#ifdef VM_STARTUP_COMPOSED
__declspec(dllimport) void OwnedConsumerAnchor();
#endif
__declspec(dllexport) void OwnedClientReader(std::uint32_t instance, void* file) {
    auto* trace = static_cast<Shared*>(file);
    if (instance != 1) ++trace->errors;
    InterlockedIncrement(&trace->originalReads);
}
__declspec(dllexport) void OwnedClientWriter(std::uint32_t instance, void* file) {
    auto* trace = static_cast<Shared*>(file);
    if (instance != 1) ++trace->errors;
    InterlockedIncrement(&trace->originalWrites);
}
__declspec(dllexport) void OwnedInsert(std::uint32_t instance, std::uint32_t id, std::uint64_t key, std::uint32_t parent);
}
namespace {
Shared* shared;
bool entry;
void Setup() {
    wchar_t text[64]{};
    if (!GetEnvironmentVariableW(L"OWNED_VM_STARTUP_MAPPING", text, 64)) ExitProcess(90);
    const auto mapping = reinterpret_cast<HANDLE>(_wcstoui64(text, nullptr, 10));
    shared = static_cast<Shared*>(MapViewOfFile(mapping, FILE_MAP_WRITE, 0, 0, sizeof(Shared)));
    if (!shared) ExitProcess(91);
    shared->helperAtTls = shared->helperLoaded;
    unsigned char code[]{0xb8,0xd0,0xfb,0x01,0x00,0xc3};
    for (size_t index = 0; index < sizeof(code); ++index) {
        GateCode[index] = code[index] ^ 0x55;
        GateCode[64 + index] = code[index] ^ 0x55;
    }
    // Decode after thread creation debug events. No software breakpoint bytes survive this write.
    for (size_t index = 0; index < sizeof(code); ++index) { GateCode[index] ^= 0x55; GateCode[64 + index] ^= 0x55; }
    for (const auto offset : {128,192}) {
        std::memcpy(GateCode + offset, code, sizeof(code));
        std::memset(GateCode + offset + sizeof(code), 0x90, 14-sizeof(code));
    }
    if (shared->scenario == Scenario::Mismatch) GateCode[64] = 0xb9;
    if (shared->scenario == Scenario::HookMismatch) GateCode[128] = 0xb9;
    if (shared->scenario == Scenario::Existing) PoolPointer = 1;
    if (shared->scenario == Scenario::ExistingHash) HashPointer = 1;
    if (shared->scenario == Scenario::Repeated) {
        PoolPointer = 1;
        std::memcpy(GateCode + 1, &shared->expectedTotal, sizeof(DWORD));
        std::memcpy(GateCode + 65, &shared->expectedTotal, sizeof(DWORD));
    }
    // After popfq, the jump creates a trace-flag exception exactly at the old gate.
    const unsigned char trace[]{0x9c,0x81,0x0c,0x24,0x00,0x01,0x00,0x00,0x9d,0xe9,0xf2,0xfe,0xff,0xff};
    std::memcpy(GateCode + 256, trace, sizeof(trace));
    DWORD previous = 0;
    if (!VirtualProtect(GateCode, sizeof(GateCode), PAGE_EXECUTE_READ, &previous)
        || !FlushInstructionCache(GetCurrentProcess(), GateCode, sizeof(GateCode))) ExitProcess(92);
}
DWORD Counts(bool client = false) {
    shared->debuggerPresent = IsDebuggerPresent();
    if (!entry) shared->beforeEntry = 1;
    const auto first = reinterpret_cast<DWORD(*)()>(&GateCode[0])();
    const auto second = reinterpret_cast<DWORD(*)()>(GateCode + 64)();
    if (shared->wantHelper && (reinterpret_cast<DWORD(*)()>(GateCode + 128)() != first
        || reinterpret_cast<DWORD(*)()>(GateCode + 192)() != first)) ++shared->errors;
    if (first != second || first != shared->expectedTotal) InterlockedIncrement(reinterpret_cast<volatile LONG*>(&shared->errors));
    InterlockedIncrement(&shared->calls);
    if (client) { shared->clientTotal = 65000; return 65000; }
    InterlockedExchange(reinterpret_cast<volatile LONG*>(&shared->observedTotal), static_cast<LONG>(first));
    InterlockedExchange(reinterpret_cast<volatile LONG*>(&shared->initTotal), static_cast<LONG>(second));
    return first;
}
int HandleStep(EXCEPTION_POINTERS* exception) {
    if (exception->ExceptionRecord->ExceptionCode != EXCEPTION_SINGLE_STEP) return EXCEPTION_CONTINUE_SEARCH;
    exception->ContextRecord->EFlags &= ~0x100u;
    ++shared->forwarded;
    return EXCEPTION_EXECUTE_HANDLER;
}
void SingleStep() {
    __try {
        if (shared->scenario == Scenario::TraceGate) reinterpret_cast<void(*)()>(GateCode + 256)();
        else RaiseException(EXCEPTION_SINGLE_STEP, 0, 0, nullptr);
    } __except(HandleStep(GetExceptionInformation())) {}
}
void Allocate() {
    const auto total = shared->observedTotal;
    shared->allocationBytes = static_cast<std::uint64_t>(total) * 64;
    auto* pool = static_cast<unsigned char*>(VirtualAlloc(nullptr, static_cast<SIZE_T>(shared->allocationBytes),
        MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
    if (!pool) ExitProcess(93);
    PoolPointer = reinterpret_cast<std::uintptr_t>(pool);
    for (DWORD id = 0; id < total; ++id) *reinterpret_cast<DWORD*>(pool + static_cast<size_t>(id) * 64) = id + 1 < total ? id + 1 : 0;
    std::uint64_t receipt = 14695981039346656037ull;
    for (DWORD id = 1; id; id = *reinterpret_cast<DWORD*>(pool + static_cast<size_t>(id) * 64)) {
        receipt = (receipt ^ id) * 1099511628211ull;
        ++shared->visited;
    }
    shared->idReceipt = receipt;
    if (shared->visited != total - 1) ++shared->errors;
    VirtualFree(pool, 0, MEM_RELEASE);
    PoolPointer = 0;
}
DWORD WINAPI Worker(LPVOID) {
    InterlockedExchange(reinterpret_cast<volatile LONG*>(&shared->workerId), static_cast<LONG>(GetCurrentThreadId()));
    Counts();
    return 0;
}
void NTAPI Tls(PVOID, DWORD reason, PVOID) {
    if (reason != DLL_PROCESS_ATTACH) return;
    Setup();
    if (shared->scenario == Scenario::Tls) Counts();
}
}
#pragma const_seg(".CRT$XLB")
extern "C" const PIMAGE_TLS_CALLBACK OwnedTls = Tls;
#pragma const_seg()
#pragma comment(linker, "/INCLUDE:_tls_used")
#pragma comment(linker, "/INCLUDE:OwnedTls")
int main() {
#ifdef VM_STARTUP_COMPOSED
    OwnedConsumerAnchor();
#endif
    entry = true;
    if (shared->scenario == Scenario::NoCall) return 0;
    if (shared->scenario == Scenario::Fault) RaiseException(0xe0427654, 0, 0, nullptr);
    if (shared->scenario == Scenario::Foreign) {
        CONTEXT context{}; context.ContextFlags = CONTEXT_DEBUG_REGISTERS;
        context.Dr0 = reinterpret_cast<DWORD64>(GateCode); context.Dr1 = 0x1234; context.Dr7 = 1;
        if (!SetThreadContext(GetCurrentThread(), &context)) return 95;
    }
    if (shared->scenario == Scenario::Worker || shared->scenario == Scenario::Concurrent) {
        HANDLE threads[8]{};
        const DWORD count = shared->scenario == Scenario::Worker ? 1 : 8;
        for (DWORD index = 0; index < count; ++index) {
            DWORD id = 0;
            threads[index] = CreateThread(nullptr, 131072, Worker, nullptr, CREATE_SUSPENDED, &id);
            if (!threads[index]) return 94;
            shared->returnedId = id;
            if (!SetThreadPriority(threads[index], THREAD_PRIORITY_BELOW_NORMAL)) return 94;
            shared->priority = GetThreadPriority(threads[index]);
        }
        for (DWORD index = 0; index < count; ++index) shared->resumeCount = ResumeThread(threads[index]);
        if (WaitForMultipleObjects(count, threads, TRUE, 20000) != WAIT_OBJECT_0) return 94;
        for (DWORD index = 0; index < count; ++index) CloseHandle(threads[index]);
    } else if (shared->scenario != Scenario::Tls) {
        if (shared->scenario == Scenario::ClientFirst) Counts(true);
        Counts();
    }
    if (shared->scenario == Scenario::SingleStep || shared->scenario == Scenario::TraceGate) SingleStep();
    Allocate();
    shared->done = 1;
    return shared->errors ? 96 : 0;
}
extern "C" void OwnedInsert(std::uint32_t instance, std::uint32_t id, std::uint64_t key, std::uint32_t parent) {
    if (instance != 1 || id != 7 || key != 0x1122334455667788ull || parent != 9) ++shared->errors;
    InterlockedIncrement(&shared->originalInserts);
}
