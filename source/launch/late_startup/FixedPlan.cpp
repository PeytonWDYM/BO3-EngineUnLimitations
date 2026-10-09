#include "FixedPlan.h"
#include "../preentry/Identity.h"
#include "GameManifest.h"
#include "../../patches/startup_intro/Plan.h"
#include "../../patches/startup_intro/AudioPlan.h"
#include <algorithm>

namespace bo3::late_startup {
PreparedPlan PrepareFixedPlan(HANDLE process,std::uintptr_t image,
    enhanced::MappedHelper& helper,const std::filesystem::path& helperFile,bool skipStartupIntro,bool customStartupIntro) {
    constexpr std::uint32_t total=500001;
    const auto& manifest=enhanced::ExactGameManifest;
    Require(manifest.guards.size()==82 && manifest.counts.size()==19,"The fixed complete inventory is required.");
    enhanced::VerifyGameCode(process,image,manifest);
    enhanced::VerifyMigrationUnallocated(process,image);
    for(const auto rva:{0x5124580u,0x5124500u,0x5124680u,0x5124600u,0x16dbb638u}) {
        const auto bytes=vm_startup::ReadStopped(process,image+rva,8);
        Require(std::all_of(bytes.begin(),bytes.end(),[](unsigned char value){return value==0;}),
            "VM or migration storage already exists. Late activation refused.");
    }
    const auto receiveSize=vm_startup::ReadStopped(process,image+0x16dbb640u,4);
    Require(std::all_of(receiveSize.begin(),receiveSize.end(),[](unsigned char value){return value==0;}),
        "Migration receive capacity already exists. Late activation refused.");
    const auto profile=enhanced::MakeGameProfile(manifest,total);
    for(const auto& check:profile.checks)
        Require(vm_startup::ReadStopped(process,image+check.rva,check.bytes.size())==check.bytes,
            "A complete native count instruction or entry prefix differs.");
    helper.Admit(process,helperFile);
    const vm_startup::ImageRange imageRange{image,manifest.imageSize};
    auto entries=std::vector(manifest.entries.begin(),manifest.entries.end());
    for(const auto rva:{0x13619e0u,0x13617f0u,0x21f9aa0u,0x21fa750u,0x12e1c0u,0x2277a60u,0x1361a50u,0x12e226u})
        entries.push_back({rva,{}});
    PreparedPlan result;
    result.helperBase=helper.image.base;
    result.relay=std::make_unique<vm_startup::NearRelay>(process,imageRange,entries);
    result.edits=vm_startup::BuildNativePlan({imageRange,helper.image,manifest.entries,helper.state,
        result.relay->Address(),total,18,8,bo3::vm::NativeModePolicy::ZombiesOnly,{}});
    auto migration=bo3::migration::BuildMigrationPlan({imageRange,helper.image,helper.migration,
        result.relay->Address()+64,total,18,32*1024*1024});
    result.edits.insert(result.edits.end(),std::make_move_iterator(migration.begin()),std::make_move_iterator(migration.end()));
    for(const auto& edit:profile.edits)result.edits.push_back({image+edit.rva,edit.original,edit.replacement});
    Require(result.edits.size()==42,"The fixed native recipe must have 42 edits.");
    if(skipStartupIntro || customStartupIntro) {
        const auto context=vm_startup::ReadStopped(process,image+startup_intro::kContextRva,startup_intro::kContext.size());
        const auto name=vm_startup::ReadStopped(process,image+startup_intro::kNameRva,sizeof(startup_intro::kName));
        const auto cinematic=vm_startup::ReadStopped(process,image+startup_intro::kCinematicRva,startup_intro::kCinematicEntry.size());
        result.edits.push_back(startup_intro::BuildPlan(imageRange,context,name,cinematic,customStartupIntro));
        if(customStartupIntro) {
            const auto loop=vm_startup::ReadStopped(process,image+startup_intro::kLoopRva,startup_intro::kLoop.size());
            const auto playing=vm_startup::ReadStopped(process,image+startup_intro::kPlayingRva,startup_intro::kPlayingEntry.size());
            const auto layout=vm_startup::ReadStopped(process,image+startup_intro::kPlayerLayoutRva,startup_intro::kPlayerLayout.size());
            auto audio=startup_intro::BuildAudioPlan(imageRange,helper.image,helper.introAudioBindings,
                helper.introAudioHandler,helper.introStartHandler,helper.introUpdateHandler,helper.originalIntro,
                helper.originalIntroUpdate,result.relay->Address()+192,loop,playing,layout);
            result.edits.insert(result.edits.end(),std::make_move_iterator(audio.begin()),std::make_move_iterator(audio.end()));
        }
    }
    return result;
}
}
