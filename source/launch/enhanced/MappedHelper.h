#pragma once
#include "Boot.h"
#include "../../patches/vm_startup/NativePlan.h"
#include "../../patches/vm_migration/MigrationPlan.h"
#include <filesystem>

namespace bo3::enhanced {
// Inspect the locked DLL without running its entry. Match executable sections in the stopped child.
class MappedHelper {
    HMODULE mapped_;
    std::uint32_t bootOffset_;
public:
    vm_startup::ImageRange image;
    vm_startup::HelperOffsets state;
    migration::HelperOffsets migration;
    std::uint32_t introAudioBindings=0,introAudioHandler=0,introStartHandler=0,introUpdateHandler=0;
    std::uint32_t originalIntro=0,originalIntroUpdate=0;
    explicit MappedHelper(const std::filesystem::path&);
    ~MappedHelper();
    void Admit(HANDLE process, const std::filesystem::path& file);
    MappedHelper(const MappedHelper&) = delete;
    MappedHelper& operator=(const MappedHelper&) = delete;
};
}
