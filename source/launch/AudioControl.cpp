// Seed a silent application session, or inspect and mute sessions for one PID.
#include <windows.h>
#include <audioclient.h>
#include <audiopolicy.h>
#include <mmdeviceapi.h>
#include <wrl/client.h>
#include <cstdio>
#include <stdexcept>
#include <string>

using Microsoft::WRL::ComPtr;

void Check(HRESULT result) {
    if (FAILED(result)) {
        throw std::runtime_error("Audio API failed: " + std::to_string(result));
    }
}

// Do not submit audible samples. Store zero volume for this executable's default session.
void Seed(IMMDevice *device) {
    ComPtr<IAudioClient> client;
    Check(device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, &client));
    WAVEFORMATEX *format = nullptr;
    Check(client->GetMixFormat(&format));
    HRESULT initialized = client->Initialize(AUDCLNT_SHAREMODE_SHARED, 0, 1000000, 0, format, nullptr);
    CoTaskMemFree(format);
    Check(initialized);
    ComPtr<ISimpleAudioVolume> volume;
    Check(client->GetService(__uuidof(ISimpleAudioVolume), &volume));
    float level;
    BOOL muted;
    Check(volume->GetMasterVolume(&level));
    Check(volume->GetMute(&muted));
    std::printf("{\"pid\":%lu,\"initialVolume\":%.6f,\"initialMuted\":%s}\n",
        GetCurrentProcessId(), level, muted ? "true" : "false");
    Check(volume->SetMasterVolume(0.0f, nullptr));
    Check(volume->SetMute(TRUE, nullptr));
    Check(client->Start());
    Sleep(200);
    Check(client->Stop());
}

int Sessions(IMMDevice *device, DWORD target, bool mute) {
    ComPtr<IAudioSessionManager2> manager;
    Check(device->Activate(__uuidof(IAudioSessionManager2), CLSCTX_ALL, nullptr, &manager));
    ComPtr<IAudioSessionEnumerator> sessions;
    Check(manager->GetSessionEnumerator(&sessions));
    int count;
    Check(sessions->GetCount(&count));
    int matches = 0;
    for (int index = 0; index < count; index++) {
        ComPtr<IAudioSessionControl> control;
        Check(sessions->GetSession(index, &control));
        ComPtr<IAudioSessionControl2> identity;
        Check(control.As(&identity));
        DWORD process;
        Check(identity->GetProcessId(&process));
        if (process != target) {
            continue;
        }
        ComPtr<ISimpleAudioVolume> volume;
        Check(control.As(&volume));
        if (mute) {
            Check(volume->SetMasterVolume(0.0f, nullptr));
            Check(volume->SetMute(TRUE, nullptr));
        }
        float level;
        BOOL muted;
        Check(volume->GetMasterVolume(&level));
        Check(volume->GetMute(&muted));
        std::printf("{\"pid\":%lu,\"volume\":%.6f,\"muted\":%s}\n",
            process, level, muted ? "true" : "false");
        matches++;
    }
    return matches;
}

int main(int argc, char **argv) {
    try {
        if (argc < 2) {
            throw std::runtime_error("Use: AudioControl seed | inspect PID | mute PID");
        }
        std::string action = argv[1];
        if (action != "seed" && action != "inspect" && action != "mute") {
            throw std::runtime_error("Unknown audio action.");
        }
        if (action != "seed" && argc != 3) {
            throw std::runtime_error("Specify a process ID.");
        }
        DWORD target = action == "seed" ? 0 : std::stoul(argv[2]);
        Check(CoInitializeEx(nullptr, COINIT_MULTITHREADED));
        ComPtr<IMMDeviceEnumerator> enumerator;
        Check(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
            __uuidof(IMMDeviceEnumerator), &enumerator));
        ComPtr<IMMDeviceCollection> devices;
        Check(enumerator->EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, &devices));
        UINT count;
        Check(devices->GetCount(&count));
        int matches = 0;
        for (UINT index = 0; index < count; index++) {
            ComPtr<IMMDevice> device;
            Check(devices->Item(index, &device));
            if (action == "seed") {
                Seed(device.Get());
                matches++;
            } else {
                matches += Sessions(device.Get(), target, action == "mute");
            }
        }
        return matches > 0 ? 0 : 2;
    } catch (const std::exception &error) {
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
