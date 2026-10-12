#pragma once
#include "../vm_startup/NativePlan.h"
#include "ActorArena.h"
#include <memory>

namespace bo3::actors {
struct HelperOffsets {
    std::uint32_t countBindings,nativeBindings,readBranches,runtimeBindings,activate,phaseHandler;
    std::uint32_t actorReader,sentientReader,secondaryReader,historyReader;
    std::uint32_t actorReentry,sentientReentry,secondaryReentry;
    std::uint32_t wholeReader,wholeReentry;
};
struct RuntimePlan {
    std::vector<vm_startup::AddressEdit> edits;
    std::shared_ptr<ActorArena> arena;
};
// Prepare and protect an unpublished arena. The caller publishes the returned edits as one transaction.
RuntimePlan BuildRuntimePlan(HANDLE process,vm_startup::ImageRange game,vm_startup::ImageRange helper,const HelperOffsets&);
}
