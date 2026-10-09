#pragma once
#include "Internal.h"

struct ScopeFacts { DWORD thread; LONG serial, active, count; };
ScopeFacts CurrentSoundScope();
void InitializeSoundIdentity();
bool ForwardContainedCom(REFCLSID, LPUNKNOWN, DWORD, REFIID, void**, HRESULT& result);
// Authority exists only while the physical provider executes its saved original trampoline.
class OriginalSoundScope {
public:
    OriginalSoundScope();
    ~OriginalSoundScope();
    OriginalSoundScope(const OriginalSoundScope&)=delete;
    OriginalSoundScope& operator=(const OriginalSoundScope&)=delete;
};
