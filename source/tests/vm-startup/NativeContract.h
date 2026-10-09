#pragma once
#include "Contract.h"
#include "../../patches/vm_startup/NativePlan.h"

enum class NativeScenario:DWORD { Roundtrip,DecodeError,StateError,LaterError,Rollback,EntryMismatch,FarRelay,BootInvalid,BootNotReady };
struct NativeShared {
    Shared loader;
    NativeScenario scenario;
    std::uintptr_t imageBase,relay;
    DWORD imageSize;
    DWORD passed,serverReads,serverWrites,clientReads,clientWrites,inserts,errorCalls,laterCalls,nonLocalExits;
    DWORD stateErrorCode,ready,readyBeforeCalls,rollbackOriginal,relayFreed,insertUnwind,errorUnwind;
    DWORD leafUnwinds;
    std::uint64_t encodedBytes,encodedHash;
};
inline constexpr std::array<vm_startup::NativeEntry,4> NativeEntries{{
    {0x12d52f0,{0x48,0x89,0x5c,0x24,0x10}}, {0x12d5f20,{0x48,0x89,0x5c,0x24,0x08}},
    {0x12d9420,{0x40,0x53,0x49,0x8b,0xd8}}, {0x20ec0b0,{0x4c,0x89,0x4c,0x24,0x20}}}};
inline constexpr std::uint32_t NativeImageSize=0xa1b1000;
