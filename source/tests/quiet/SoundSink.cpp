#include "Fixture.h"
#include <algorithm>
#include <cstring>
#include <ks.h>
#include <ksmedia.h>

namespace fixture {
bool IsSilent(const SoundState& state) {
    return std::all_of(state.memory.begin(), state.memory.end(), [&](BYTE byte) { return byte == state.silence; });
}
std::shared_ptr<SoundState> MakeSoundState(WORD tag, WORD bits, WORD channels, bool extensible) {
    auto state = std::make_shared<SoundState>();
    auto& format = state->format.Format;
    format.wFormatTag = extensible ? WAVE_FORMAT_EXTENSIBLE : tag;
    format.nChannels = channels;
    format.nSamplesPerSec = 48000;
    format.wBitsPerSample = bits;
    format.nBlockAlign = channels * (bits / 8);
    format.nAvgBytesPerSec = format.nSamplesPerSec * format.nBlockAlign;
    if (extensible) {
        format.cbSize = 22;
        state->format.Samples.wValidBitsPerSample = bits;
        state->format.dwChannelMask = channels == 2 ? 3 : 0;
        state->format.SubFormat = tag == WAVE_FORMAT_PCM ? KSDATAFORMAT_SUBTYPE_PCM : KSDATAFORMAT_SUBTYPE_IEEE_FLOAT;
        state->formatBytes = sizeof(WAVEFORMATEXTENSIBLE);
    }
    state->silence = tag == WAVE_FORMAT_PCM && bits == 8 ? 0x80 : 0;
    state->memory.assign(static_cast<size_t>(format.nBlockAlign) * 32, 0x55);
    return state;
}
// This circular buffer never calls DirectSoundCreate or opens a physical device.
class SoundSink final : public IDirectSoundBuffer8 {
public:
    explicit SoundSink(std::shared_ptr<SoundState> state) : state_(std::move(state)) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** object) override {
        if (!object) return E_POINTER;
        *object = nullptr;
        if (iid != IID_IUnknown && iid != IID_IDirectSoundBuffer && iid != IID_IDirectSoundBuffer8 && iid != EscapeId) return E_NOINTERFACE;
        *object = static_cast<IDirectSoundBuffer8*>(this);
        AddRef();
        return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references_; }
    ULONG STDMETHODCALLTYPE Release() override {
        const ULONG remaining = --references_;
        if (!remaining) delete this;
        return remaining;
    }
    HRESULT STDMETHODCALLTYPE GetCaps(LPDSBCAPS caps) override {
        if (!caps || caps->dwSize != sizeof(DSBCAPS)) return DSERR_INVALIDPARAM;
        caps->dwFlags = state_->caps;
        caps->dwBufferBytes = static_cast<DWORD>(state_->memory.size());
        return DS_OK;
    }
    HRESULT STDMETHODCALLTYPE GetCurrentPosition(LPDWORD play, LPDWORD write) override {
        if (play) *play = state_->position;
        if (write) *write = state_->position;
        return DS_OK;
    }
    HRESULT STDMETHODCALLTYPE GetFormat(LPWAVEFORMATEX format, DWORD bytes, LPDWORD written) override {
        if (written) *written = state_->formatBytes;
        if (!format) return written ? DS_OK : DSERR_INVALIDPARAM;
        if (bytes < state_->formatBytes) return DSERR_INVALIDPARAM;
        memcpy(format, &state_->format, state_->formatBytes);
        return DS_OK;
    }
    HRESULT STDMETHODCALLTYPE GetVolume(LPLONG value) override { if (!value) return E_POINTER; *value = state_->volume; return DS_OK; }
    HRESULT STDMETHODCALLTYPE GetPan(LPLONG value) override { if (!value) return E_POINTER; *value = state_->pan; return DS_OK; }
    HRESULT STDMETHODCALLTYPE GetFrequency(LPDWORD value) override { if (!value) return E_POINTER; *value = state_->frequency; return DS_OK; }
    HRESULT STDMETHODCALLTYPE GetStatus(LPDWORD value) override {
        if (!value) return E_POINTER;
        *value = (state_->playing ? DSBSTATUS_PLAYING : 0) | (state_->lost ? DSBSTATUS_BUFFERLOST : 0);
        return DS_OK;
    }
    HRESULT STDMETHODCALLTYPE Initialize(LPDIRECTSOUND, LPCDSBUFFERDESC) override { return DSERR_ALREADYINITIALIZED; }
    HRESULT STDMETHODCALLTYPE Lock(DWORD offset, DWORD bytes, LPVOID* first, LPDWORD firstBytes,
        LPVOID* second, LPDWORD secondBytes, DWORD flags) override {
        if (FAILED(state_->lockError)) return state_->lockError;
        if (state_->lost) return DSERR_BUFFERLOST;
        if (state_->locked) return DSERR_INVALIDCALL;
        if (!first || !firstBytes || (!second != !secondBytes) || (flags & ~(DSBLOCK_ENTIREBUFFER | DSBLOCK_FROMWRITECURSOR))) return DSERR_INVALIDPARAM;
        const DWORD capacity = static_cast<DWORD>(state_->memory.size());
        if (flags & DSBLOCK_FROMWRITECURSOR) offset = state_->position;
        if (flags & DSBLOCK_ENTIREBUFFER) bytes = capacity;
        if (offset >= capacity || !bytes || bytes > capacity) return DSERR_INVALIDPARAM;
        state_->first = state_->memory.data() + offset;
        state_->firstBytes = (std::min)(bytes, capacity - offset);
        state_->secondBytes = second ? bytes - state_->firstBytes : 0;
        state_->second = state_->secondBytes ? state_->memory.data() : nullptr;
        *first = state_->first;
        *firstBytes = state_->firstBytes;
        if (second) { *second = state_->second; *secondBytes = state_->secondBytes; }
        state_->locked = true;
        return DS_OK;
    }
    HRESULT STDMETHODCALLTYPE Play(DWORD, DWORD, DWORD) override {
        if (FAILED(state_->playError)) return state_->playError;
        if (state_->lost) return DSERR_BUFFERLOST;
        state_->playing = true;
        state_->outputs.push_back(IsSilent(*state_));
        return DS_OK;
    }
    HRESULT STDMETHODCALLTYPE SetCurrentPosition(DWORD value) override { state_->position = value; return DS_OK; }
    HRESULT STDMETHODCALLTYPE SetFormat(LPCWAVEFORMATEX) override { return DSERR_INVALIDCALL; }
    HRESULT STDMETHODCALLTYPE SetVolume(LONG value) override { state_->volume = value; return DS_OK; }
    HRESULT STDMETHODCALLTYPE SetPan(LONG value) override { state_->pan = value; return DS_OK; }
    HRESULT STDMETHODCALLTYPE SetFrequency(DWORD value) override { state_->frequency = value; return DS_OK; }
    HRESULT STDMETHODCALLTYPE Stop() override { state_->playing = false; return DS_OK; }
    HRESULT STDMETHODCALLTYPE Unlock(LPVOID first, DWORD firstBytes, LPVOID second, DWORD secondBytes) override {
        ++state_->unlockCalls;
        if (FAILED(state_->unlockError)) return state_->unlockError;
        if (!state_->locked || first != state_->first || second != state_->second || firstBytes != state_->firstBytes || secondBytes != state_->secondBytes) return DSERR_INVALIDPARAM;
        state_->locked = false;
        state_->outputs.push_back(IsSilent(*state_));
        return DS_OK;
    }
    HRESULT STDMETHODCALLTYPE Restore() override {
        if (FAILED(state_->restoreError)) return state_->restoreError;
        if (state_->lost) std::fill(state_->memory.begin(), state_->memory.end(), BYTE{0x77});
        state_->lost = false;
        return DS_OK;
    }
    HRESULT STDMETHODCALLTYPE SetFX(DWORD, LPDSEFFECTDESC, LPDWORD) override { return DSERR_CONTROLUNAVAIL; }
    HRESULT STDMETHODCALLTYPE AcquireResources(DWORD, DWORD, LPDWORD) override { return DSERR_CONTROLUNAVAIL; }
    HRESULT STDMETHODCALLTYPE GetObjectInPath(REFGUID, DWORD, REFGUID iid, LPVOID* object) override { return QueryInterface(iid, object); }
private:
    ~SoundSink() { state_->destroyed = true; }
    std::atomic<ULONG> references_{1};
    std::shared_ptr<SoundState> state_;
};
ComPtr<IDirectSoundBuffer8> MakeSound(const std::shared_ptr<SoundState>& state) {
    ComPtr<IDirectSoundBuffer8> result;
    result.Attach(new SoundSink(state));
    return result;
}
}
