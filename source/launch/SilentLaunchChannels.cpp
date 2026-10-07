// Probe persistent session channel controls. This tool never submits audible samples.
#include <windows.h>
#include <audioclient.h>
#include <audiopolicy.h>
#include <endpointvolume.h>
#include <mmdeviceapi.h>
#include <wrl/client.h>
#include <algorithm>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;

namespace {
void Check(HRESULT result) {
    if (FAILED(result)) {
        throw std::runtime_error("Audio API failed: " + std::to_string(result));
    }
}

std::string JsonString(const wchar_t *value) {
    int bytes = WideCharToMultiByte(CP_UTF8, 0, value, -1, nullptr, 0, nullptr, nullptr);
    if (!bytes) {
        throw std::runtime_error("Cannot encode an audio identifier.");
    }
    std::string utf8(bytes, '\0');
    WideCharToMultiByte(CP_UTF8, 0, value, -1, utf8.data(), bytes, nullptr, nullptr);
    utf8.pop_back();
    std::string escaped = "\"";
    for (char character : utf8) {
        switch (character) {
        case '\\': escaped += "\\\\"; break;
        case '"': escaped += "\\\""; break;
        case '\n': escaped += "\\n"; break;
        case '\r': escaped += "\\r"; break;
        case '\t': escaped += "\\t"; break;
        default: escaped += character;
        }
    }
    return escaped + "\"";
}

std::string DeviceId(IMMDevice *device) {
    LPWSTR value = nullptr;
    Check(device->GetId(&value));
    std::string result = JsonString(value);
    CoTaskMemFree(value);
    return result;
}

// Read only endpoint controls. Session actions never use endpoint setters.
void EndpointSnapshot(IMMDevice *device) {
    ComPtr<IAudioEndpointVolume> volume;
    Check(device->Activate(__uuidof(IAudioEndpointVolume), CLSCTX_ALL, nullptr, &volume));
    float level;
    BOOL muted;
    Check(volume->GetMasterVolumeLevelScalar(&level));
    Check(volume->GetMute(&muted));
    std::printf("{\"kind\":\"endpoint\",\"pid\":%lu,\"endpoint\":%s,\"volume\":%.9g,\"muted\":%s}\n",
        GetCurrentProcessId(), DeviceId(device).c_str(), level, muted ? "true" : "false");
}

void PrintSession(IMMDevice *device, IAudioSessionControl2 *control,
                  ISimpleAudioVolume *master, IChannelAudioVolume *channels,
                  const char *phase) {
    DWORD pid;
    float level;
    BOOL muted;
    UINT32 count;
    Check(control->GetProcessId(&pid));
    Check(master->GetMasterVolume(&level));
    Check(master->GetMute(&muted));
    Check(channels->GetChannelCount(&count));
    std::vector<float> values(count);
    Check(channels->GetAllVolumes(count, values.data()));
    LPWSTR identifier = nullptr;
    LPWSTR instance = nullptr;
    Check(control->GetSessionIdentifier(&identifier));
    Check(control->GetSessionInstanceIdentifier(&instance));
    std::string encodedIdentifier = JsonString(identifier);
    std::string encodedInstance = JsonString(instance);
    CoTaskMemFree(identifier);
    CoTaskMemFree(instance);
    std::printf("{\"kind\":\"session\",\"phase\":\"%s\",\"pid\":%lu,\"endpoint\":%s,"
        "\"session\":%s,\"instance\":%s,\"volume\":%.9g,\"muted\":%s,\"channels\":[",
        phase, pid, DeviceId(device).c_str(), encodedIdentifier.c_str(), encodedInstance.c_str(),
        level, muted ? "true" : "false");
    for (UINT32 index = 0; index < count; index++) {
        std::printf("%s%.9g", index ? "," : "", values[index]);
    }
    std::puts("]}");
}

// Use the current executable's default shared-mode session. No BO3 files are opened.
void DefaultSession(IMMDevice *device, const std::string &action) {
    ComPtr<IAudioClient> client;
    Check(device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, &client));
    WAVEFORMATEX *format = nullptr;
    Check(client->GetMixFormat(&format));
    std::printf("{\"kind\":\"format\",\"pid\":%lu,\"endpoint\":%s,\"mixChannels\":%u,\"sampleRate\":%lu,\"formatTag\":%u}\n",
        GetCurrentProcessId(), DeviceId(device).c_str(), format->nChannels, format->nSamplesPerSec, format->wFormatTag);
    HRESULT initialized = client->Initialize(AUDCLNT_SHAREMODE_SHARED, 0, 1000000, 0, format, nullptr);
    CoTaskMemFree(format);
    Check(initialized);
    ComPtr<IAudioSessionControl> session;
    ComPtr<IAudioSessionControl2> identity;
    ComPtr<ISimpleAudioVolume> master;
    ComPtr<IChannelAudioVolume> channels;
    Check(client->GetService(__uuidof(IAudioSessionControl), &session));
    Check(session.As(&identity));
    Check(client->GetService(__uuidof(ISimpleAudioVolume), &master));
    Check(client->GetService(__uuidof(IChannelAudioVolume), &channels));
    PrintSession(device, identity.Get(), master.Get(), channels.Get(), "initial");

