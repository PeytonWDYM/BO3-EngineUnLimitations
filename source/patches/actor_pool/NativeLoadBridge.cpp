#include "NativeLoadBridge.h"
#include "ActorRecord.h"
#include <cstring>
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#pragma comment(linker,"/EXPORT:ActorReadReentry")
#pragma comment(linker,"/EXPORT:SentientReadReentry")
#pragma comment(linker,"/EXPORT:SecondaryReadReentry")
#pragma comment(linker,"/EXPORT:ActorLoadReentry")

namespace bo3::actors {
extern "C" {
__declspec(dllexport) constinit NativeBindings Bo3ActorNativeBindings{};
__declspec(dllexport) constinit ReadBranches Bo3ActorReadBranches{};
}
namespace {
constexpr std::uint32_t LegacyHistoryBytes=20*0x684,HistoryRowBytes=13004,HistoryBytes=20*HistoryRowBytes;
void Refuse(const char* message) {
    ClearCurrentLoadContext();
    Bo3ActorNativeBindings.error("actor_pool",0,2,"%s",message);
}
bool RequireScope(void* file) {
    if(ReaderAllowed(file,GetCurrentThreadId()))return true;
    Refuse("Actor reader has no matching root load scope");return false;
}
bool ReadScoped(void* file,Reader reader) {
    if(!RequireScope(file))return false;
    try {reader(file);}
    catch(...) {ClearCurrentLoadContext();throw;}
    if(static_cast<const migration::WrittenState*>(file)->overflow) {
        Refuse("Actor state input is incomplete");return false;
    }
    return true;
}
}
void ReadActorState(void* file) noexcept(false) {
    if(!ReadScoped(file,Bo3ActorNativeBindings.actor))return;
    if(Bo3ActorLoadBindings.counts->actorBytes==LegacyCounts.actorBytes) {
        auto* unused=Bo3ActorNativeBindings.actors+LegacyCounts.actorBytes;
        std::memset(unused,0,static_cast<std::size_t>(ExpandedCounts.actorBytes-LegacyCounts.actorBytes));
        InitializeActorRecords(unused,500-64,Bo3ActorNativeBindings.image);
    }
}
void ReadSentientState(void* file) noexcept(false) {
    if(!ReadScoped(file,Bo3ActorNativeBindings.sentient))return;
    if(Bo3ActorLoadBindings.counts->sentientBytes==LegacyCounts.sentientBytes)
        std::memset(Bo3ActorNativeBindings.sentients+LegacyCounts.sentientBytes,0,
            static_cast<std::size_t>(ExpandedCounts.sentientBytes-LegacyCounts.sentientBytes));
    // Native load discards awareness entries and indexed words. Clear unused rows and columns too.
    std::memset(Bo3ActorNativeBindings.knowledge,0,540ull*540*0x48);
    std::memset(Bo3ActorNativeBindings.indexedWords,0,540ull*540*2);
}
void ReadSecondaryState(void* file) noexcept(false) {
    if(!ReadScoped(file,Bo3ActorNativeBindings.secondary))return;
    if(Bo3ActorLoadBindings.counts->secondaryRecords==LegacyCounts.secondaryRecords)
        std::memset(Bo3ActorNativeBindings.secondaryActors+64*0xB00,0,(500-64)*0xB00);
}
bool LoadActorState(void* file) noexcept(false) {
    // Native startup permits a null file when no saved state exists.
    if(file==nullptr)return Bo3ActorNativeBindings.whole(nullptr);
    if(!RequireScope(file))return false;
    if(Bo3ActorLoadBindings.counts->secondaryRecords==LegacyCounts.secondaryRecords)
        std::memset(Bo3ActorNativeBindings.secondaryActors+64*0xB00,0,(500-64)*0xB00);
    bool loaded;
    try {loaded=Bo3ActorNativeBindings.whole(file);}
    catch(...) {ClearCurrentLoadContext();throw;}
    EndLoad(file,GetCurrentThreadId());
    return loaded;
}
void ReadActorHistory(void* file,std::uint32_t bytes,void* destination) noexcept(false) {
    if(!RequireScope(file))return;
    if(bytes!=LegacyHistoryBytes || reinterpret_cast<std::uintptr_t>(destination)!=Bo3ActorNativeBindings.image+0xA1C3484) {
        Refuse("Actor history call differs from its guarded native contract");return;
    }
    const bool legacy=Bo3ActorLoadBindings.counts->actorBytes==LegacyCounts.actorBytes;
    const auto readBytes=legacy?LegacyHistoryBytes:HistoryBytes;
    try {Bo3ActorNativeBindings.read(file,readBytes,Bo3ActorNativeBindings.scratch);}
    catch(...) {ClearCurrentLoadContext();throw;}
    if(static_cast<const migration::WrittenState*>(file)->overflow) {
        Refuse("Actor history input is incomplete");return;
    }
    auto* history=Bo3ActorNativeBindings.history;
    const auto* scratch=Bo3ActorNativeBindings.scratch;
    if(!legacy) {std::memcpy(history,scratch,HistoryBytes);return;}
    std::memset(history,0,HistoryBytes);
    for(std::uint32_t row=0;row<20;++row) {
        auto* target=history+row*HistoryRowBytes;
        const auto* source=scratch+row*0x684;
        std::memcpy(target,source,0x300);
        std::memcpy(target+6000,source+0x300,0x300);
        std::memcpy(target+12000,source+0x600,64);
        std::memcpy(target+12500,source+0x640,64);
        std::memcpy(target+13000,source+0x680,4);
    }
}
}
