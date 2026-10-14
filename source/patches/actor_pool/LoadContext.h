#pragma once
#include "../vm_migration/Admission.h"
#include <cstdint>

namespace bo3::actors {
using RootHeader=bo3::migration::Header;
inline constexpr std::uint32_t VmOnlyVersion=bo3::migration::FormatVersion(500001,18);
inline constexpr std::uint32_t Actor500Version=0xC8000000|(VmOnlyVersion&0x01FFFFFF);
struct ReadCounts {
    std::uint64_t actorBytes,sentientBytes;
    std::uint32_t secondaryRecords,padding;
};
static_assert(sizeof(ReadCounts)==24 && offsetof(ReadCounts,secondaryRecords)==16);
inline constexpr ReadCounts LegacyCounts{64ull*0x2110,104ull*0x3088,64,0};
inline constexpr ReadCounts ExpandedCounts{500ull*0x2110,540ull*0x3088,500,0};
struct LoadBindings {ReadCounts* counts;};
static_assert(sizeof(LoadBindings)==8);
extern "C" __declspec(dllexport) LoadBindings Bo3ActorLoadBindings;

// The root caller supplies its actual file and thread. Native reader wrappers check them before calling game code.
bool BeginLoad(const RootHeader&,void* file,std::uint32_t thread,std::uint32_t bufferBytes);
bool ReaderAllowed(void* file,std::uint32_t thread);
bool EndLoad(void* file,std::uint32_t thread);
// Call from the existing Com_Error prelude as well as the normal root return.
void ClearLoadContext(std::uint32_t thread);
void ClearCurrentLoadContext();
}
