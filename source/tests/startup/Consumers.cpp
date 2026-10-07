#include "Consumers.h"
#include "../activation/Harness.h"
#include <cstring>
#include <memory>
#include <vector>
#include <algorithm>

using Microsoft::WRL::ComPtr;
using namespace activation_test;
namespace {
struct Chain {
    ComPtr<IMMDeviceEnumerator> enumerator;
    ComPtr<IMMDevice> device;
    ComPtr<IAudioClient> client;
    ComPtr<IAudioRenderClient> render;
    ComPtr<IAudioSessionControl> session;
    DWORD generation = 0;
};
struct Held {
    std::vector<Chain> chains;
    std::vector<std::pair<ComPtr<IDirectSoundBuffer>, DWORD>> buffers;
    ComPtr<IMMDeviceEnumerator> notifications;
    ComPtr<IMMNotificationClient> endpointCallback;
    IAudioSessionEvents* sessionCallback = nullptr;
    std::shared_ptr<bool> callbackDestroyed;
    HANDLE event = nullptr;
};
Held* held;
void Good(HRESULT result) { if (FAILED(result)) StopOwned(result, Stage::Error); }
void Submit(IAudioRenderClient* render, DWORD generation, DWORD flags = 0) {
    BYTE* memory = nullptr;
    Good(render->GetBuffer(8, &memory));
    std::memset(memory, 0x3f, 64);
    Good(render->ReleaseBuffer(8, flags));
    const auto& generations = MemoryState().generations;
    const auto found = std::find_if(generations.begin(), generations.end(), [=](const auto& item) { return item->id == generation; });
    CheckOwned(found != generations.end());
    StartupEvent(Stage::RenderOutput, Api::Com, generation, (*found)->render->packets.back().silent, nullptr);
}
Chain CreateChain() {
    auto& state = MemoryState();
    Chain chain;
    Good(OwnedCoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
         __uuidof(IMMDeviceEnumerator), reinterpret_cast<void**>(chain.enumerator.GetAddressOf())));
    Good(chain.enumerator->GetDefaultAudioEndpoint(eRender, eConsole, &chain.device));
    Good(chain.device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr,
         reinterpret_cast<void**>(chain.client.GetAddressOf())));
    chain.generation = state.generations.back()->id;
    WAVEFORMATEX* format = nullptr;
    Good(chain.client->GetMixFormat(&format));
    const HRESULT initialized = chain.client->Initialize(AUDCLNT_SHAREMODE_SHARED,
        AUDCLNT_STREAMFLAGS_EVENTCALLBACK | AUDCLNT_STREAMFLAGS_NOPERSIST, 250000, 0, format, nullptr);
    CoTaskMemFree(format);
    Good(initialized);
    Good(chain.client->SetEventHandle(held->event));
    UINT32 count = 0;
    Good(chain.client->GetBufferSize(&count));
    CheckOwned(count == 8);
    Good(chain.client->GetService(__uuidof(IAudioRenderClient), reinterpret_cast<void**>(chain.render.GetAddressOf())));
    Publish(state, chain.render.Get(), "render", chain.generation);
    StartupEvent(Stage::RenderPublish, Api::Com, chain.generation, IsRaw(chain.render.Get()), nullptr);
    ComPtr<IAudioRenderClient> repeated;
    Good(chain.client->GetService(__uuidof(IAudioRenderClient), reinterpret_cast<void**>(repeated.GetAddressOf())));
    CheckOwned(SameIdentity(chain.render.Get(), repeated.Get()));
    Good(chain.client->GetService(__uuidof(IAudioSessionControl), reinterpret_cast<void**>(chain.session.GetAddressOf())));
    if (state.sharedIdentity) CheckOwned(SameIdentity(chain.client.Get(), chain.render.Get()) && SameIdentity(chain.render.Get(), chain.session.Get()));
    else CheckOwned(!SameIdentity(chain.client.Get(), chain.render.Get()) && !SameIdentity(chain.render.Get(), chain.session.Get()));
    Submit(chain.render.Get(), chain.generation, AUDCLNT_BUFFERFLAGS_SILENT);
    Good(chain.client->Start());
    Submit(chain.render.Get(), chain.generation);
    return chain;
}
void TemporaryChain() {
    auto chain = CreateChain();
    Good(chain.client->Stop());
}
void MakeBuffers() {
    auto& state = MemoryState();
    ComPtr<IDirectSound8> device;
    Good(OwnedDirectSoundCreate8(nullptr, &device, nullptr));
    Good(device->SetCooperativeLevel(nullptr, DSSCL_PRIORITY));
    for (unsigned index = 0; index < 3; ++index) {
        WAVEFORMATEX format{WAVE_FORMAT_PCM, 2, 48000, 192000, 4, 16, 0};
        DSBUFFERDESC description{};
        description.dwSize = sizeof(description);
        description.dwFlags = 0x80e8;
        description.dwBufferBytes = 128;
        description.lpwfxFormat = &format;
        ComPtr<IDirectSoundBuffer> buffer;
        const HRESULT result = device->CreateSoundBuffer(&description, &buffer, nullptr);
        if (FAILED(result)) {
            StartupState()->unsafeBranch = 1;
            StartupEvent(Stage::NativeFailure, Api::Sound, 0, result, nullptr);
            StopOwned(result, Stage::Error);
        }
        const auto generation = state.generations.back();
        Publish(state, buffer.Get(), "buffer", generation->id);
        StartupEvent(Stage::BufferPublish, Api::Sound, generation->id, IsRaw(buffer.Get()), nullptr);
        ComPtr<IDirectSoundBuffer8> extended;
        Good(buffer->QueryInterface(IID_IDirectSoundBuffer8, reinterpret_cast<void**>(extended.GetAddressOf())));
        CheckOwned(SameIdentity(buffer.Get(), extended.Get()));
        Good(buffer->Play(0, 0, DSBPLAY_LOOPING));
        StartupEvent(Stage::SoundOutput, Api::Sound, generation->id, generation->sound->outputs.back(), nullptr);
        LPVOID first = nullptr, second = nullptr;
        DWORD firstBytes = 0, secondBytes = 0;
        Good(buffer->Lock(112, 32, &first, &firstBytes, &second, &secondBytes, 0));
        std::memset(first, 0x35, firstBytes);
        std::memset(second, 0x35, secondBytes);
        Good(buffer->Unlock(first, firstBytes, second, secondBytes));
        generation->sound->lost = true;
        Good(extended->Restore());
        Good(buffer->Play(0, 0, DSBPLAY_LOOPING));
        StartupEvent(Stage::SoundOutput, Api::Sound, generation->id, generation->sound->outputs.back(), nullptr);
        Good(buffer->Stop());
        held->buffers.emplace_back(buffer, generation->id);
    }
}
}
void CheckOwned(bool condition, HRESULT failure) { if (!condition) StopOwned(failure, Stage::Error); }
DWORD ConsumeFamilies() {
    held = new Held;
    held->event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    CheckOwned(held->event != nullptr);
    auto& state = MemoryState();
    held->chains.push_back(CreateChain());
    held->chains.push_back(CreateChain());
    ComPtr<IMMDeviceEnumerator> repeated;
    Good(OwnedCoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
        __uuidof(IMMDeviceEnumerator), reinterpret_cast<void**>(repeated.GetAddressOf())));
    CheckOwned(SameIdentity(repeated.Get(), held->chains.front().enumerator.Get()));
    held->notifications = repeated;
    held->endpointCallback = Make<IMMNotificationClient, EndpointCallback>([] {
        try { InterlockedIncrement(&StartupState()->callbacks); StartupEvent(Stage::Callback, Api::Com, 0, 0, nullptr); TemporaryChain(); }
        catch (...) { StopOwned(E_UNEXPECTED, Stage::Error); }
    });
    Good(held->notifications->RegisterEndpointNotificationCallback(held->endpointCallback.Get()));
    CheckOwned(state.lastEndpointCallback == held->endpointCallback.Get());
    state.callbackExpectedThread = GetCurrentThreadId();
    state.NotifyEndpoint();
    held->callbackDestroyed = std::make_shared<bool>(false);
    auto callback = Make<IAudioSessionEvents, SessionCallback>([] {
        try { InterlockedIncrement(&StartupState()->callbacks); StartupEvent(Stage::Callback, Api::Com, 0, 0, nullptr); TemporaryChain(); }
        catch (...) { StopOwned(E_UNEXPECTED, Stage::Error); }
    }, held->callbackDestroyed, held->chains.front().client);
    held->sessionCallback = callback.Get();
    state.sessionRegisterResult = S_FALSE;
    CheckOwned(held->chains.front().session->RegisterAudioSessionNotification(callback.Get()) == S_FALSE);
    CheckOwned(held->chains.front().session->RegisterAudioSessionNotification(callback.Get()) == S_FALSE);
    CheckOwned(state.lastSessionCallback == callback.Get());
    callback.Reset();
    state.NotifySession(state.generations.front());
    CheckOwned(state.callbackThread == state.callbackExpectedThread && !*held->callbackDestroyed);
    StartupState()->callbackThread = static_cast<LONG>(state.callbackThread);
    MakeBuffers();
    // Service and callback references remain live after their parent interfaces are released.
    for (auto& chain : held->chains) {
        Good(chain.client->Stop());
        chain.client.Reset(); chain.device.Reset(); chain.enumerator.Reset();
    }
    constexpr GUID decoderClass = {0x62ce7e72, 0x4c71, 0x4d20, {0xb1, 0x5d, 0x45, 0x28, 0x31, 0xa8, 0x7d, 0x9d}};
    ComPtr<IUnknown> nonAudio;
    Good(OwnedCoCreateInstance(decoderClass, nullptr, CLSCTX_ALL, IID_IUnknown,
         reinterpret_cast<void**>(nonAudio.GetAddressOf())));
    CheckOwned(IsRaw(nonAudio.Get()));
    SnapshotMemory();
    return 0;
}
DWORD ConsumeRetained() {
    CheckOwned(held != nullptr && !*held->callbackDestroyed);
    for (const auto& chain : held->chains) Submit(chain.render.Get(), chain.generation);
    for (const auto& item : held->buffers) {
        Good(item.first->Play(0, 0, DSBPLAY_LOOPING));
        const auto& generations = MemoryState().generations;
        const auto found = std::find_if(generations.begin(), generations.end(), [&](const auto& generation) { return generation->id == item.second; });
        CheckOwned(found != generations.end());
        StartupEvent(Stage::SoundOutput, Api::Sound, item.second, (*found)->sound->outputs.back(), nullptr);
        Good(item.first->Stop());
    }
    SnapshotMemory();
    return 0;
}
void ReleaseFamilies() {
    if (!held) return;
    Good(held->notifications->UnregisterEndpointNotificationCallback(held->endpointCallback.Get()));
    held->endpointCallback.Reset(); held->notifications.Reset();
    Good(held->chains.front().session->UnregisterAudioSessionNotification(held->sessionCallback));
    Good(held->chains.front().session->UnregisterAudioSessionNotification(held->sessionCallback));
    CheckOwned(*held->callbackDestroyed && MemoryState().generations.front()->sessionRegisters == 2
        && MemoryState().generations.front()->sessionUnregisters == 2);
    held->buffers.clear(); held->chains.clear();
    CheckOwned(CloseHandle(held->event) != FALSE);
    delete held;
    held = nullptr;
    StartupEvent(Stage::ReferencesReleased, Api::None, 0, 1, nullptr);
    SnapshotMemory();
}
void SnapshotMemory() {
    auto* trace = StartupState();
    const auto& state = MemoryState();
    trace->rawPublications = static_cast<LONG>(state.rawPublications);
    trace->generations = static_cast<LONG>(state.generations.size());
    trace->renderPackets = trace->silentRenderPackets = trace->soundPlays = trace->silentSoundPlays = 0;
    for (const auto& generation : state.generations) {
        if (generation->sound) {
            for (const bool silent : generation->sound->outputs) {
                ++trace->soundPlays;
                if (silent) ++trace->silentSoundPlays;
            }
        } else {
            for (const auto& packet : generation->render->packets) {
                ++trace->renderPackets;
                if (packet.silent) ++trace->silentRenderPackets;
            }
        }
    }
}
