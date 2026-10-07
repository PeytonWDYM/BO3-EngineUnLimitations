#include "Harness.h"
#include <cstring>

namespace activation_test {
void OtherScenarios(fixture::Report& report) {
    Run(report, "directsound-base-to-buffer8-before-first-play", [](fixture::Scenario& test, State& state, Harness& harness) {
        ComPtr<IDirectSound8> device;
        Ok(harness.CreateDirectSound(nullptr, &device, nullptr));
        Ok(device->SetCooperativeLevel(nullptr, DSSCL_PRIORITY));
        WAVEFORMATEX format{};
        const auto description = Description(format);
        ComPtr<IDirectSoundBuffer> buffer;
        Ok(NativeBufferCreate(device.Get(), description, &buffer, state));
        auto generation = state.generations.back();
        Publish(state, buffer.Get(), "buffer", generation->id);
        const bool prepared = fixture::IsSilent(*generation->sound);
        Ok(buffer->Play(0, 0, DSBPLAY_LOOPING));
        LPVOID first = nullptr, second = nullptr;
        DWORD firstBytes = 0, secondBytes = 0;
        Ok(buffer->Lock(112, 32, &first, &firstBytes, &second, &secondBytes, 0));
        memset(first, 0x35, firstBytes); memset(second, 0x35, secondBytes);
        Ok(buffer->Unlock(first, firstBytes, second, secondBytes));
        test.Boolean("clearedBeforePublication", prepared);
        test.Boolean("firstPlaySilent", generation->sound->outputs.front());
        test.String("submittedHex", fixture::Hex(generation->sound->memory));
        Require(prepared && generation->sound->outputs.front() && fixture::IsSilent(*generation->sound), "Raw DirectSound output reached Play");
    });
    Run(report, "factory-activate-initialize-service-errors", [](fixture::Scenario& test, State& state, Harness& harness) {
        state.rootError = E_ACCESSDENIED;
        void* output = reinterpret_cast<void*>(1);
        const HRESULT root = harness.CreateCom(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), &output);
        Require(root == E_ACCESSDENIED && !output, "Root failure changed");
        state.rootError = S_OK;
        ComPtr<IMMDeviceEnumerator> enumerator;
        Ok(harness.CreateCom(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), reinterpret_cast<void**>(enumerator.GetAddressOf())));
        ComPtr<IMMDevice> device;
        Ok(enumerator->GetDefaultAudioEndpoint(eRender, eConsole, &device));
        state.activateError = AUDCLNT_E_DEVICE_INVALIDATED;
        output = reinterpret_cast<void*>(1);
        const HRESULT activate = device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, &output);
        Require(activate == state.activateError && !output, "Activate failure changed");
        state.activateError = S_OK;
        ComPtr<IAudioClient> client;
        Ok(device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, reinterpret_cast<void**>(client.GetAddressOf())));
        state.initializeError = AUDCLNT_E_UNSUPPORTED_FORMAT;
        WAVEFORMATEX format{WAVE_FORMAT_IEEE_FLOAT, 2, 48000, 384000, 8, 32, 0};
        const HRESULT initialize = client->Initialize(AUDCLNT_SHAREMODE_SHARED, 0xc0000, 250000, 0, &format, nullptr);
        Require(initialize == state.initializeError, "Initialize failure changed");
        state.initializeError = S_OK;
        Initialize(client.Get());
        state.serviceError = AUDCLNT_E_SERVICE_NOT_RUNNING;
        output = reinterpret_cast<void*>(1);
        const HRESULT service = client->GetService(__uuidof(IAudioRenderClient), &output);
        Require(service == state.serviceError && !output, "GetService failure changed");
        test.String("rootHRESULT", fixture::Hresult(root));
        test.String("activateHRESULT", fixture::Hresult(activate));
        test.String("initializeHRESULT", fixture::Hresult(initialize));
        test.String("serviceHRESULT", fixture::Hresult(service));
    });
    Run(report, "directsound-failure-stops-before-native-null-release", [](fixture::Scenario& test, State& state, Harness& harness) {
        ComPtr<IDirectSound8> device;
        Ok(harness.CreateDirectSound(nullptr, &device, nullptr));
        unsigned preserved = 0;
        for (unsigned index = 0; index < 5; ++index) {
            WAVEFORMATEX format{};
            auto description = Description(format);
            state.bufferError = index == 0 ? DSERR_OUTOFMEMORY : S_OK;
            state.buffer8 = index != 1;
            state.clearError = index == 2 ? DSERR_BUFFERLOST : S_OK;
            if (index == 3) description.dwFlags |= DSBCAPS_CTRLFX;
            if (index == 4) description.dwFlags |= DSBCAPS_PRIMARYBUFFER;
            const HRESULT expected = index == 0 ? DSERR_OUTOFMEMORY : index == 1 ? E_NOINTERFACE : index == 2 ? DSERR_BUFFERLOST : DSERR_CONTROLUNAVAIL;
            ComPtr<IDirectSoundBuffer> buffer;
            try { NativeBufferCreate(device.Get(), description, &buffer, state); }
            catch (const Stopped& stopped) { if (stopped.code == expected && !buffer) ++preserved; }
        }
        test.Number("abortHRESULTsPreserved", preserved);
        test.Boolean("unsafeBranchReached", state.unsafeBranchReached);
        Require(preserved == 5 && state.aborts == 5 && !state.unsafeBranchReached, "Failure returned into the native-style null branch");
    });
    Run(report, "unsupported-interfaces-duplicates-and-non-audio-com", [](fixture::Scenario& test, State& state, Harness& harness) {
        auto chain = CreateChain(harness, state);
        void* escape = nullptr;
        const HRESULT qi = chain.client->QueryInterface(fixture::EscapeId, &escape);
        if (SUCCEEDED(qi)) static_cast<IUnknown*>(escape)->Release();
        escape = nullptr;
        const HRESULT service = chain.client->GetService(__uuidof(IAudioStreamVolume), &escape);
        if (SUCCEEDED(service)) static_cast<IUnknown*>(escape)->Release();
        escape = nullptr;
        const HRESULT alternate = chain.device->Activate(IID_IDirectSound8, CLSCTX_ALL, nullptr, &escape);
        if (SUCCEEDED(alternate)) static_cast<IUnknown*>(escape)->Release();
        ComPtr<IDirectSound8> device;
        Ok(harness.CreateDirectSound(nullptr, &device, nullptr));
        WAVEFORMATEX format{};
        const auto description = Description(format);
        ComPtr<IDirectSoundBuffer> buffer, duplicate;
        Ok(NativeBufferCreate(device.Get(), description, &buffer, state));
        bool duplicateStopped = false;
        try { device->DuplicateSoundBuffer(buffer.Get(), &duplicate); }
        catch (const Stopped& stopped) { duplicateStopped = stopped.code == DSERR_UNSUPPORTED && !duplicate; }
        constexpr GUID decoderClass = {0x62ce7e72, 0x4c71, 0x4d20, {0xb1, 0x5d, 0x45, 0x28, 0x31, 0xa8, 0x7d, 0x9d}};
        ComPtr<IUnknown> nonAudio;
        Ok(harness.CreateCom(decoderClass, nullptr, CLSCTX_ALL, IID_IUnknown, reinterpret_cast<void**>(nonAudio.GetAddressOf())));
        test.String("unknownQI", fixture::Hresult(qi));
        test.String("unknownService", fixture::Hresult(service));
        test.String("alternateActivation", fixture::Hresult(alternate));
        test.Boolean("duplicateStopped", duplicateStopped);
        test.Boolean("nonAudioObjectUnchanged", IsRaw(nonAudio.Get()));
        Require(qi == E_NOINTERFACE && service == E_NOINTERFACE && alternate == E_NOINTERFACE && duplicateStopped && IsRaw(nonAudio.Get()), "Unsupported output interface escaped or non-audio creation changed");
    });
    Run(report, "adapter-allocation-failure-no-fallback", [](fixture::Scenario& test, State& state, Harness& harness) {
        state.failAdapterAllocation = true;
        void* output = nullptr;
        const HRESULT result = harness.CreateCom(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), &output);
        FailNextAllocation = false;
        if (SUCCEEDED(result)) static_cast<IUnknown*>(output)->Release();
        test.String("allocationHRESULT", fixture::Hresult(result));
        test.Boolean("noPublishedOutput", output == nullptr);
        test.Boolean("noLiveAdapter", harness.CanUnload());
        Require(result == E_OUTOFMEMORY && !output && harness.CanUnload(), "Allocation failure exposed fallback or retained an adapter");
    });
    Run(report, "buffer-recreation-restore-and-unload-order", [](fixture::Scenario& test, State& state, Harness& harness) {
        ComPtr<IDirectSound8> device;
        Ok(harness.CreateDirectSound(nullptr, &device, nullptr));
        bool silent = true;
        bool identity = true;
        for (unsigned index = 0; index < 5; ++index) {
            WAVEFORMATEX format{};
            const auto description = Description(format);
            ComPtr<IDirectSoundBuffer> buffer;
            Ok(NativeBufferCreate(device.Get(), description, &buffer, state));
            auto generation = state.generations.back();
            Publish(state, buffer.Get(), "buffer", generation->id);
            ComPtr<IDirectSoundBuffer8> extended;
            Ok(buffer->QueryInterface(IID_IDirectSoundBuffer8, reinterpret_cast<void**>(extended.GetAddressOf())));
            identity = identity && SameIdentity(buffer.Get(), extended.Get());
            generation->sound->lost = true;
            Ok(extended->Restore());
            Ok(buffer->Play(0, 0, DSBPLAY_LOOPING));
            silent = silent && generation->sound->outputs.back();
            Ok(buffer->Stop());
        }
        const bool liveBlocked = !harness.CanUnload();
        device.Reset();
        test.Boolean("allRestoredBuffersSilent", silent);
        test.Boolean("baseAndExtendedIdentity", identity);
        test.Boolean("liveDeviceBlocksUnload", liveBlocked);
        test.Boolean("allAdaptersReleased", harness.CanUnload());
        Require(silent && identity && liveBlocked && harness.CanUnload(), "Buffer recreation, Restore, or teardown failed");
    });
}
}
