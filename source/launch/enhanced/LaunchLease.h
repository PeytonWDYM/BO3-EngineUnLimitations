#pragma once
#include "../preentry/Identity.h"

namespace bo3::enhanced {
// One enhanced game per Windows session. Hold this before file validation through child exit.
class LaunchLease {
    Handle mutex_;
public:
    LaunchLease() : mutex_(CreateMutexW(nullptr, TRUE, L"Local\\BO3EngineUnLimitations.EnhancedZombies")) {
        const auto error = GetLastError();
        Require(mutex_.value != nullptr, "Cannot create the enhanced launch lease.");
        Require(error != ERROR_ALREADY_EXISTS, "Another enhanced Zombies launcher is active. Close its game first.");
    }
    ~LaunchLease() { ReleaseMutex(mutex_.value); }
    LaunchLease(const LaunchLease&) = delete;
    LaunchLease& operator=(const LaunchLease&) = delete;
};
}