    UINT32 count;
    Check(channels->GetChannelCount(&count));
    if (action == "seed-default" || action == "reset-default") {
        std::vector<float> values(count, action == "seed-default" ? 0.0f : 1.0f);
        Check(channels->SetAllVolumes(count, values.data(), nullptr));
        Check(master->SetMasterVolume(action == "seed-default" ? 0.0f : 1.0f, nullptr));
        Check(master->SetMute(action == "seed-default", nullptr));
    } else if (action == "probe-default") {
        // Simulate an application's startup master reset. Keep the separate channel multiplier.
        Check(master->SetMasterVolume(1.0f, nullptr));
        Check(master->SetMute(FALSE, nullptr));
    }
    PrintSession(device, identity.Get(), master.Get(), channels.Get(), "after");

    UINT32 frames;
    Check(client->GetBufferSize(&frames));
    ComPtr<IAudioRenderClient> renderer;
    Check(client->GetService(__uuidof(IAudioRenderClient), &renderer));
    BYTE *buffer = nullptr;
    Check(renderer->GetBuffer(frames, &buffer));
    Check(renderer->ReleaseBuffer(frames, AUDCLNT_BUFFERFLAGS_SILENT));
    Check(client->Start());
    PrintSession(device, identity.Get(), master.Get(), channels.Get(), "active");
    Sleep(40);
    PrintSession(device, identity.Get(), master.Get(), channels.Get(), "settled");
    if (action == "seed-default" || action == "reset-default") {
        // Reapply after activation to test delayed application policy updates.
        Sleep(260);
        std::vector<float> values(count, action == "seed-default" ? 0.0f : 1.0f);
        Check(channels->SetAllVolumes(count, values.data(), nullptr));
        Check(master->SetMasterVolume(action == "seed-default" ? 0.0f : 1.0f, nullptr));
        Check(master->SetMute(action == "seed-default", nullptr));
        Sleep(100);
        PrintSession(device, identity.Get(), master.Get(), channels.Get(), "reapplied");
    }
    Check(client->Stop());
}

int Inspect(IMMDevice *device, DWORD target) {
    ComPtr<IAudioSessionManager2> manager;
    Check(device->Activate(__uuidof(IAudioSessionManager2), CLSCTX_ALL, nullptr, &manager));
    ComPtr<IAudioSessionEnumerator> sessions;
    Check(manager->GetSessionEnumerator(&sessions));
    int count;
    Check(sessions->GetCount(&count));
    int matches = 0;
    for (int index = 0; index < count; index++) {
        ComPtr<IAudioSessionControl> session;
        ComPtr<IAudioSessionControl2> identity;
        Check(sessions->GetSession(index, &session));
        Check(session.As(&identity));
        DWORD pid;
        Check(identity->GetProcessId(&pid));
        if (pid != target) {
            continue;
        }
        ComPtr<ISimpleAudioVolume> master;
        ComPtr<IChannelAudioVolume> channels;
        Check(session.As(&master));
        Check(session.As(&channels));
        PrintSession(device, identity.Get(), master.Get(), channels.Get(), "inspect");
        matches++;
    }
    return matches;
}

int Run(const std::string &action, DWORD target) {
    ComPtr<IMMDeviceEnumerator> enumerator;
    Check(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
        __uuidof(IMMDeviceEnumerator), &enumerator));
    ComPtr<IMMDeviceCollection> devices;
    Check(enumerator->EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, &devices));
    UINT count;
    Check(devices->GetCount(&count));
    int processed = 0;
    for (UINT index = 0; index < count; index++) {
        ComPtr<IMMDevice> device;
        Check(devices->Item(index, &device));
        if (action == "endpoint-snapshot") {
            EndpointSnapshot(device.Get());
            processed++;
        } else if (action == "inspect") {
            processed += Inspect(device.Get(), target);
        } else {
            DefaultSession(device.Get(), action);
            processed++;
        }
    }
    return processed ? 0 : 2;
}
}

int main(int argc, char **argv) {
    try {
        if (argc < 2) {
            throw std::runtime_error("Use: seed-default | probe-default | reset-default | endpoint-snapshot | inspect PID");
        }
        std::string action = argv[1];
        if (action != "seed-default" && action != "probe-default" && action != "reset-default" &&
            action != "endpoint-snapshot" && action != "inspect") {
            throw std::runtime_error("Unknown audio action.");
        }
        if (argc != (action == "inspect" ? 3 : 2)) {
            throw std::runtime_error("Invalid audio arguments.");
        }
        DWORD target = 0;
        if (action == "inspect") {
            std::string digits = argv[2];
            if (digits.empty() || !std::all_of(digits.begin(), digits.end(),
                [](char digit) { return digit >= '0' && digit <= '9'; })) {
                throw std::runtime_error("Specify a positive process ID.");
            }
            size_t consumed = 0;
            unsigned long parsed = std::stoul(argv[2], &consumed);
            if (!parsed || consumed != std::string(argv[2]).size()) {
                throw std::runtime_error("Specify a positive process ID.");
            }
            target = parsed;
        }
        Check(CoInitializeEx(nullptr, COINIT_MULTITHREADED));
        int result = Run(action, target);
        CoUninitialize();
        return result;
    } catch (const std::exception &error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
