#include "Internal.h"
#include "ContainedSound.h"
#include <intrin.h>

namespace { Shared* shared; }
thread_local LONG AudioDepth = 0;
thread_local Api OuterApi = Api::None;
thread_local std::uint64_t RootCaller = 0;
thread_local CallArguments RootArguments{};
extern "C" Shared* SdkTrace() { return shared; }
bool MapTrace() {
    wchar_t text[32]{};
    const DWORD length = GetEnvironmentVariableW(L"OWNED_SDK_INTERCEPT_TRACE", text, 32);
    if (!length || length >= 32) return false;
    std::uintptr_t handle = 0;
    for (DWORD i = 0; i < length; ++i) {
        if (text[i] < L'0' || text[i] > L'9') return false;
        handle = handle * 10 + static_cast<unsigned>(text[i] - L'0');
    }
    shared = static_cast<Shared*>(MapViewOfFile(reinterpret_cast<HANDLE>(handle), FILE_MAP_WRITE, 0, 0, sizeof(Shared)));
    return shared && shared->magic == kSdkMagic && (shared->mode == Mode::Memory || shared->mode == Mode::PhysicalSilent);
}
void CloseTrace() { if (shared) UnmapViewOfFile(shared); }
bool DescribeAddress(std::uint64_t address, ModuleIdentity& info) {
    HMODULE module = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(static_cast<std::uintptr_t>(address)), &module)) return false;
    const DWORD length = GetModuleFileNameW(module, info.path, 1024);
    if (!length || length >= 1024) return false;
    info.base = reinterpret_cast<std::uintptr_t>(module); info.rva = address - info.base;
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(module);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return false;
    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS*>(reinterpret_cast<const BYTE*>(module) + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return false;
    info.imageSize = nt->OptionalHeader.SizeOfImage; info.timestamp = nt->FileHeader.TimeDateStamp;
    return info.rva < info.imageSize;
}
extern "C" void SdkRecord(Stage stage, Api api, DWORD generation, LONG value, const GUID* clsid, const GUID* iid) {
    const LONG index = InterlockedIncrement(&shared->count) - 1;
    if (index < 0 || index >= kSdkEvents) { InterlockedIncrement(&shared->errors); return; }
    shared->events[index] = {stage, api, static_cast<Phase>(shared->phase), GetCurrentProcessId(), GetCurrentThreadId(),
        generation, value, shared->hooksReady, shared->runtimeReady, AudioDepth, OuterApi,
        RootCaller ? RootCaller : reinterpret_cast<std::uintptr_t>(_ReturnAddress()), clsid ? *clsid : GUID{}, iid ? *iid : GUID{}, {}};
    // Resolve only already-loaded caller metadata after readiness. Do not load a DLL or change its reference count.
    if (stage == Stage::RootEnter && shared->runtimeReady)
        RequireSdk(DescribeAddress(shared->events[index].caller, shared->events[index].callerModule));
    const auto scope=CurrentSoundScope();
    auto& event=shared->events[index];
    event.context=RootArguments.context; event.aggregation=RootArguments.aggregation;
    event.outputProvided=RootArguments.outputProvided; event.outputNull=RootArguments.outputNull;
    event.failedAdmission=RootArguments.failed; event.scopeThread=scope.thread; event.scopeSerial=scope.serial;
    event.containedActive=scope.active; event.admittedCount=scope.count;
}
void RequireSdk(bool condition, HRESULT code) { if (!condition) StopSdk(code, Stage::Error); }
[[noreturn]] void StopSdk(HRESULT code, Stage stage) {
    if (shared->runtimeReady) SdkSnapshot();
    shared->aborted = 1; shared->abortHresult = code;
    SdkRecord(stage, OuterApi, 0, code, nullptr, nullptr);
    TerminateProcess(GetCurrentProcess(), kSdkStop); __fastfail(7);
}
