#include "Runtime.h"

namespace activation {
class DirectSound final : public Node, public IDirectSound8 {
public:
    DirectSound(std::shared_ptr<Runtime> runtime, IUnknown* identity) : Node(std::move(runtime), identity) {
        identity->QueryInterface(IID_IDirectSound8, reinterpret_cast<void**>(raw_.GetAddressOf()));
    }
    HRESULT QueryKnown(REFIID iid, void** output) override { return QueryInterface(iid, output); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (iid == IID_IUnknown || iid == IID_IDirectSound8) *output = static_cast<IDirectSound8*>(this);
        else if (iid == IID_IDirectSound) *output = static_cast<IDirectSound*>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return Node::AddRef(); }
    ULONG STDMETHODCALLTYPE Release() override { return Node::Release(); }
    HRESULT STDMETHODCALLTYPE CreateSoundBuffer(LPCDSBUFFERDESC description, LPDIRECTSOUNDBUFFER* output, LPUNKNOWN outer) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (outer) runtime_->Abort(CLASS_E_NOAGGREGATION, "buffer-aggregation");
        ComPtr<IDirectSoundBuffer> raw;
        const HRESULT result = raw_->CreateSoundBuffer(description, &raw, nullptr);
        if (FAILED(result)) runtime_->Abort(result, "buffer-create");
        const HRESULT wrapped = runtime_->Wrap(raw.Get(), Kind::SoundBuffer, IID_IDirectSoundBuffer, reinterpret_cast<void**>(output));
        if (FAILED(wrapped)) runtime_->Abort(wrapped, "buffer-prepare");
        return result;
    }
    HRESULT STDMETHODCALLTYPE GetCaps(LPDSCAPS value) override { return raw_->GetCaps(value); }
    HRESULT STDMETHODCALLTYPE DuplicateSoundBuffer(LPDIRECTSOUNDBUFFER, LPDIRECTSOUNDBUFFER* output) override {
        if (output) *output = nullptr;
        runtime_->Abort(DSERR_UNSUPPORTED, "buffer-duplicate");
    }
    HRESULT STDMETHODCALLTYPE SetCooperativeLevel(HWND window, DWORD level) override { return raw_->SetCooperativeLevel(window, level); }
    HRESULT STDMETHODCALLTYPE Compact() override { return raw_->Compact(); }
    HRESULT STDMETHODCALLTYPE GetSpeakerConfig(LPDWORD value) override { return raw_->GetSpeakerConfig(value); }
    HRESULT STDMETHODCALLTYPE SetSpeakerConfig(DWORD value) override { return raw_->SetSpeakerConfig(value); }
    HRESULT STDMETHODCALLTYPE Initialize(LPCGUID value) override { return raw_->Initialize(value); }
    HRESULT STDMETHODCALLTYPE VerifyCertification(LPDWORD value) override { return raw_->VerifyCertification(value); }
private:
    ComPtr<IDirectSound8> raw_;
};
std::unique_ptr<Node> MakeDirectSoundNode(const std::shared_ptr<Runtime>& runtime, IUnknown* identity) { return std::make_unique<DirectSound>(runtime, identity); }
}
