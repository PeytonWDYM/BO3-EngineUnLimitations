#pragma once
#include "../../patches/vm_startup/DebugGate.h"
#include <filesystem>
#include <string_view>

namespace bo3::enhanced {
class SessionReceipt {
    std::filesystem::path path_;
    HANDLE file_;
    DWORD processId_;
    std::uint64_t created_;
public:
    explicit SessionReceipt(const PROCESS_INFORMATION&);
    ~SessionReceipt();
    void Write(const vm_startup::Receipt&, std::uintptr_t helper, std::string_view status, std::string_view error = {});
    const std::filesystem::path& Path() const { return path_; }
    SessionReceipt(const SessionReceipt&) = delete;
    SessionReceipt& operator=(const SessionReceipt&) = delete;
};
}
