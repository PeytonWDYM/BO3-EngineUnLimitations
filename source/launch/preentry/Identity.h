#pragma once
#include <windows.h>
#include <filesystem>
#include <string>
#include <vector>

struct Handle {
    HANDLE value = nullptr;
    ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
    Handle() = default;
    explicit Handle(HANDLE handle) : value(handle) {}
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
};
void Require(bool condition, const char* operation);
void VerifyFile(const std::filesystem::path& path, const char* expected, std::vector<HANDLE>& locks);
std::filesystem::path PrivateOutput(const wchar_t* text);
