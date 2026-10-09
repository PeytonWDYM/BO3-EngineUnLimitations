#pragma once
#include "StateAdapter.h"
#include <type_traits>

namespace bo3::vm {
using InsertFunction = void (*)(std::uint32_t, std::uint32_t, std::uint64_t, std::uint32_t);
enum class NativeModePolicy : std::uint32_t { Any, ZombiesOnly };
struct NativeStateBindings {
    std::uintptr_t imageBase;
    std::uint32_t total, clientRoots, stockClientRoots;
    NativeModePolicy modePolicy;
    WholeFunction originalClientReader, originalClientWriter;
    InsertFunction originalInsert;
};
static_assert(std::is_standard_layout_v<NativeStateBindings> && std::is_trivially_copyable_v<NativeStateBindings>);
static_assert(sizeof(NativeStateBindings) == 48);
static_assert(offsetof(NativeStateBindings, total) == 8);
static_assert(offsetof(NativeStateBindings, modePolicy) == 20);
static_assert(offsetof(NativeStateBindings, originalClientReader) == 24);
static_assert(offsetof(NativeStateBindings, originalClientWriter) == 32);
static_assert(offsetof(NativeStateBindings, originalInsert) == 40);
extern "C" __declspec(dllexport) NativeStateBindings Bo3VmStateBindings;

// The caller verifies all code ranges, pool capacity, and client allocation bounds before binding.
void BindNativeState(const NativeStateBindings&);
extern "C" __declspec(dllexport) StateError ReadNativeState(std::uint32_t instance, void* file);
extern "C" __declspec(dllexport) StateError WriteNativeState(std::uint32_t instance, void* file);
extern "C" __declspec(dllexport) void InsertNativeStateKey(std::uint32_t instance, std::uint32_t id, std::uint64_t key, std::uint32_t parent);
// The native engine error handler must clear this context before its non-local error exit.
extern "C" __declspec(dllexport) void ClearNativeImportContext();
}
