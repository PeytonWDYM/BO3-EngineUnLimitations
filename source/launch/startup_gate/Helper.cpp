#include "Admission.h"
#include "Gate.h"
#include "NativeEntry.h"
#include "../startup_probe/Observation.h"
#include "../enhanced/Boot.h"
#include "ProbeProfile.h"
#include <detours.h>
#include <intrin.h>

namespace {
using Startup=void(WINAPI*)(LPSTARTUPINFOW);
constinit Startup original{};
void WINAPI GateStartup(LPSTARTUPINFOW info) {
    const auto site=reinterpret_cast<std::uintptr_t>(_ReturnAddress());
    original(info);
    const DWORD error=GetLastError();
    bo3::startup_gate::Enter(site,reinterpret_cast<std::uintptr_t>(_AddressOfReturnAddress()));
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
extern "C" {
__declspec(dllexport) constinit bo3::enhanced::BootRecord Bo3StartupGateBoot{};
void GateOrdinal() {}
}
BOOL WINAPI DllMain(HINSTANCE module,DWORD reason,LPVOID) {
    if(reason!=DLL_PROCESS_ATTACH) return TRUE;
    if(!DetourRestoreAfterWith()) return FALSE;
    const auto base=reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    if(!AdmitImage(base) || !bo3::startup_gate::AdmitPayload() || !bo3::startup_gate::AdmitEntryAnchor()) return FALSE;
    original=GetStartupInfoW;
    LONG error=DetourTransactionBegin();
    if(error!=NO_ERROR) return FALSE;
    error=DetourUpdateThread(GetCurrentThread());
    if(error==NO_ERROR) error=DetourAttach(reinterpret_cast<PVOID*>(&original),GateStartup);
    if(error!=NO_ERROR) { DetourTransactionAbort(); return FALSE; }
    if(DetourTransactionCommit()!=NO_ERROR) return FALSE;
    auto& counters=bo3::startup_probe::Bo3StartupProbeCounters;
    counters.abi=1; counters.bytes=sizeof(counters); counters.imageBase=base;
    counters.originalTrampoline=reinterpret_cast<std::uintptr_t>(original);
    auto& record=bo3::startup_probe::Bo3StartupProbeObservation;
    record.abi=1; record.bytes=sizeof(record);
    auto& state=bo3::startup_gate::Bo3StartupGateState;
    const auto& payload=bo3::startup_gate::configuration;
    state.abi=1; state.bytes=sizeof(state); state.processId=payload.processId;
    state.primaryThreadId=payload.primaryThreadId; state.processCreatedFileTime=payload.processCreatedFileTime;
    state.nonce[0]=payload.nonce[0]; state.nonce[1]=payload.nonce[1];
    InterlockedExchange(&state.phase,static_cast<LONG>(bo3::startup_gate::Phase::Armed));
    Bo3StartupGateBoot={1,sizeof(Bo3StartupGateBoot),reinterpret_cast<std::uintptr_t>(module),1,0};
    return TRUE;
}
