#pragma once
#include "../../launch/enhanced/GameProfile.h"
#include <stdexcept>

namespace bo3::clientfields {
inline constexpr std::uint32_t kCounterCapacity=8192;
inline constexpr std::uint32_t kCounterStorageBytes=kCounterCapacity*24;
inline constexpr std::uint32_t kStockCounterPoolRva=0x41C9C30;
enum class CounterOperand {Pool,End,LastField,LastState,LastCount,Bytes,Capacity};
struct CounterInstruction {
    std::uint32_t rva;
    std::array<unsigned char,10> bytes;
    std::uint32_t size,offset,width;
    CounterOperand operand;
};
constexpr std::uint32_t CounterOffset(CounterOperand operand) {
    switch(operand) {
    case CounterOperand::Pool:return 0;
    case CounterOperand::End:return kCounterStorageBytes;
    case CounterOperand::LastField:return kCounterStorageBytes-24;
    case CounterOperand::LastState:return kCounterStorageBytes-16;
    case CounterOperand::LastCount:return kCounterStorageBytes-8;
    default:throw std::invalid_argument("A counter storage reference is required.");
    }
}
// Caller owns a file-verified, frozen child. Existing VM backing or counter state refuses activation.
void AdmitCounters(HANDLE,std::uintptr_t image);
// Complete native counter edits. No target writes or allocations.
std::vector<vm_startup::AddressEdit> BuildCounterPlan(std::uintptr_t image,std::uintptr_t pool);
}
