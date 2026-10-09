#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <cstdint>
#include <type_traits>

namespace bo3::startup_probe {
inline constexpr DWORD Abi=1;
struct alignas(8) Observation {
    DWORD abi,bytes;
    volatile LONG sequence;
    DWORD threadId;
    std::uint64_t count,returnSite,wrapperCallerReturn;
    DWORD wrapperCallerReadable,wrapperCallerMatches;
    DWORD readableMask,reserved;
    std::uint64_t pools[4],migrationPointers[5];
    DWORD migrationSizes[3];
    unsigned char caller[44],allocatorPrefix[16];
};
struct alignas(8) Counters {
    DWORD abi,bytes;
    volatile LONG attempts,rejected,dropped,vmReads;
    std::uintptr_t imageBase,originalTrampoline;
    volatile LONG publicationLock;
    DWORD reserved;
};
static_assert(sizeof(Observation)==200 && sizeof(Counters)==48);
static_assert(std::is_standard_layout_v<Observation> && std::is_trivially_copyable_v<Observation>);
static_assert(std::is_standard_layout_v<Counters> && std::is_trivially_copyable_v<Counters>);
extern "C" __declspec(dllexport) Observation Bo3StartupProbeObservation;
extern "C" __declspec(dllexport) Counters Bo3StartupProbeCounters;
void Observe(std::uintptr_t returnSite,std::uintptr_t apiReturnSlot);
}
