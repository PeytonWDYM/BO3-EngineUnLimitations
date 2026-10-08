#pragma once
#include "Coordinator.h"
#include "../enhanced/MappedHelper.h"

namespace bo3::late_startup {
// Exact recipe only: 500001 total, 18 roots, 32 MiB. No runtime inventory override.
PreparedPlan PrepareFixedPlan(HANDLE process,std::uintptr_t image,
    enhanced::MappedHelper& helper,const std::filesystem::path& helperFile);
}
