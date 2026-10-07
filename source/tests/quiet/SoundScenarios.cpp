#include "Fixture.h"
#include <cstring>

namespace fixture {
namespace {
struct Regions { LPVOID first = nullptr; LPVOID second = nullptr; DWORD firstBytes = 0; DWORD secondBytes = 0; };
Regions Write(IDirectSoundBuffer8* caller, DWORD offset, DWORD bytes, DWORD flags = 0) {
    Regions regions;
    Ok(caller->Lock(offset, bytes, &regions.first, &regions.firstBytes, &regions.second, &regions.secondBytes, flags));
    memset(regions.first, 0x35, regions.firstBytes);
    if (regions.second) memset(regions.second, 0x6a, regions.secondBytes);
    return regions;
}
HRESULT Unlock(IDirectSoundBuffer8* caller, const Regions& regions) {
    return caller->Unlock(regions.first, regions.firstBytes, regions.second, regions.secondBytes);
}
void FormatScenario(Report& report, const char* name, WORD tag, WORD bits, WORD channels, bool extensible) {
    report.Run(name, [=](Scenario& test) {
        auto state = MakeSoundState(tag, bits, channels, extensible);
        auto sink = MakeSound(state);
        ComPtr<IDirectSoundBuffer8> caller;
        Ok(SoundBoundary(sink.Get(), &caller));
        Ok(caller->Play(0, 0, DSBPLAY_LOOPING));
        const bool firstSilent = state->outputs.back();
        const std::string firstHex = Hex(state->memory);
        const auto regions = Write(caller.Get(), 0, 0, DSBLOCK_ENTIREBUFFER);
        const bool duringWrite = IsSilent(*state);
        Ok(Unlock(caller.Get(), regions));
        test.Number("channels", channels);
        test.Number("bits", bits);
        test.Number("silenceByte", state->silence);
        test.String("firstOutputHex", firstHex);
        test.String("submittedOutputHex", Hex(state->memory));
        test.Boolean("firstPlaySilent", firstSilent);
        test.Boolean("silentDuringWrite", duringWrite);
        Require(firstSilent && duringWrite && IsSilent(*state), "DirectSound output contains caller samples");
    });
}
}
void SoundScenarios(Report& report) {
    FormatScenario(report, "directsound-pcm8-first-output", WAVE_FORMAT_PCM, 8, 1, false);
    FormatScenario(report, "directsound-pcm16-stereo-first-output", WAVE_FORMAT_PCM, 16, 2, false);
    FormatScenario(report, "directsound-float32-eight-channels", WAVE_FORMAT_IEEE_FLOAT, 32, 8, true);
    report.Run("directsound-split-lock-during-looping-play", [](Scenario& test) {
        auto state = MakeSoundState(WAVE_FORMAT_PCM, 16, 2);
        auto sink = MakeSound(state);
        ComPtr<IDirectSoundBuffer8> caller;
        Ok(SoundBoundary(sink.Get(), &caller));
        Ok(caller->Play(0, 0, DSBPLAY_LOOPING));
        const auto regions = Write(caller.Get(), 112, 32);
        const bool privatePointers = regions.first != state->first && regions.second != state->second;
        const bool beforeUnlock = IsSilent(*state);
        Ok(caller->Play(0, 0, DSBPLAY_LOOPING));
        const bool playingSilent = state->outputs.back();
        Ok(Unlock(caller.Get(), regions));
        Ok(caller->SetCurrentPosition(112));
        const auto cursorRegions = Write(caller.Get(), 0, 32, DSBLOCK_FROMWRITECURSOR);
        Ok(Unlock(caller.Get(), cursorRegions));
        LPVOID first = nullptr;
        DWORD bytes = 0;
        Ok(caller->Lock(112, 32, &first, &bytes, nullptr, nullptr, 0));
        memset(first, 0x62, bytes);
        Ok(caller->Unlock(first, bytes, nullptr, 0));
        test.Number("splitFirstBytes", regions.firstBytes);
        test.Number("splitSecondBytes", regions.secondBytes);
        test.Number("cursorFirstBytes", cursorRegions.firstBytes);
        test.Number("withoutSecondRegionBytes", bytes);
        test.Boolean("separateWriteMemory", privatePointers);
        test.Boolean("silentBeforeUnlock", beforeUnlock);
        test.Boolean("silentWhilePlaying", playingSilent);
        Require(regions.firstBytes == 16 && regions.secondBytes == 16 && bytes == 16, "Split region contract changed");
        Require(privatePointers && beforeUnlock && playingSilent && IsSilent(*state), "Playing ring read caller writes");
    });
    report.Run("directsound-errors-invalid-unlock-and-retry", [](Scenario& test) {
        auto state = MakeSoundState(WAVE_FORMAT_PCM, 16, 2);
        auto sink = MakeSound(state);
        ComPtr<IDirectSoundBuffer8> caller;
        Ok(SoundBoundary(sink.Get(), &caller));
        state->lockError = DSERR_BUFFERLOST;
        LPVOID pointer = nullptr;
        DWORD bytes = 0;
        Require(caller->Lock(0, 16, &pointer, &bytes, nullptr, nullptr, 0) == DSERR_BUFFERLOST, "Lock error changed");
        state->lockError = S_OK;
        const auto regions = Write(caller.Get(), 0, 16);
        Require(caller->Lock(0, 16, &pointer, &bytes, nullptr, nullptr, 0) == DSERR_INVALIDCALL, "Second Lock succeeded");
        const auto calls = state->unlockCalls;
        const HRESULT invalid = caller->Unlock(regions.first, regions.firstBytes - 1, regions.second, regions.secondBytes);
        Require(invalid == DSERR_INVALIDPARAM && state->locked, "Bad Unlock lost the lock");
        const bool invalidNotSubmitted = state->unlockCalls == calls;
        state->unlockError = DSERR_BUFFERLOST;
        const HRESULT failed = Unlock(caller.Get(), regions);
        Require(failed == DSERR_BUFFERLOST && state->locked, "Unlock error or pending lock changed");
        state->unlockError = S_OK;
        Ok(Unlock(caller.Get(), regions));
        Require(Unlock(caller.Get(), regions) == DSERR_INVALIDPARAM, "Repeated Unlock succeeded");
        state->playError = DSERR_PRIOLEVELNEEDED;
        Require(caller->Play(0, 0, 0) == state->playError, "Play error changed");
        test.String("invalidUnlock", Hresult(invalid));
        test.String("underlyingUnlock", Hresult(failed));
        test.Boolean("invalidUnlockNotSubmitted", invalidNotSubmitted);
        test.Boolean("retrySilent", IsSilent(*state));
        Require(invalidNotSubmitted && IsSilent(*state), "Unsafe Unlock reached the output sink");
    });
    report.Run("directsound-unsupported-formats-caps-and-effects", [](Scenario& test) {
        unsigned rejected = 0;
        for (unsigned index = 0; index < 6; ++index) {
            auto state = MakeSoundState(WAVE_FORMAT_PCM, 16, 2);
            if (index == 0) state->format.Format.wFormatTag = WAVE_FORMAT_ALAW;
            if (index == 1) state->format.Format.nBlockAlign = 3;
            if (index == 2) state->caps |= DSBCAPS_PRIMARYBUFFER;
            if (index == 3) state->caps |= DSBCAPS_CTRLFX;
            if (index == 4) state->playing = true;
            if (index == 5) state->format.Format.nAvgBytesPerSec = 1;
            auto sink = MakeSound(state);
            ComPtr<IDirectSoundBuffer8> caller;
            const HRESULT result = SoundBoundary(sink.Get(), &caller);
            if (FAILED(result) && !caller) ++rejected;
        }
        auto state = MakeSoundState(WAVE_FORMAT_PCM, 8, 2, true);
        auto sink = MakeSound(state);
        ComPtr<IDirectSoundBuffer8> caller;
        Ok(SoundBoundary(sink.Get(), &caller));
        Require(caller->SetFX(0, nullptr, nullptr) == DSERR_CONTROLUNAVAIL, "SetFX exposed effects");
        Require(caller->AcquireResources(0, 0, nullptr) == DSERR_CONTROLUNAVAIL, "Effect resources exposed");
        void* object = reinterpret_cast<void*>(1);
        const HRESULT result = caller->GetObjectInPath(GUID_NULL, 0, EscapeId, &object);
        const bool blocked = result == E_NOINTERFACE && !object;
        if (SUCCEEDED(result)) static_cast<IUnknown*>(object)->Release();
        test.Number("rejectedInputs", rejected);
        test.Boolean("effectInterfaceBlocked", blocked);
        test.String("extensiblePcm8Hex", Hex(state->memory));
        Require(rejected == 6 && blocked && IsSilent(*state), "Unsupported input escaped the scope");
    });
    report.Run("directsound-lost-buffer-restoration", [](Scenario& test) {
        auto state = MakeSoundState(WAVE_FORMAT_PCM, 8, 2);
        auto sink = MakeSound(state);
        ComPtr<IDirectSoundBuffer8> caller;
        Ok(SoundBoundary(sink.Get(), &caller));
        state->lost = true;
        state->restoreError = DSERR_OUTOFMEMORY;
        const HRESULT failed = caller->Restore();
        Require(failed == state->restoreError, "Restore error changed");
        state->restoreError = S_OK;
        Ok(caller->Restore());
        Ok(caller->Play(0, 0, DSBPLAY_LOOPING));
        const bool restoredSilent = state->outputs.back();
        Ok(caller->Stop());
        state->lost = true;
        state->lockError = DSERR_BUFFERLOST;
        const HRESULT resetFailure = caller->Restore();
        const HRESULT blockedPlay = caller->Play(0, 0, DSBPLAY_LOOPING);
        state->lockError = S_OK;
        Ok(caller->Restore());
        Ok(caller->Play(0, 0, DSBPLAY_LOOPING));
        test.String("restoreError", Hresult(failed));
        test.String("clearFailure", Hresult(resetFailure));
        test.String("playAfterClearFailure", Hresult(blockedPlay));
        test.Boolean("firstRestoredPlaySilent", restoredSilent);
        test.Boolean("retrySilent", state->outputs.back());
        Require(restoredSilent && state->outputs.back() && resetFailure == DSERR_BUFFERLOST && blockedPlay == DSERR_BUFFERLOST, "Restored memory reached Play before silence");
    });
    report.Run("directsound-identity-recreation-and-teardown", [](Scenario& test) {
        unsigned destroyed = 0;
        bool identity = true;
        bool blocked = true;
        bool unlocked = true;
        bool allSilent = true;
        for (unsigned index = 0; index < 32; ++index) {
            auto state = MakeSoundState(WAVE_FORMAT_PCM, 16, 2);
            auto sink = MakeSound(state);
            ComPtr<IDirectSoundBuffer8> caller;
            Ok(SoundBoundary(sink.Get(), &caller));
            sink.Reset();
            ComPtr<IDirectSoundBuffer> base;
            ComPtr<IUnknown> first, second;
            Ok(caller->QueryInterface(IID_IDirectSoundBuffer, reinterpret_cast<void**>(base.GetAddressOf())));
            Ok(caller.As(&first));
            Ok(base.As(&second));
            identity = identity && first.Get() == second.Get();
            void* escape = nullptr;
            const HRESULT result = base->QueryInterface(EscapeId, &escape);
            blocked = blocked && result == E_NOINTERFACE && !escape;
            if (SUCCEEDED(result)) static_cast<IUnknown*>(escape)->Release();
            base.Reset(); first.Reset(); second.Reset();
            const ULONG increased = caller->AddRef();
            const ULONG decreased = caller->Release();
            Require(increased == 2 && decreased == 1, "DirectSound reference count changed");
            Write(caller.Get(), 0, 16);
            caller.Reset();
            destroyed += state->destroyed ? 1 : 0;
            unlocked = unlocked && !state->locked;
            allSilent = allSilent && IsSilent(*state);
        }
        test.Number("recreatedAndDestroyed", destroyed);
        test.Boolean("sameIdentity", identity);
        test.Boolean("allEscapesBlocked", blocked);
        test.Boolean("pendingLocksReleased", unlocked);
        test.Boolean("allOutputSilent", allSilent);
        Require(destroyed == 32 && identity && blocked && unlocked && allSilent, "Recreation or teardown escaped the boundary");
    });
}
}
