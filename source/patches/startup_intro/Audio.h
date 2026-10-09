#pragma once
#include <cstdint>
#include <type_traits>

namespace bo3::startup_intro {
struct AudioBindings {
    bool (*isPlaying)();
    const volatile std::uint32_t* playerCount;
    const volatile std::uintptr_t* players;
    std::uint32_t (*startMovie)(const char*,const char*,std::uint32_t,float,const void*,int);
    void (*updatePlayers)();
    std::uintptr_t introContinuation,updateContinuation;
};
static_assert(std::is_trivially_copyable_v<AudioBindings> && sizeof(AudioBindings)==56);
static_assert(offsetof(AudioBindings,introContinuation)==40 && offsetof(AudioBindings,updateContinuation)==48);
extern "C" __declspec(dllexport) AudioBindings Bo3IntroAudioBindings;
extern "C" __declspec(dllexport) volatile long Bo3IntroAudioStatus;
extern "C" __declspec(dllexport) bool IsCustomIntroPlaying();
extern "C" __declspec(dllexport) std::uint32_t StartCustomIntro(const char*,const char*,std::uint32_t,float,const void*,int);
extern "C" __declspec(dllexport) void UpdateCustomIntroPlayers();
}
