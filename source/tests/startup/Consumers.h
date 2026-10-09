#pragma once
#include "Contract.h"
#include "../activation/Providers.h"

[[noreturn]] void StopOwned(HRESULT code, Stage stage);
activation_test::State& MemoryState();
void CheckOwned(bool condition, HRESULT failure = E_UNEXPECTED);
DWORD ConsumeFamilies();
DWORD ConsumeRetained();
void ReleaseFamilies();
void SnapshotMemory();
