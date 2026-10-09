#include "Consumer.h"
#include "MemoryCallbacks.h"
#include <intrin.h>

using Microsoft::WRL::ComPtr;
using driver_probe::ValidateFormat;
using driver_probe::FillSilence;
namespace {
struct Client {
    ComPtr<IMMDeviceEnumerator> root;
    ComPtr<IMMDevice> device;
    ComPtr<IAudioClient> client;
    ComPtr<IAudioRenderClient> render;
    ComPtr<IAudioSessionControl> session;
    DWORD generation = 0;
    driver_probe::SilenceFormat silence{};
};
struct Held {
    std::vector<Client> clients;
    std::vector<ComPtr<IDirectSoundBuffer8>> buffers;
    ComPtr<IMMNotificationClient> endpoint;
    ComPtr<IAudioSessionEvents> session;
    ComPtr<IMMDeviceEnumerator> notifications;
    std::shared_ptr<bool> callbackDestroyed;
    std::shared_ptr<driver_probe::CallbackCounts> callbackCounts;
    HANDLE event = nullptr;
    HWND window = nullptr;
};
Held* held;
void Handshake() {
    // A missing SDK hook must not turn memory mode into a physical factory test.
    ConsumerCheck(SdkTrace()->hooksReady == 1 && SdkTrace()->runtimeReady == 1);
}
Client MakeClient(DWORD generation) {
    Handshake();
    Client result;
    result.generation = generation;
    SdkRecord(Stage::FactoryRequested, Api::Com, generation, 0, &__uuidof(MMDeviceEnumerator), &__uuidof(IMMDeviceEnumerator));
    ConsumerGood(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
        __uuidof(IMMDeviceEnumerator), reinterpret_cast<void**>(result.root.GetAddressOf())));
    ConsumerGood(result.root->GetDefaultAudioEndpoint(eRender, eConsole, &result.device));
    ConsumerGood(result.device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr,
        reinterpret_cast<void**>(result.client.GetAddressOf())));
    WAVEFORMATEX* mix = nullptr;
    ConsumerGood(result.client->GetMixFormat(&mix));
    driver_probe::SilenceFormat silence{};
    try { silence = ValidateFormat(*mix); }
    catch (...) { CoTaskMemFree(mix); ConsumerStop(AUDCLNT_E_UNSUPPORTED_FORMAT); }
    result.silence = silence;
    SdkRecord(Stage::Format, Api::Com, generation, mix->wBitsPerSample, nullptr, nullptr);
    const HRESULT initialized = result.client->Initialize(AUDCLNT_SHAREMODE_SHARED,
        AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_NOPERSIST, 250000, 0, mix, nullptr);
    CoTaskMemFree(mix);
    ConsumerGood(initialized);
    ConsumerGood(result.client->SetEventHandle(held->event));
    UINT32 frames = 0;
    ConsumerGood(result.client->GetBufferSize(&frames));
    ConsumerCheck(frames > 0 && static_cast<ULONGLONG>(frames) * silence.alignment <= SIZE_MAX);
    ConsumerGood(result.client->GetService(__uuidof(IAudioRenderClient), reinterpret_cast<void**>(result.render.GetAddressOf())));
    SdkObserve(result.render.Get(), Api::Com, generation);
    ComPtr<IAudioRenderClient> repeated;
    ConsumerGood(result.client->GetService(__uuidof(IAudioRenderClient), reinterpret_cast<void**>(repeated.GetAddressOf())));
    ComPtr<IUnknown> firstIdentity, secondIdentity;
    ConsumerGood(result.render.As(&firstIdentity)); ConsumerGood(repeated.As(&secondIdentity));
    ConsumerCheck(firstIdentity.Get() == secondIdentity.Get());
    ConsumerGood(result.client->GetService(__uuidof(IAudioSessionControl), reinterpret_cast<void**>(result.session.GetAddressOf())));
    BYTE* memory = nullptr;
    ConsumerGood(result.render->GetBuffer(frames, &memory));
    FillSilence(memory, static_cast<size_t>(frames) * silence.alignment, silence);
    ConsumerGood(result.render->ReleaseBuffer(frames, AUDCLNT_BUFFERFLAGS_SILENT));
    InterlockedIncrement(&SdkTrace()->silentReleases);
    SdkRecord(Stage::FirstSilent, Api::Com, generation, AUDCLNT_BUFFERFLAGS_SILENT, nullptr, nullptr);
    ConsumerGood(result.client->Start());
    SdkRecord(Stage::Start, Api::Com, generation, S_OK, nullptr, nullptr);
    ConsumerGood(result.client->Stop());
    return result;
}
void Callback() noexcept {
    try {
        InterlockedIncrement(&SdkTrace()->callbackCalls);
        SdkTrace()->callbackTid = static_cast<LONG>(GetCurrentThreadId());
        SdkRecord(Stage::Callback, Api::Com, 0, S_OK, nullptr, nullptr);
        if (SdkTrace()->mode == Mode::Memory) {
            auto temporary = MakeClient(2 + static_cast<DWORD>(SdkTrace()->callbackCalls));
        }
    } catch (...) { ConsumerStop(E_UNEXPECTED); }
}
void ClearRing(IDirectSoundBuffer8* buffer, DWORD generation, bool full) {
    // This complete caller clear protects first playback even when the helper did not wrap the buffer.
    ConsumerGood(buffer->Stop());
    DWORD formatBytes = 0;
    ConsumerGood(buffer->GetFormat(nullptr, 0, &formatBytes));
    ConsumerCheck(formatBytes >= sizeof(WAVEFORMATEX) && formatBytes <= 4096);
    std::vector<BYTE> formatMemory(formatBytes);
    DWORD read = 0;
    ConsumerGood(buffer->GetFormat(reinterpret_cast<WAVEFORMATEX*>(formatMemory.data()), formatBytes, &read));
    ConsumerCheck(read == formatBytes);
    const auto& format = *reinterpret_cast<WAVEFORMATEX*>(formatMemory.data());
    ConsumerCheck(format.wFormatTag != WAVE_FORMAT_EXTENSIBLE || formatBytes >= sizeof(WAVEFORMATEXTENSIBLE));
    driver_probe::SilenceFormat silence{};
    try { silence = ValidateFormat(format); }
    catch (...) { ConsumerStop(DSERR_BADFORMAT); }
    DSBCAPS caps{}; caps.dwSize = sizeof(caps);
    ConsumerGood(buffer->GetCaps(&caps));
    ConsumerCheck(caps.dwBufferBytes >= 4u * silence.alignment && caps.dwBufferBytes % silence.alignment == 0);
    LPVOID first = nullptr, second = nullptr;
    DWORD firstBytes = 0, secondBytes = 0;
    const DWORD count = full ? caps.dwBufferBytes : 4u * silence.alignment;
    const DWORD offset = full ? 0 : caps.dwBufferBytes - 2u * silence.alignment;
    ConsumerGood(buffer->Lock(offset, count, &first, &firstBytes, &second, &secondBytes, 0));
    ConsumerCheck(static_cast<ULONGLONG>(firstBytes) + secondBytes == count
        && firstBytes % silence.alignment == 0 && secondBytes % silence.alignment == 0);
    FillSilence(first, firstBytes, silence); FillSilence(second, secondBytes, silence);
    ConsumerGood(buffer->Unlock(first, firstBytes, second, secondBytes));
    if (full) InterlockedIncrement(&SdkTrace()->fullClears);
    SdkRecord(full ? Stage::FullClear : Stage::SplitClear, Api::Sound, generation, static_cast<LONG>(count), nullptr, nullptr);
}
void Sound(DWORD generation) {
    Handshake();
    ComPtr<IDirectSound8> root;
    SdkRecord(Stage::FactoryRequested, Api::Sound, generation, 0, nullptr, &IID_IDirectSound8);
    ConsumerGood(DirectSoundCreate8(nullptr, &root, nullptr));
    ConsumerGood(root->SetCooperativeLevel(held->window, DSSCL_PRIORITY));
    auto format = driver_probe::Wave(WAVE_FORMAT_PCM, 16);
    DSBUFFERDESC description{}; description.dwSize = sizeof(description); description.dwFlags = 0x80e8;
    description.dwBufferBytes = SdkTrace()->mode == Mode::Memory ? 128 : format.nAvgBytesPerSec / 20;
    description.lpwfxFormat = &format;
    ComPtr<IDirectSoundBuffer> base;
    ConsumerGood(root->CreateSoundBuffer(&description, &base, nullptr));
    SdkObserve(base.Get(), Api::Sound, generation);
    ComPtr<IDirectSoundBuffer8> extended;
    ConsumerGood(base->QueryInterface(IID_IDirectSoundBuffer8, reinterpret_cast<void**>(extended.GetAddressOf())));
    ComPtr<IUnknown> firstIdentity, secondIdentity;
    ConsumerGood(base.As(&firstIdentity)); ConsumerGood(extended.As(&secondIdentity));
    ConsumerCheck(firstIdentity.Get() == secondIdentity.Get());
    ClearRing(extended.Get(), generation, true);
    ConsumerGood(extended->Play(0, 0, DSBPLAY_LOOPING));
    InterlockedIncrement(&SdkTrace()->plays);
    SdkRecord(Stage::Play, Api::Sound, generation, S_OK, nullptr, nullptr);
    ConsumerGood(extended->Stop());
    ClearRing(extended.Get(), generation, false);
    held->buffers.push_back(extended);
}
}
[[noreturn]] void ConsumerStop(HRESULT code) {
    auto* trace = SdkTrace();
    trace->aborted = 1; trace->abortHresult = code;
    SdkRecord(Stage::Error, Api::None, 0, code, nullptr, nullptr);
    TerminateProcess(GetCurrentProcess(), kSdkStop); __fastfail(7);
}
void ConsumerCheck(bool condition, HRESULT code) { if (!condition) ConsumerStop(code); }
void ConsumerGood(HRESULT code) { if (FAILED(code)) ConsumerStop(code); }
void RunConsumers() {
    held = new Held;
    held->event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    ConsumerCheck(held->event != nullptr);
    held->window = CreateWindowExW(0, L"STATIC", L"Owned SDK silent consumer", WS_OVERLAPPED,
        0, 0, 1, 1, nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
    ConsumerCheck(held->window != nullptr && IsWindowVisible(held->window) == FALSE);
    held->clients.push_back(MakeClient(1)); held->clients.push_back(MakeClient(2));
    held->notifications = held->clients.front().root;
    held->callbackCounts = std::make_shared<driver_probe::CallbackCounts>();
    held->endpoint = SdkTrace()->mode == Mode::Memory ? MemoryEndpoint(held->callbackCounts, Callback)
        : driver_probe::EndpointCallback(held->callbackCounts);
    ConsumerGood(held->notifications->RegisterEndpointNotificationCallback(held->endpoint.Get()));
    if (SdkTrace()->mode == Mode::Memory) {
        held->callbackDestroyed = std::make_shared<bool>(false);
        held->session = MemorySession(held->callbackCounts, Callback, held->callbackDestroyed, held->clients.front().client);
    } else held->session = driver_probe::SessionCallback(held->callbackCounts);
    const HRESULT registered = held->clients.front().session->RegisterAudioSessionNotification(held->session.Get());
    ConsumerGood(registered);
    if (SdkTrace()->mode == Mode::Memory) {
        ConsumerCheck(registered == S_FALSE);
        ConsumerCheck(held->clients.front().session->RegisterAudioSessionNotification(held->session.Get()) == S_FALSE);
        SdkFireCallbacks();
        ConsumerCheck(SdkTrace()->callbackCalls == 3 && SdkTrace()->callbackTid == static_cast<LONG>(GetCurrentThreadId()));
    }
    SdkTrace()->callbackLive = static_cast<LONG>(held->callbackCounts->live.load());
    Sound(1); Sound(2);
    for (auto& client : held->clients) { client.root.Reset(); client.device.Reset(); client.client.Reset(); }
    ComPtr<IGlobalInterfaceTable> nonAudio;
    ConsumerGood(CoCreateInstance(CLSID_StdGlobalInterfaceTable, nullptr, CLSCTX_INPROC_SERVER,
        IID_IGlobalInterfaceTable, reinterpret_cast<void**>(nonAudio.GetAddressOf())));
    SdkRecord(Stage::NonAudio, Api::Com, 0, S_OK, &CLSID_StdGlobalInterfaceTable, &IID_IGlobalInterfaceTable);
    SdkSnapshot();
}
void RetainedConsumers() {
    ConsumerCheck(held && (SdkTrace()->mode != Mode::Memory || !*held->callbackDestroyed));
    for (auto& client : held->clients) {
        BYTE* memory = nullptr;
        ConsumerGood(client.render->GetBuffer(1, &memory));
        FillSilence(memory, client.silence.alignment, client.silence);
        ConsumerGood(client.render->ReleaseBuffer(1, AUDCLNT_BUFFERFLAGS_SILENT));
        InterlockedIncrement(&SdkTrace()->silentReleases);
    }
    for (size_t index = 0; index < held->buffers.size(); ++index) {
        ClearRing(held->buffers[index].Get(), static_cast<DWORD>(index + 1), true);
        ConsumerGood(held->buffers[index]->Play(0, 0, DSBPLAY_LOOPING));
        ConsumerGood(held->buffers[index]->Stop());
        InterlockedIncrement(&SdkTrace()->plays);
        SdkRecord(Stage::Play, Api::Sound, static_cast<DWORD>(index + 1), S_OK, nullptr, nullptr);
    }
    SdkSnapshot();
}
void ReleaseConsumers() {
    ConsumerGood(held->notifications->UnregisterEndpointNotificationCallback(held->endpoint.Get()));
    ConsumerGood(held->clients.front().session->UnregisterAudioSessionNotification(held->session.Get()));
    if (SdkTrace()->mode == Mode::Memory) ConsumerGood(held->clients.front().session->UnregisterAudioSessionNotification(held->session.Get()));
    held->session.Reset(); held->endpoint.Reset(); held->notifications.Reset();
    if (SdkTrace()->mode == Mode::Memory) ConsumerCheck(*held->callbackDestroyed);
    SdkTrace()->callbackLive = static_cast<LONG>(held->callbackCounts->live.load());
    ConsumerCheck(SdkTrace()->callbackLive == 0);
    held->clients.clear(); held->buffers.clear();
    ConsumerCheck(CloseHandle(held->event) != FALSE && DestroyWindow(held->window) != FALSE);
    delete held; held = nullptr;
    SdkTrace()->callbackLive = 0;
    SdkRecord(Stage::ReferencesReleased, Api::None, 0, S_OK, nullptr, nullptr);
    SdkSnapshot();
}
