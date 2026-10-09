#include "Fixture.h"

namespace fixture {
// This sink implements the SDK submission contract in owned memory only.
class RenderSink final : public IAudioRenderClient {
public:
    explicit RenderSink(std::shared_ptr<RenderState> state) : state_(std::move(state)) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** object) override {
        if (!object) return E_POINTER;
        *object = nullptr;
        if (iid != IID_IUnknown && iid != __uuidof(IAudioRenderClient) && iid != EscapeId) return E_NOINTERFACE;
        *object = static_cast<IAudioRenderClient*>(this);
        AddRef();
        return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references_; }
    ULONG STDMETHODCALLTYPE Release() override {
        const ULONG remaining = --references_;
        if (!remaining) delete this;
        return remaining;
    }
    HRESULT STDMETHODCALLTYPE GetBuffer(UINT32 frames, BYTE** data) override {
        if (FAILED(state_->getError)) return state_->getError;
        if (!data) return E_POINTER;
        if (!frames) return S_OK;
        if (state_->pending) return AUDCLNT_E_OUT_OF_ORDER;
        state_->memory.assign(static_cast<size_t>(frames) * state_->channels * 4, 0x55);
        state_->requested = frames;
        state_->pending = true;
        *data = state_->memory.data();
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE ReleaseBuffer(UINT32 frames, DWORD flags) override {
        if (FAILED(state_->releaseError)) return state_->releaseError;
        if (flags & ~AUDCLNT_BUFFERFLAGS_SILENT) return E_INVALIDARG;
        if (!frames && !state_->pending) return S_OK;
        if (!state_->pending) return AUDCLNT_E_OUT_OF_ORDER;
        if (frames > state_->requested) return AUDCLNT_E_INVALID_SIZE;
        Packet packet{frames, flags, (flags & AUDCLNT_BUFFERFLAGS_SILENT) != 0, {}};
        packet.bytes.assign(state_->memory.begin(), state_->memory.begin() + static_cast<size_t>(frames) * state_->channels * 4);
        if (packet.silent) std::fill(packet.bytes.begin(), packet.bytes.end(), BYTE{0});
        else packet.silent = std::all_of(packet.bytes.begin(), packet.bytes.end(), [](BYTE byte) { return byte == 0; });
        state_->packets.push_back(std::move(packet));
        state_->pending = false;
        return S_OK;
    }
private:
    ~RenderSink() { state_->destroyed = true; }
    std::atomic<ULONG> references_{1};
    std::shared_ptr<RenderState> state_;
};
ComPtr<IAudioRenderClient> MakeRender(const std::shared_ptr<RenderState>& state) {
    ComPtr<IAudioRenderClient> result;
    result.Attach(new RenderSink(state));
    return result;
}
}
