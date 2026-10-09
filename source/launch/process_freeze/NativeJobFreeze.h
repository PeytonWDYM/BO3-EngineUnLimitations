#pragma once
#include "NativeState.h"

namespace process_freeze {
// PHNT JobObjectFreezeInformation (18). All filter, swap and reserved fields stay zero.
struct JobFreezeInformation {
    ULONG flags;
    BOOLEAN freeze;
    BOOLEAN swap;
    UCHAR reserved[2];
    ULONG wakeHigh;
    ULONG wakeLow;
};
static_assert(sizeof(JobFreezeInformation) == 16);
static_assert(offsetof(JobFreezeInformation, freeze) == 4);
using SetJobInformation = NTSTATUS(NTAPI*)(HANDLE, ULONG, PVOID, ULONG);
struct NativeJobApi {
    SetJobInformation set;
    NativeJobApi();
};
NTSTATUS ChangeOwnedJobFreeze(const NativeJobApi& api, HANDLE job, HANDLE process,
    const Identity& identity, bool freeze);
}
