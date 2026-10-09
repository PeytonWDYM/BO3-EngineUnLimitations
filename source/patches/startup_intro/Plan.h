#pragma once
#include "../vm_startup/NativePlan.h"
#include <algorithm>
#include <span>
#include <stdexcept>

namespace bo3::startup_intro {
inline constexpr std::uint32_t kContextRva=0x20f0082,kCallRva=0x20f00a1;
inline constexpr std::uint32_t kNameRva=0x2fc1758,kCinematicRva=0x12be3c0;
inline constexpr std::array<unsigned char,54> kContext{
    0xf3,0x0f,0x10,0x1d,0x5a,0x46,0xe2,0x00,0x33,0xc0,0x48,0x8d,0x0d,0xc5,0x16,0xed,0x00,
    0x89,0x44,0x24,0x28,0x45,0x33,0xc0,0x33,0xd2,0x48,0x89,0x44,0x24,0x20,
    0xe8,0x1a,0xe3,0x1c,0xff,0x89,0x05,0x64,0x56,0x27,0x03,0xe8,0x0f,0x7e,0x19,0x00,
    0x83,0x3d,0x58,0x56,0x27,0x03,0x00};
inline constexpr std::array<unsigned char,21> kCinematicEntry{
    0x48,0x8b,0xc4,0x55,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,0x48,0x81,0xec,0x70,0x01,0x00,0x00};
inline constexpr char kName[]="BO3_Global_Logo_LogoSequence";
inline constexpr char kCustomName[]="BO3_500K_Custom_Intro";
// Pure preparation. The caller first admits the exact game build and reads these
// spans while all its threads are stopped. PausedPatch owns publication/rollback.
inline vm_startup::AddressEdit BuildPlan(vm_startup::ImageRange image,
    std::span<const unsigned char> context,std::span<const unsigned char> name,
    std::span<const unsigned char> cinematic,bool custom=false) {
    if(image.size!=494186496 || image.base>UINTPTR_MAX-image.size)
        throw std::runtime_error("Unsupported startup intro image range.");
    const auto equal=[](auto actual,auto expected) {
        return actual.size()==expected.size() && std::equal(actual.begin(),actual.end(),expected.begin());
    };
    const auto label=std::span(reinterpret_cast<const unsigned char*>(kName),sizeof(kName));
    if(!equal(context,std::span(kContext)) || !equal(name,label) || !equal(cinematic,std::span(kCinematicEntry)))
        throw std::runtime_error("The exact startup intro context differs. No intro edit prepared.");
    if(custom) {
        // Preserve the engine call, playback ID, frame pump and normal teardown.
        // Only the exact startup movie label changes; the stock file is untouched.
        std::vector<unsigned char> replacement(sizeof(kName),0);
        std::copy_n(reinterpret_cast<const unsigned char*>(kCustomName),sizeof(kCustomName),replacement.begin());
        return {image.base+kNameRva,{label.begin(),label.end()},std::move(replacement)};
    }
    // Zero is the engine's inactive playback ID. Its existing result store and
    // continuation remain intact; every other cinematic call is unchanged.
    return {image.base+kCallRva,{0xe8,0x1a,0xe3,0x1c,0xff},{0x33,0xc0,0x90,0x90,0x90}};
}
}
