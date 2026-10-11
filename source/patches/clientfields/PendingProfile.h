#pragma once
#include "../../launch/enhanced/GameProfile.h"

namespace bo3::clientfields {
inline constexpr std::uint32_t kPendingCapacity=8192;
inline constexpr std::uint32_t kPendingCountOffset=kPendingCapacity*32*2;
inline constexpr std::uint32_t kPendingStorageBytes=kPendingCountOffset+8;
inline constexpr std::uint32_t kStockPendingPoolRva=0x49925A0;
inline constexpr std::uint32_t kPendingPointerRva=0x4992590;
enum class PendingOperand {Pool,Bytes,Counts,Capacity,Shift};
struct PendingInstruction {
    std::uint32_t rva;
    std::array<unsigned char,8> bytes;
    std::uint32_t size,offset,width;
    PendingOperand operand;
};
// Caller owns a file-verified, frozen child. Refuses callbacks or VM backing already in use.
std::uintptr_t AdmitPendingCallbacks(HANDLE,std::uintptr_t image);
// Complete instruction and pointer edits; no target writes or allocations.
std::vector<vm_startup::AddressEdit> BuildPendingPlan(std::uintptr_t image,std::uintptr_t pool,std::uintptr_t published);
}
