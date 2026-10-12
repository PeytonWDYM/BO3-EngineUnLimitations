#include "LoadContext.h"
#include <atomic>
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

namespace bo3::actors {
extern "C" {__declspec(dllexport) constinit LoadBindings Bo3ActorLoadBindings{};}
namespace {
constinit std::atomic<std::uint32_t> owner{};
void* activeFile{};
constexpr std::uint32_t BufferBytes=32*1024*1024;
}
bool BeginLoad(const RootHeader& header,void* file,std::uint32_t thread,std::uint32_t bufferBytes) {
    if (!Bo3ActorLoadBindings.counts || !file || !thread || bufferBytes!=BufferBytes || !header.size || header.size>bufferBytes || header.magic!=0x4864 ||
        (header.version!=3 && header.version!=VmOnlyVersion && header.version!=Actor500Version))return false;
    std::uint32_t expected=0;
    if(!owner.compare_exchange_strong(expected,thread,std::memory_order_acq_rel))return false;
    activeFile=file;
    *Bo3ActorLoadBindings.counts=header.version==Actor500Version ? ExpandedCounts : LegacyCounts;
    return true;
}
bool ReaderAllowed(void* file,std::uint32_t thread) {
    if(!file || !thread)return false;
    const auto current=owner.load(std::memory_order_acquire);
    return current==thread && activeFile==file;
}
bool EndLoad(void* file,std::uint32_t thread) {
    if(owner.load(std::memory_order_acquire)!=thread || !thread || activeFile!=file)return false;
    *Bo3ActorLoadBindings.counts=LegacyCounts;activeFile=nullptr;
    owner.store(0,std::memory_order_release);
    return true;
}
void ClearLoadContext(std::uint32_t thread) {
    if(thread && owner.load(std::memory_order_acquire)==thread) {
        *Bo3ActorLoadBindings.counts=LegacyCounts;activeFile=nullptr;
        owner.store(0,std::memory_order_release);
    }
}
void ClearCurrentLoadContext() {ClearLoadContext(GetCurrentThreadId());}
}
