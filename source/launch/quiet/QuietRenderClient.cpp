#include "QuietBoundary.h"
#include <wrl/client.h>
#include <atomic>
#include <new>

namespace quiet {
class QuietRenderClient final : public IAudioRenderClient {
public:
    explicit QuietRenderClient(IAudioRenderClient* sink) : sink_(sink) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (iid != IID_IUnknown && iid != __uuidof(IAudioRenderClient)) return E_NOINTERFACE;
        *output = static_cast<IAudioRenderClient*>(this);
        AddRef();
        return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references_; }
    ULONG STDMETHODCALLTYPE Release() override {
        const ULONG remaining = --references_;
        if (!remaining) delete this;
        return remaining;
    }
    HRESULT STDMETHODCALLTYPE GetBuffer(UINT32 frames, BYTE** samples) override { return sink_->GetBuffer(frames, samples); }
    HRESULT STDMETHODCALLTYPE ReleaseBuffer(UINT32 frames, DWORD flags) override {
        // The SDK treats this packet as silence, regardless of the sample bytes.
        return sink_->ReleaseBuffer(frames, flags | AUDCLNT_BUFFERFLAGS_SILENT);
    }
private:
    std::atomic<ULONG> references_{1};
    Microsoft::WRL::ComPtr<IAudioRenderClient> sink_;
};
HRESULT WrapRenderClient(IAudioRenderClient* sink, IAudioRenderClient** output) {
    if (!output) return E_POINTER;
    *output = nullptr;
    if (!sink) return E_POINTER;
    auto* wrapper = new (std::nothrow) QuietRenderClient(sink);
    if (!wrapper) return E_OUTOFMEMORY;
    *output = wrapper;
    return S_OK;
}
}
