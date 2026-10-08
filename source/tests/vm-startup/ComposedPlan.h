#pragma once
#include "Contract.h"
#include "../../patches/vm_startup/DebugGate.h"
void SetComposedPlan(Shared*, HMODULE target, HMODULE helper, DWORD gateRva);
std::vector<vm_startup::AddressEdit> PrepareComposed(HANDLE, const vm_startup::Receipt&);
bool CompositionOriginal(HANDLE, std::uintptr_t imageBase);
