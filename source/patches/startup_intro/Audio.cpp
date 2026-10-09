#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include "Audio.h"
#include "Wave.h"
#include "Plan.h"
#include <cstring>

namespace bo3::startup_intro {
extern "C" {
__declspec(dllexport) constinit AudioBindings Bo3IntroAudioBindings{};
__declspec(dllexport) constinit volatile long Bo3IntroAudioStatus=0;
}
namespace {SRWLOCK audioLock=SRWLOCK_INIT;}
std::uint32_t StartCustomIntro(const char* name,const char* context,std::uint32_t flags,
    float volume,const void* callback,int id) {
    if(name && std::strcmp(name,kCustomName)==0)
        InterlockedCompareExchange(&Bo3IntroAudioStatus,4,0);
    return Bo3IntroAudioBindings.startMovie(name,context,flags,volume,callback,id);
}
void UpdateCustomIntroPlayers() {
    const auto& binding=Bo3IntroAudioBindings;
    binding.updatePlayers();
    if(InterlockedCompareExchange(&Bo3IntroAudioStatus,0,0)!=4) return;
    AcquireSRWLockExclusive(&audioLock);
    // This native update runs before the first image is displayed, including
    // while the outer startup thread is still initializing. No new thread or
    // external player is needed. The admitted native routine fixes this layout.
    if(Bo3IntroAudioStatus==4 && *binding.playerCount==1) {
        const auto player=*binding.players;
        if(player) {
            const auto state=*reinterpret_cast<const volatile std::uint32_t*>(player+0x321c8);
            if(state==6 || state==7) Bo3IntroAudioStatus=StartWave()?1:2;
        }
    }
    ReleaseSRWLockExclusive(&audioLock);
}
bool IsCustomIntroPlaying() {
    const bool playing=Bo3IntroAudioBindings.isPlaying();
    if(!playing) {
        AcquireSRWLockExclusive(&audioLock);
        if(InterlockedExchange(&Bo3IntroAudioStatus,3)==1) StopWave();
        ReleaseSRWLockExclusive(&audioLock);
    }
    return playing;
}
}
