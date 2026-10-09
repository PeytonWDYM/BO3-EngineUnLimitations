#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <audioclient.h>
#include <dsound.h>
#include <mmreg.h>
#include <wrl/client.h>
#include <atomic>
#include <algorithm>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace fixture {
using Microsoft::WRL::ComPtr;
inline constexpr GUID EscapeId = {0x74cab383, 0x2d3c, 0x44dd, {0xb8, 0x10, 0x37, 0xe5, 0xe9, 0xdb, 0xd4, 0x87}};
struct Packet { UINT32 frames; DWORD flags; bool silent; std::vector<BYTE> bytes; };
struct RenderState {
    UINT32 channels = 2;
    bool pending = false;
    bool destroyed = false;
    UINT32 requested = 0;
    HRESULT getError = S_OK;
    HRESULT releaseError = S_OK;
    std::vector<BYTE> memory;
    std::vector<Packet> packets;
};
ComPtr<IAudioRenderClient> MakeRender(const std::shared_ptr<RenderState>& state);

struct SoundState {
    WAVEFORMATEXTENSIBLE format{};
    DWORD formatBytes = sizeof(WAVEFORMATEX);
    DWORD caps = 0x80e8;
    std::vector<BYTE> memory;
    BYTE silence = 0;
    bool playing = false;
    bool locked = false;
    bool lost = false;
    bool destroyed = false;
    DWORD position = 0;
    LONG volume = 0;
    LONG pan = 0;
    DWORD frequency = 48000;
    LPVOID first = nullptr;
    LPVOID second = nullptr;
    DWORD firstBytes = 0;
    DWORD secondBytes = 0;
    HRESULT lockError = S_OK;
    HRESULT unlockError = S_OK;
    HRESULT playError = S_OK;
    HRESULT restoreError = S_OK;
    unsigned unlockCalls = 0;
    std::vector<bool> outputs;
};
std::shared_ptr<SoundState> MakeSoundState(WORD tag, WORD bits, WORD channels, bool extensible = false);
ComPtr<IDirectSoundBuffer8> MakeSound(const std::shared_ptr<SoundState>& state);
HRESULT RenderBoundary(IAudioRenderClient* sink, IAudioRenderClient** output);
HRESULT SoundBoundary(IDirectSoundBuffer8* sink, IDirectSoundBuffer8** output);
bool IsSilent(const SoundState& state);
std::string Hex(const std::vector<BYTE>& bytes);
std::string Hresult(HRESULT result);
std::string Quote(const std::string& value);
void Require(bool condition, const char* message);
void Ok(HRESULT result);
struct Scenario {
    std::string name;
    bool passed = false;
    std::string error;
    std::vector<std::pair<std::string, std::string>> evidence;
    void Number(const std::string& name, unsigned value);
    void String(const std::string& name, const std::string& value);
    void Boolean(const std::string& name, bool value);
};
class Report {
public:
    template<typename Action> void Run(const char* name, Action action) {
        Scenario scenario;
        scenario.name = name;
        try { action(scenario); scenario.passed = true; }
        catch (const std::exception& error) { scenario.error = error.what(); }
        scenarios.push_back(std::move(scenario));
    }
    int Write(const char* path, bool baseline) const;
private:
    std::vector<Scenario> scenarios;
};
void RenderScenarios(Report& report);
void SoundScenarios(Report& report);
}
