#include "QuietFormat.h"
#include <wrl/client.h>
#include <atomic>
#include <cstring>
#include <mutex>
#include <new>
#include <vector>

namespace quiet {
class QuietSoundBuffer final : public IDirectSoundBuffer8 {
public:
    QuietSoundBuffer(IDirectSoundBuffer8* sink, SoundContract contract)
        : sink_(sink), silence_(contract.silenceByte), scratch_(contract.bufferBytes, contract.silenceByte) {}
    HRESULT Prepare() {
        // Silence the whole ring before any caller can invoke Play.
        ready_ = Clear();
        return ready_;
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (iid == IID_IUnknown || iid == IID_IDirectSoundBuffer8) *output = static_cast<IDirectSoundBuffer8*>(this);
        else if (iid == IID_IDirectSoundBuffer) *output = static_cast<IDirectSoundBuffer*>(this);
        else return E_NOINTERFACE;
        AddRef();
        return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references_; }
    ULONG STDMETHODCALLTYPE Release() override {
        const ULONG remaining = --references_;
        if (!remaining) delete this;
        return remaining;
    }
    HRESULT STDMETHODCALLTYPE GetCaps(LPDSBCAPS value) override { return sink_->GetCaps(value); }
    HRESULT STDMETHODCALLTYPE GetCurrentPosition(LPDWORD play, LPDWORD write) override { return sink_->GetCurrentPosition(play, write); }
    HRESULT STDMETHODCALLTYPE GetFormat(LPWAVEFORMATEX format, DWORD bytes, LPDWORD written) override { return sink_->GetFormat(format, bytes, written); }
    HRESULT STDMETHODCALLTYPE GetVolume(LPLONG value) override { return sink_->GetVolume(value); }
    HRESULT STDMETHODCALLTYPE GetPan(LPLONG value) override { return sink_->GetPan(value); }
    HRESULT STDMETHODCALLTYPE GetFrequency(LPDWORD value) override { return sink_->GetFrequency(value); }
    HRESULT STDMETHODCALLTYPE GetStatus(LPDWORD value) override { return sink_->GetStatus(value); }
    HRESULT STDMETHODCALLTYPE Initialize(LPDIRECTSOUND, LPCDSBUFFERDESC) override { return DSERR_ALREADYINITIALIZED; }
    HRESULT STDMETHODCALLTYPE Lock(DWORD offset, DWORD bytes, LPVOID* first, LPDWORD firstBytes,
        LPVOID* second, LPDWORD secondBytes, DWORD flags) override {
        std::lock_guard<std::mutex> guard(mutex_);
        if (FAILED(ready_)) return ready_;
        if (pending_) return DSERR_INVALIDCALL;
        if (!first || !firstBytes || (!second != !secondBytes)) return DSERR_INVALIDPARAM;
        const HRESULT result = sink_->Lock(offset, bytes, &regions_.first, &regions_.firstBytes,
            second ? &regions_.second : nullptr, second ? &regions_.secondBytes : nullptr, flags);
        if (FAILED(result)) { regions_ = {}; return result; }
        pending_ = true;
        // Keep output memory silent while the caller writes private memory.
        SilenceRegions();
        *first = scratch_.data();
        *firstBytes = regions_.firstBytes;
        if (second) {
            *second = regions_.second ? scratch_.data() + regions_.firstBytes : nullptr;
            *secondBytes = regions_.secondBytes;
        }
        return result;
    }
    HRESULT STDMETHODCALLTYPE Play(DWORD first, DWORD second, DWORD flags) override {
        std::lock_guard<std::mutex> guard(mutex_);
        if (FAILED(ready_)) return ready_;
        return sink_->Play(first, second, flags);
    }
    HRESULT STDMETHODCALLTYPE SetCurrentPosition(DWORD value) override { return sink_->SetCurrentPosition(value); }
    HRESULT STDMETHODCALLTYPE SetFormat(LPCWAVEFORMATEX) override { return DSERR_INVALIDCALL; }
    HRESULT STDMETHODCALLTYPE SetVolume(LONG value) override { return sink_->SetVolume(value); }
    HRESULT STDMETHODCALLTYPE SetPan(LONG value) override { return sink_->SetPan(value); }
    HRESULT STDMETHODCALLTYPE SetFrequency(DWORD value) override { return sink_->SetFrequency(value); }
    HRESULT STDMETHODCALLTYPE Stop() override { return sink_->Stop(); }
    HRESULT STDMETHODCALLTYPE Unlock(LPVOID first, DWORD firstBytes, LPVOID second, DWORD secondBytes) override {
        std::lock_guard<std::mutex> guard(mutex_);
        const LPVOID expectedSecond = regions_.second ? scratch_.data() + regions_.firstBytes : nullptr;
        if (!pending_ || first != scratch_.data() || firstBytes != regions_.firstBytes ||
            second != expectedSecond || secondBytes != regions_.secondBytes) return DSERR_INVALIDPARAM;
        SilenceRegions();
        return SubmitRegions();
    }
    HRESULT STDMETHODCALLTYPE Restore() override {
        std::lock_guard<std::mutex> guard(mutex_);
        if (pending_) return DSERR_INVALIDCALL;
        const HRESULT result = sink_->Restore();
        if (FAILED(result)) return result;
        ready_ = Clear();
        return ready_;
    }
    HRESULT STDMETHODCALLTYPE SetFX(DWORD, LPDSEFFECTDESC, LPDWORD) override { return DSERR_CONTROLUNAVAIL; }
    HRESULT STDMETHODCALLTYPE AcquireResources(DWORD, DWORD, LPDWORD) override { return DSERR_CONTROLUNAVAIL; }
    HRESULT STDMETHODCALLTYPE GetObjectInPath(REFGUID, DWORD, REFGUID, LPVOID* output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        return E_NOINTERFACE;
    }
private:
    ~QuietSoundBuffer() {
        if (pending_) { SilenceRegions(); SubmitRegions(); }
    }
    void SilenceRegions() {
        memset(regions_.first, silence_, regions_.firstBytes);
        if (regions_.second) memset(regions_.second, silence_, regions_.secondBytes);
    }
    HRESULT SubmitRegions() {
        const HRESULT result = sink_->Unlock(regions_.first, regions_.firstBytes, regions_.second, regions_.secondBytes);
        if (SUCCEEDED(result)) { pending_ = false; regions_ = {}; }
        return result;
    }
    HRESULT Clear() {
        const HRESULT result = sink_->Lock(0, 0, &regions_.first, &regions_.firstBytes,
            &regions_.second, &regions_.secondBytes, DSBLOCK_ENTIREBUFFER);
        if (FAILED(result)) { regions_ = {}; return result; }
        pending_ = true;
        SilenceRegions();
        return SubmitRegions();
    }
    struct Regions { LPVOID first = nullptr; DWORD firstBytes = 0; LPVOID second = nullptr; DWORD secondBytes = 0; } regions_;
    std::atomic<ULONG> references_{1};
    Microsoft::WRL::ComPtr<IDirectSoundBuffer8> sink_;
    BYTE silence_;
    std::vector<BYTE> scratch_;
    std::mutex mutex_;
    bool pending_ = false;
    HRESULT ready_ = DSERR_INVALIDCALL;
};
HRESULT WrapSoundBuffer(IDirectSoundBuffer8* sink, IDirectSoundBuffer8** output) {
    if (!output) return E_POINTER;
    *output = nullptr;
    if (!sink) return E_POINTER;
    SoundContract contract{};
    HRESULT result = ReadSoundContract(sink, contract);
    if (FAILED(result)) return result;
    QuietSoundBuffer* wrapper = nullptr;
    try { wrapper = new QuietSoundBuffer(sink, contract); }
    catch (const std::bad_alloc&) { return E_OUTOFMEMORY; }
    result = wrapper->Prepare();
    if (FAILED(result)) { wrapper->Release(); return result; }
    *output = wrapper;
    return S_OK;
}
}
