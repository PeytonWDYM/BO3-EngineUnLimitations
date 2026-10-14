#pragma once
#include "PendingProfile.h"
#include "CounterProfile.h"

namespace bo3::clientfields {
inline constexpr std::uint32_t kCounterStorageOffset=(kPendingStorageBytes+15)&~15u;
inline constexpr std::uint32_t kClientfieldStorageBytes=kCounterStorageOffset+kCounterStorageBytes;
// Complete RW callback/counter backing. Rollback releases it. Commit retains it for the child lifetime.
class ClientfieldStorage {
    HANDLE process_;
    std::uintptr_t address_{};
    bool committed_{};
public:
    ClientfieldStorage(HANDLE,std::uintptr_t image);
    ~ClientfieldStorage();
    ClientfieldStorage(const ClientfieldStorage&)=delete;
    ClientfieldStorage& operator=(const ClientfieldStorage&)=delete;
    std::uintptr_t Address() const noexcept {return address_;}
    std::uintptr_t CounterAddress() const noexcept {return address_+kCounterStorageOffset;}
    std::size_t Size() const noexcept {return kClientfieldStorageBytes;}
    void Commit() noexcept {committed_=true;}
};
}
