#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace bo3::startup_gate {
inline constexpr DWORD Abi=1;
inline constexpr GUID PayloadGuid{0x5ee454b6,0xa0c1,0x42cd,{0xa9,0x30,0x3d,0xc1,0x5f,0x96,0x8b,0xa2}};
enum class Phase : LONG { Cold=0, Armed=1, Waiting=2, Released=3, Returned=4, Refused=5 };
// The parent duplicates these handles into the suspended child before publishing this payload.
// Production uses a 30000ms gate deadline. Owned builds pin their shorter deadline at compile time.
struct alignas(8) Payload {
    DWORD abi,bytes,processId,primaryThreadId,parentProcessId,deadlineMs;
    std::uint64_t processCreatedFileTime,nonce[2];
    std::uint64_t readyEvent,releaseEvent,parentProcess;
};
// One callback generation. Waiting is published before signaling ready.
// Release is an event signal after coordinator commit/detach. No parent memory write is required.
struct alignas(8) State {
    DWORD abi,bytes;
    volatile LONG phase;
    DWORD refusal,processId,primaryThreadId;
    std::uint64_t processCreatedFileTime,nonce[2],generation,returnSite,wrapperCallerReturn;
    DWORD callbackThreadId,loaderCallout,waitResult,lastError;
    std::uint64_t observationCount;
    std::uint64_t entryAnchorStart,entryAnchorEnd;
    DWORD entryFrameCount,entryAnchorPresent;
};
static_assert(sizeof(Payload)==72 && sizeof(State)==120);
static_assert(offsetof(Payload,readyEvent)==48 && offsetof(State,generation)==48);
static_assert(std::is_standard_layout_v<Payload> && std::is_trivially_copyable_v<Payload>);
static_assert(std::is_standard_layout_v<State> && std::is_trivially_copyable_v<State>);
extern "C" __declspec(dllexport) State Bo3StartupGateState;
}
