#pragma once
#include <windows.h>
#include <cstdint>
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
// Locks the game file, requires the profiled x64 PE timestamp and image size, and returns its SHA-256.
std::string VerifyGameBuild(const std::filesystem::path& path, std::uint32_t timestamp, std::uint32_t imageSize,
    std::vector<HANDLE>& locks);
std::filesystem::path PrivateOutput(const wchar_t* text);
