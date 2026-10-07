#pragma once
#include "Profile.h"

namespace patch {
class Target {
public:
    Target(DWORD pid, const Profile& profile, bool writable);
    HANDLE process() const { return process_.get(); }
    uintptr_t base() const { return base_; }
    DWORD pid() const { return pid_; }
    bool exited() const;
    void verify_bytes(const std::vector<Record>& records, bool replacement) const;
    void verify_range(const Record& record) const;
private:
    Handle process_;
    Handle executable_;
    uintptr_t base_ = 0;
    uint32_t image_size_ = 0;
    DWORD pid_;
};
}
