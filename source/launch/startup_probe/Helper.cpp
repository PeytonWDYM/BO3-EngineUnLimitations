#include "Observation.h"
#include "ProbeProfile.h"
#include "../enhanced/Boot.h"
#include <detours.h>
#include <intrin.h>

namespace {
using Startup=void(WINAPI*)(LPSTARTUPINFOW);
constinit Startup original{};
void WINAPI ProbeStartup(LPSTARTUPINFOW info) {
    const auto site=reinterpret_cast<std::uintptr_t>(_ReturnAddress());
    original(info);
    const DWORD error=GetLastError();
    if(site==bo3::startup_probe::Bo3StartupProbeCounters.imageBase+kReturnRva)
        bo3::startup_probe::Observe(site,reinterpret_cast<std::uintptr_t>(_AddressOfReturnAddress()));
    SetLastError(error);
}
bool AdmitImage(std::uintptr_t base) {
    const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if(dos->e_magic!=IMAGE_DOS_SIGNATURE || dos->e_lfanew<static_cast<LONG>(sizeof(IMAGE_DOS_HEADER))
        || static_cast<DWORD>(dos->e_lfanew)>kImageSize-sizeof(IMAGE_NT_HEADERS64)) return false;
    const auto* pe=reinterpret_cast<const IMAGE_NT_HEADERS64*>(base+dos->e_lfanew);
    return pe->Signature==IMAGE_NT_SIGNATURE && pe->FileHeader.Machine==IMAGE_FILE_MACHINE_AMD64
        && pe->FileHeader.TimeDateStamp==kTimestamp && pe->OptionalHeader.Magic==IMAGE_NT_OPTIONAL_HDR64_MAGIC
        && pe->OptionalHeader.SizeOfImage==kImageSize;
}
}
namespace bo3::enhanced {
extern "C" { __declspec(dllexport) constinit BootRecord Bo3EnhancedBoot{}; }
}
extern "C" void ProbeOrdinal() {}
// No handshake, runtime construction or VM reads during loader initialization.
BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID) {
    if(reason!=DLL_PROCESS_ATTACH) return TRUE;
    if(!DetourRestoreAfterWith()) return FALSE;
    const auto base=reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    if(!AdmitImage(base)) return FALSE;
    original=GetStartupInfoW;
    LONG error=DetourTransactionBegin();
    if(error!=NO_ERROR) return FALSE;
    error=DetourUpdateThread(GetCurrentThread());
    if(error==NO_ERROR) error=DetourAttach(reinterpret_cast<PVOID*>(&original),ProbeStartup);
    if(error!=NO_ERROR) { DetourTransactionAbort(); return FALSE; }
    if(DetourTransactionCommit()!=NO_ERROR) return FALSE;
    auto& counters=bo3::startup_probe::Bo3StartupProbeCounters;
    counters.abi=bo3::startup_probe::Abi;
    counters.bytes=sizeof(counters);
    counters.imageBase=base;
    counters.originalTrampoline=reinterpret_cast<std::uintptr_t>(original);
    auto& record=bo3::startup_probe::Bo3StartupProbeObservation;
    record.abi=bo3::startup_probe::Abi;
    record.bytes=sizeof(record);
    bo3::enhanced::Bo3EnhancedBoot={bo3::enhanced::BootAbi,sizeof(bo3::enhanced::BootRecord),
        reinterpret_cast<std::uintptr_t>(module),1,0};
    return TRUE;
}
