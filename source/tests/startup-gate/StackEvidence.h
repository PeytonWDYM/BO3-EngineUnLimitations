#pragma once
#include <Windows.h>
#include <cstdint>

struct StackEvidence {
    DWORD count{},anchorPresent{},anchorAvailable{};
    std::uint64_t anchorStart{},anchorEnd{},frames[64]{};
};
// Owned diagnostic only: bounded native unwind with a single Windows entry anchor.
inline StackEvidence CaptureEntryStack() {
    StackEvidence evidence{};
    const auto anchor=reinterpret_cast<DWORD64>(GetProcAddress(GetModuleHandleW(L"kernel32.dll"),"BaseThreadInitThunk"));
    DWORD64 base{};
    const auto* function=RtlLookupFunctionEntry(anchor,&base,nullptr);
    if(function) {
        evidence.anchorStart=base+function->BeginAddress;
        evidence.anchorEnd=base+function->EndAddress;
        evidence.anchorAvailable=evidence.anchorStart<=anchor && anchor<evidence.anchorEnd;
    }
    void* frames[64]{};
    evidence.count=RtlCaptureStackBackTrace(0,64,frames,nullptr);
    for(DWORD i=0;i<evidence.count;++i) {
        evidence.frames[i]=reinterpret_cast<std::uint64_t>(frames[i]);
        evidence.anchorPresent|=evidence.anchorAvailable && evidence.frames[i]>=evidence.anchorStart && evidence.frames[i]<evidence.anchorEnd;
    }
    return evidence;
}
