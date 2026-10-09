#pragma once
#include "ControlAdmission.h"

namespace bo3::late_startup {
using PassiveImage=std::function<std::uintptr_t(HANDLE)>;
// This control holds only the cooperative callback. Every process read is sequential.
void CoordinatePassiveControl(OwnedChild&,MappedGate&,enhanced::MappedHelper&,
    const std::filesystem::path&,const PassiveImage&,ControlReceipt&);
#ifdef BO3_LATE_OWNED_TEST
void SetPassiveOwnedObserver(std::function<void(HANDLE)>);
#endif
}
