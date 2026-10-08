#pragma once
#include "DebugGate.h"
#include "../vm_pool/NativeStateBridge.h"
#include <array>

namespace vm_startup {
struct ImageRange { std::uintptr_t base; std::uint32_t size; };
struct NativeEntry { std::uint32_t rva; std::array<unsigned char,5> original; };
// All offsets come from the admitted exact helper's PE exports, not live lookup.
struct HelperOffsets {
    std::uint32_t stateBindings,errorBindings,readState,writeState,insertState,readOrDrop,writeOrDrop,errorPrelude;
    std::uint32_t originalReader,originalWriter,originalInsert,originalError;
};
struct NativePlanInput {
    ImageRange image,helper;
    std::array<NativeEntry,4> entries; // reader, writer, insert, Com_Error
    HelperOffsets exports;
    std::uintptr_t relay;
    std::uint32_t total,clientRoots,stockClientRoots;
    bo3::vm::NativeModePolicy modePolicy;
    std::vector<Edit> counts; // Caller supplies the complete admitted count manifest.
};
// Pure preparation: no allocation or process write. PausedPatch preflights the result.
std::vector<AddressEdit> BuildNativePlan(const NativePlanInput&);
}
