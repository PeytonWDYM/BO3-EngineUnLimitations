#pragma once
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <Windows.h>
#include <cstdint>
#include <cstddef>

namespace bo3::actors {
class ActorArena final {
public:
    static constexpr std::size_t Bytes=0xC000000;
    ActorArena(HANDLE process,std::uintptr_t game,std::uint32_t imageBytes);
    ~ActorArena();
    ActorArena(const ActorArena&)=delete;
    ActorArena& operator=(const ActorArena&)=delete;
    std::uintptr_t Base() const noexcept {return base_;}
    std::size_t Size() const noexcept {return Bytes;}
    void Write(std::size_t offset,const void* bytes,std::size_t count);
    void Protect();
    // The caller commits only after source publication and runtime registration succeed.
    void Commit() noexcept {committed_=true;}
private:
    HANDLE process_{};
    std::uintptr_t base_{};
    bool committed_{};
};
}
