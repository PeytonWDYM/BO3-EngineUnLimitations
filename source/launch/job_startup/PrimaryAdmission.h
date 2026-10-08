#pragma once
#include "Coordinator.h"
namespace bo3::job_startup {
void AdmitPrimary(const late_startup::OwnedChild&,late_startup::MappedGate&,Receipt&);
void AdmitEditFrames(const Receipt&,std::span<const vm_startup::AddressEdit>);
std::uintptr_t ImageBase(HANDLE process);
}
