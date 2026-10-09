#pragma once
#include "../../launch/late_startup/OwnedChild.h"
#include "../../patches/vm_startup/PausedPatch.h"
int VerifyOwnedParentDeath(const std::filesystem::path& executable,const std::filesystem::path& output);
[[noreturn]] void DieAfterPartialWrite(const bo3::late_startup::OwnedChild&,const std::filesystem::path&,
    const std::vector<vm_startup::AddressEdit>&);
