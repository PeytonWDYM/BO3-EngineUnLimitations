#include "NativeEntry.h"
#include "GateProfile.h"
namespace bo3::startup_gate {
namespace {
struct Range { std::uint64_t start,end; };
constinit Range entry{};
}
// Resolve one Windows thread-entry export and its registered native unwind range.
bool AdmitEntryAnchor() {
    const auto module=GetModuleHandleW(L"kernel32.dll");
    const auto anchor=reinterpret_cast<DWORD64>(GetProcAddress(module,kEntryAnchorName));
    if(!anchor) return false;
    DWORD64 base{};
    const auto* function=RtlLookupFunctionEntry(anchor,&base,nullptr);
    if(!function || base!=reinterpret_cast<DWORD64>(module) || function->BeginAddress>=function->EndAddress) return false;
    const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(module);
    const auto* pe=reinterpret_cast<const IMAGE_NT_HEADERS64*>(reinterpret_cast<DWORD64>(module)+dos->e_lfanew);
    if(function->EndAddress>pe->OptionalHeader.SizeOfImage) return false;
    entry={base+function->BeginAddress,base+function->EndAddress};
    return entry.start<=anchor && anchor<entry.end;
}
// This is a bounded native unwind, not a scan of guessed stack words.
bool HasNativeEntry(State& state) {
    void* frames[64]{};
    const DWORD count=RtlCaptureStackBackTrace(0,64,frames,nullptr);
    if(!count) return false;
    for(DWORD i=0;i<count;++i) {
        const auto pc=reinterpret_cast<DWORD64>(frames[i]);
        if(pc>=entry.start && pc<entry.end) {
            state.entryAnchorStart=entry.start; state.entryAnchorEnd=entry.end;
            state.entryFrameCount=count; state.entryAnchorPresent=1;
            return true;
        }
    }
    return false;
}
}
