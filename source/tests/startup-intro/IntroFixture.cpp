#include "../../patches/startup_intro/Plan.h"
#include <array>
#include <cstdio>
#include <functional>
#include <stdexcept>

namespace {
void Check(bool value,const char* message) {if(!value)throw std::runtime_error(message);}
bool Refuses(const std::function<void()>& call) {try{call();}catch(const std::runtime_error&){return true;}return false;}
}
int main() {
    try {
        constexpr std::array<unsigned char,54> original{
            0xf3,0x0f,0x10,0x1d,0x5a,0x46,0xe2,0x00,0x33,0xc0,0x48,0x8d,0x0d,0xc5,0x16,0xed,0x00,
            0x89,0x44,0x24,0x28,0x45,0x33,0xc0,0x33,0xd2,0x48,0x89,0x44,0x24,0x20,
            0xe8,0x1a,0xe3,0x1c,0xff,0x89,0x05,0x64,0x56,0x27,0x03,0xe8,0x0f,0x7e,0x19,0x00,
            0x83,0x3d,0x58,0x56,0x27,0x03,0x00};
        constexpr std::array<unsigned char,21> entry{
            0x48,0x8b,0xc4,0x55,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,0x48,0x81,0xec,0x70,0x01,0x00,0x00};
        constexpr char name[]="BO3_Global_Logo_LogoSequence";
        const auto label=std::span(reinterpret_cast<const unsigned char*>(name),sizeof(name));
        const vm_startup::ImageRange image{0x140000000ull,494186496};
        const auto edit=bo3::startup_intro::BuildPlan(image,original,label,entry);
        Check(edit.address==image.base+0x20f00a1 && edit.original==std::vector<unsigned char>{0xe8,0x1a,0xe3,0x1c,0xff}
            && edit.replacement==std::vector<unsigned char>{0x33,0xc0,0x90,0x90,0x90},"Wrong startup edit.");
        std::puts("exact-startup-call-zero-playback-id passed");
        for(const auto index:{12u,32u,37u,53u}) {
            auto changed=original;changed[index]^=1;
            Check(Refuses([&]{bo3::startup_intro::BuildPlan(image,changed,label,entry);}),"Changed startup context admitted.");
        }
        Check(Refuses([&]{bo3::startup_intro::BuildPlan(image,std::span(original).first(53),label,entry);}),"Short context admitted.");
        std::puts("changed-arguments-call-result-and-short-read-refused passed");
        auto changedLabel=std::vector<unsigned char>(label.begin(),label.end());changedLabel.back()=1;
        auto changedEntry=entry;changedEntry[0]^=1;
        Check(Refuses([&]{bo3::startup_intro::BuildPlan(image,original,changedLabel,entry);})
            && Refuses([&]{bo3::startup_intro::BuildPlan(image,original,label,changedEntry);}),"Wrong cinematic admitted.");
        std::puts("wrong-logo-or-cinematic-entry-refused passed");
        Check(Refuses([&]{bo3::startup_intro::BuildPlan({image.base,494186495},original,label,entry);})
            && Refuses([&]{bo3::startup_intro::BuildPlan({UINTPTR_MAX-1024,494186496},original,label,entry);}),"Invalid image admitted.");
        std::puts("wrong-image-or-address-overflow-refused passed");
        return 0;
    }catch(const std::exception& error){std::printf("refusal=%s\n",error.what());return 1;}
}
