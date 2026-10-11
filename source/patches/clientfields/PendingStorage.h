#pragma once
#include "PendingProfile.h"

namespace bo3::clientfields {
// RW backing near both native LEAs. Ownership lasts through rollback, or the child lifetime on commit.
class PendingStorage {
    HANDLE process_;
    std::uintptr_t address_{};
    bool committed_{};
public:
    PendingStorage(HANDLE,std::uintptr_t image);
    ~PendingStorage();
    PendingStorage(const PendingStorage&)=delete;
    PendingStorage& operator=(const PendingStorage&)=delete;
    std::uintptr_t Address() const noexcept {return address_;}
    std::size_t Size() const noexcept {return kPendingStorageBytes;}
    void Commit() noexcept {committed_=true;}
};
}
