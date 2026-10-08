#pragma once
#include "StartupControl.h"

namespace bo3::startup_control {
void RecordObservation(HANDLE process,std::uintptr_t image,std::uintptr_t helper,const Profile& profile,Timeline& trace);
// A signaled handle is authoritative even when no debug exit event is available.
bool RecordSignaledExit(HANDLE process,Outcome& outcome,Timeline& trace);
Outcome ObservePassive(const PROCESS_INFORMATION& child,const Profile& profile,Timeline& trace);
}
