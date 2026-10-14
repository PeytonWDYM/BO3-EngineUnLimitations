#pragma once
#include "LoadContext.h"
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace bo3::actors {
using Reader = void (*)(void*);
using NativeRead = void (*)(void*,std::uint32_t,void*);
using WholeReader = bool (*)(void*);
struct NativeBindings {
    Reader actor,sentient,secondary;
    NativeRead read;
    migration::ErrorEntry error;
    std::uintptr_t image;
    std::byte *actors,*sentients,*knowledge,*indexedWords,*history,*scratch,*secondaryActors;
    WholeReader whole;
};
static_assert(sizeof(NativeBindings)==112 && offsetof(NativeBindings,image)==40 && offsetof(NativeBindings,scratch)==88 && offsetof(NativeBindings,secondaryActors)==96 && offsetof(NativeBindings,whole)==104);
static_assert(std::is_standard_layout_v<NativeBindings> && std::is_trivially_copyable_v<NativeBindings>);
struct ReadBranches {std::uintptr_t actor,sentient,secondary,whole;};
static_assert(sizeof(ReadBranches)==32 && offsetof(ReadBranches,whole)==24 && std::is_standard_layout_v<ReadBranches> && std::is_trivially_copyable_v<ReadBranches>);
extern "C" __declspec(dllexport) NativeBindings Bo3ActorNativeBindings;
extern "C" __declspec(dllexport) ReadBranches Bo3ActorReadBranches;
extern "C" __declspec(dllexport) void ReadActorState(void*) noexcept(false);
extern "C" __declspec(dllexport) void ReadSentientState(void*) noexcept(false);
extern "C" __declspec(dllexport) void ReadSecondaryState(void*) noexcept(false);
// The guarded native call retains its legacy length and destination arguments.
extern "C" __declspec(dllexport) void ReadActorHistory(void*,std::uint32_t,void*) noexcept(false);
extern "C" __declspec(dllexport) void ActorReadReentry(void*);
extern "C" __declspec(dllexport) void SentientReadReentry(void*);
extern "C" __declspec(dllexport) void SecondaryReadReentry(void*);
extern "C" __declspec(dllexport) bool LoadActorState(void*) noexcept(false);
extern "C" __declspec(dllexport) bool ActorLoadReentry(void*);
}
