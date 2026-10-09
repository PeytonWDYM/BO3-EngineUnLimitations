#pragma once
#include "../vm_pool/StateAdapter.h"
#include <type_traits>

namespace bo3::vm {
using ErrorFunction = void (*)(const char*, int, int, const char*, ...);
using StateFunction = StateError (*)(std::uint32_t, void*);
struct ErrorBindings {
    ErrorFunction entry;
    ErrorFunction original;
    StateFunction read;
    StateFunction write;
};
static_assert(std::is_standard_layout_v<ErrorBindings> && std::is_trivially_copyable_v<ErrorBindings>);
static_assert(sizeof(ErrorBindings)==32 && offsetof(ErrorBindings,original)==8
    && offsetof(ErrorBindings,read)==16 && offsetof(ErrorBindings,write)==24);
extern "C" __declspec(dllexport) ErrorBindings Bo3VmErrorBindings;
extern "C" __declspec(dllexport) void ReadStateOrDrop(std::uint32_t instance, void* file);
extern "C" __declspec(dllexport) void WriteStateOrDrop(std::uint32_t instance, void* file);
extern "C" __declspec(dllexport) void VmErrorPrelude(const char*, int, int, const char*, ...);
}
