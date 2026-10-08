#include "SessionReceipt.h"
#include "../preentry/Identity.h"
#include <ShlObj.h>
#include <sstream>

namespace bo3::enhanced {
namespace {
std::string Quote(std::string_view text) {
    std::string result = "\"";
    for (unsigned char c : text) {
        if (c == '\\' || c == '"') result += '\\';
        Require(c >= 32 && c < 127, "The receipt text must use printable ASCII.");
        result += static_cast<char>(c);
    }
    return result + '"';
}
}
SessionReceipt::SessionReceipt(const PROCESS_INFORMATION& child)
    : file_(INVALID_HANDLE_VALUE), processId_(child.dwProcessId), created_(0) {
    FILETIME created{}, exited{}, kernel{}, user{};
    Require(GetProcessTimes(child.hProcess, &created, &exited, &kernel, &user) != FALSE, "Cannot read the owned process identity.");
    created_ = static_cast<std::uint64_t>(created.dwHighDateTime) << 32 | created.dwLowDateTime;
    PWSTR directory = nullptr;
    Require(SHGetKnownFolderPath(FOLDERID_LocalAppData, KF_FLAG_DEFAULT, nullptr, &directory) == S_OK,
        "Cannot locate the private session directory.");
    path_ = std::filesystem::path(directory) / L"BO3 Engine UnLimitations" / L"sessions";
    CoTaskMemFree(directory);
    std::filesystem::create_directories(path_);
    path_ /= std::to_wstring(created_) + L"-" + std::to_wstring(processId_) + L".json";
    file_ = CreateFileW(path_.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    Require(file_ != INVALID_HANDLE_VALUE, "Cannot create the private startup receipt.");
}
SessionReceipt::~SessionReceipt() { CloseHandle(file_); }
void SessionReceipt::Write(const vm_startup::Receipt& receipt, std::uintptr_t helper, std::string_view status, std::string_view error) {
    std::ostringstream text;
    text << "{\"schema\":1,\"candidate\":\"0.1.0-test.3\",\"status\":" << Quote(status)
        << ",\"processId\":" << processId_ << ",\"processCreatedFileTime\":" << created_
        << ",\"imageBase\":" << receipt.imageBase << ",\"helperBase\":" << helper
        << ",\"serverTotal\":500001,\"clientTotal\":65000,\"clientRoots\":18,\"stockClientRoots\":8"
        << ",\"migrationBufferBytes\":33554432,\"editsWritten\":" << receipt.editsWritten
        << ",\"activated\":" << (receipt.activated ? "true" : "false")
        << ",\"rollbackCompleted\":" << (receipt.rollbackCompleted ? "true" : "false")
        << ",\"exited\":" << (receipt.exited ? "true" : "false") << ",\"exitCode\":" << receipt.exitCode
        << ",\"error\":" << Quote(error) << "}\n";
    const auto bytes = text.str();
    LARGE_INTEGER begin{};
    Require(SetFilePointerEx(file_, begin, nullptr, FILE_BEGIN) != FALSE, "Cannot rewind the startup receipt.");
    DWORD written = 0;
    Require(WriteFile(file_, bytes.data(), static_cast<DWORD>(bytes.size()), &written, nullptr) != FALSE && written == bytes.size()
        && SetEndOfFile(file_) && FlushFileBuffers(file_), "Cannot save the startup receipt.");
}
}
