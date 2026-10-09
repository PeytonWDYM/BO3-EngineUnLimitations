#pragma once
#include "Coordinator.h"
#include "../enhanced/MappedHelper.h"

namespace bo3::late_startup {
void VerifyControlBindings(HANDLE,const enhanced::MappedHelper&);
void CaptureControlBeforeAttach(HANDLE,std::uintptr_t,ControlReceipt&);
void AdmitStockControl(HANDLE,std::uintptr_t,enhanced::MappedHelper&,
    const std::filesystem::path&,ControlReceipt&);
// Production fixes this limit at 120 seconds. Owned fixtures use a shorter bound.
void ObserveControl(OwnedChild&,ControlReceipt&,DWORD limitMs=120000);
}
