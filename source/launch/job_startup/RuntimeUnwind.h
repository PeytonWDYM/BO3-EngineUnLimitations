#pragma once
#include "Coordinator.h"
namespace bo3::job_startup {
// Only the two verified game CRT records may replace encrypted disk unwind data.
PVOID RuntimeFunction(HANDLE,std::uintptr_t,const unsigned char*,DWORD64);
unsigned int RuntimeMetadataReadMask(std::uintptr_t,DWORD64,DWORD);
#ifdef BO3_JOB_OWNED_TEST
void SetOwnedRuntimeGuardAbsent(bool);
#endif
}
