#pragma once
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include "handler_bridge.hpp"
#include <cstdint>
#include <type_traits>

namespace bo3::actors {
struct RuntimeBindings {
    std::uintptr_t image,arena;
    PRUNTIME_FUNCTION functions;
    std::uint32_t functionCount,phaseCount;
    const actor_pool::NativeHandlerFrame* phases;
};
static_assert(sizeof(RuntimeBindings)==40 && std::is_trivially_copyable_v<RuntimeBindings>);
static_assert(sizeof(actor_pool::NativeHandlerFrame)==56);
extern "C" __declspec(dllexport) RuntimeBindings Bo3ActorRuntimeBindings;
// The startup gate calls this on the primary thread before it returns to game code.
extern "C" __declspec(dllexport) bool ActivateActorRuntime();
extern "C" __declspec(dllexport) EXCEPTION_DISPOSITION ActorPhaseHandler(PEXCEPTION_RECORD,PVOID,PCONTEXT,PDISPATCHER_CONTEXT);
}
