#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include "../../launch/activation/ActivationBoundary.h"
#include <audiopolicy.h>
#include <mmdeviceapi.h>
#include <wrl/client.h>
#include <atomic>
#include <filesystem>
#include <functional>
#include <stdexcept>
#include <string>
#include <vector>

namespace driver_probe {
using Microsoft::WRL::ComPtr;
struct Failure final : std::runtime_error {
    HRESULT code;
    Failure(HRESULT value, const char* stage) : std::runtime_error(stage), code(value) {}
};
struct Trace {
    unsigned generation = 0;
    std::vector<std::string> events;
    std::function<void(IUnknown*)> publication;
    void Call(const char* stage, HRESULT result);
    void Fact(const char* name, const std::string& json);
    void Publish(IUnknown* object, const char* name);
};
std::string Quote(const std::string& value);
std::string Utf8(const wchar_t* value);
std::string Hresult(HRESULT value);
void Check(Trace& trace, const char* stage, HRESULT result);
bool SameIdentity(Trace& trace, IUnknown* first, IUnknown* second);
struct SilenceFormat { BYTE byte; WORD alignment; };
SilenceFormat ValidateFormat(const WAVEFORMATEX& format);
void FillSilence(void* data, size_t bytes, SilenceFormat format);
WAVEFORMATEX Wave(WORD tag, WORD bits);
std::string FormatJson(const WAVEFORMATEX& format);
bool RunWasapi(activation::Boundary& boundary, Trace& trace, const WAVEFORMATEX* ownedFormat = nullptr, bool wait = false);
bool RunDirectSound(activation::Boundary& boundary, Trace& trace, const WAVEFORMATEX& format, bool wait = false);
std::filesystem::path EvidencePath(const std::filesystem::path& requested);
bool ExplicitPhysicalMode(int argc, const wchar_t* const* argv);
}
