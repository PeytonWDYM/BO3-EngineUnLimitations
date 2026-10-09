#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace patch {
class Handle {
public:
    explicit Handle(HANDLE value = nullptr) : value_(value) {}
    ~Handle() { if (value_ && value_ != INVALID_HANDLE_VALUE) CloseHandle(value_); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
    Handle(Handle&& other) noexcept : value_(std::exchange(other.value_, nullptr)) {}
    Handle& operator=(Handle&& other) noexcept {
        if (this != &other) {
            if (value_ && value_ != INVALID_HANDLE_VALUE) CloseHandle(value_);
            value_ = std::exchange(other.value_, nullptr);
        }
        return *this;
    }
    HANDLE get() const { return value_; }
private:
    HANDLE value_;
};

inline std::runtime_error win_error(const std::string& operation) {
    return std::runtime_error(operation + " failed. Windows error " + std::to_string(GetLastError()) + ".");
}

inline std::wstring widen(const std::string& text) {
    const int size = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), nullptr, 0);
    if (size == 0) throw win_error("UTF-8 conversion");
    std::wstring result(size, L'\0');
    if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), result.data(), size)) throw win_error("UTF-8 conversion");
    return result;
}

inline std::string narrow(const std::wstring& text) {
    const int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
    if (size == 0) throw win_error("UTF-8 conversion");
    std::string result(size, '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), result.data(), size, nullptr, nullptr)) throw win_error("UTF-8 conversion");
    return result;
}

inline std::vector<uint8_t> read_bytes(HANDLE process, uintptr_t address, size_t count) {
    std::vector<uint8_t> bytes(count);
    SIZE_T read = 0;
    if (!ReadProcessMemory(process, reinterpret_cast<void*>(address), bytes.data(), count, &read)) throw win_error("ReadProcessMemory");
    if (read != count) throw std::runtime_error("ReadProcessMemory returned a short read.");
    return bytes;
}
}
