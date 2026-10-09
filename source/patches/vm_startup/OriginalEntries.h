#pragma once
#include "../vm_pool/StateAdapter.h"
#include "StateErrors.h"

namespace bo3::vm {
extern "C" __declspec(dllexport) void NativeOriginalReader(std::uint32_t,void*);
extern "C" __declspec(dllexport) void NativeOriginalWriter(std::uint32_t,void*);
extern "C" __declspec(dllexport) void NativeOriginalInsert(std::uint32_t,std::uint32_t,std::uint64_t,std::uint32_t);
extern "C" __declspec(dllexport) void NativeOriginalError(const char*,int,int,const char*,...);
}
