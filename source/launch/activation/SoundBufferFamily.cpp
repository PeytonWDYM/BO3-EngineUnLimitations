#include "Runtime.h"

namespace activation {
class SoundBuffer final : public Node, public IDirectSoundBuffer8 {
public:
    SoundBuffer(std::shared_ptr<Runtime> runtime, IUnknown* identity, ComPtr<IDirectSoundBuffer8> quiet)
        : Node(std::move(runtime), identity), quiet_(std::move(quiet)) {}
    HRESULT QueryKnown(REFIID iid, void** output) override { return QueryInterface(iid, output); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (iid == IID_IUnknown || iid == IID_IDirectSoundBuffer8) *output = static_cast<IDirectSoundBuffer8*>(this);
        else if (iid == IID_IDirectSoundBuffer) *output = static_cast<IDirectSoundBuffer*>(this);
        else return E_NOINTERFACE;
        AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return Node::AddRef(); }
    ULONG STDMETHODCALLTYPE Release() override { return Node::Release(); }
    HRESULT STDMETHODCALLTYPE GetCaps(LPDSBCAPS value) override { return quiet_->GetCaps(value); }
    HRESULT STDMETHODCALLTYPE GetCurrentPosition(LPDWORD a, LPDWORD b) override { return quiet_->GetCurrentPosition(a, b); }
    HRESULT STDMETHODCALLTYPE GetFormat(LPWAVEFORMATEX a, DWORD b, LPDWORD c) override { return quiet_->GetFormat(a, b, c); }
    HRESULT STDMETHODCALLTYPE GetVolume(LPLONG value) override { return quiet_->GetVolume(value); }
    HRESULT STDMETHODCALLTYPE GetPan(LPLONG value) override { return quiet_->GetPan(value); }
    HRESULT STDMETHODCALLTYPE GetFrequency(LPDWORD value) override { return quiet_->GetFrequency(value); }
    HRESULT STDMETHODCALLTYPE GetStatus(LPDWORD value) override { return quiet_->GetStatus(value); }
    HRESULT STDMETHODCALLTYPE Initialize(LPDIRECTSOUND a, LPCDSBUFFERDESC b) override { return quiet_->Initialize(a, b); }
    HRESULT STDMETHODCALLTYPE Lock(DWORD a, DWORD b, LPVOID* c, LPDWORD d, LPVOID* e, LPDWORD f, DWORD g) override { return quiet_->Lock(a, b, c, d, e, f, g); }
    HRESULT STDMETHODCALLTYPE Play(DWORD a, DWORD b, DWORD c) override { return quiet_->Play(a, b, c); }
    HRESULT STDMETHODCALLTYPE SetCurrentPosition(DWORD value) override { return quiet_->SetCurrentPosition(value); }
    HRESULT STDMETHODCALLTYPE SetFormat(LPCWAVEFORMATEX value) override { return quiet_->SetFormat(value); }
    HRESULT STDMETHODCALLTYPE SetVolume(LONG value) override { return quiet_->SetVolume(value); }
    HRESULT STDMETHODCALLTYPE SetPan(LONG value) override { return quiet_->SetPan(value); }
    HRESULT STDMETHODCALLTYPE SetFrequency(DWORD value) override { return quiet_->SetFrequency(value); }
    HRESULT STDMETHODCALLTYPE Stop() override { return quiet_->Stop(); }
    HRESULT STDMETHODCALLTYPE Unlock(LPVOID a, DWORD b, LPVOID c, DWORD d) override { return quiet_->Unlock(a, b, c, d); }
    HRESULT STDMETHODCALLTYPE Restore() override { return quiet_->Restore(); }
    HRESULT STDMETHODCALLTYPE SetFX(DWORD a, LPDSEFFECTDESC b, LPDWORD c) override { return quiet_->SetFX(a, b, c); }
    HRESULT STDMETHODCALLTYPE AcquireResources(DWORD a, DWORD b, LPDWORD c) override { return quiet_->AcquireResources(a, b, c); }
    HRESULT STDMETHODCALLTYPE GetObjectInPath(REFGUID a, DWORD b, REFGUID c, LPVOID* d) override { return quiet_->GetObjectInPath(a, b, c, d); }
private:
    ComPtr<IDirectSoundBuffer8> quiet_;
};
std::unique_ptr<Node> MakeSoundNode(const std::shared_ptr<Runtime>& runtime, IUnknown* identity, HRESULT& result) {
    // The SDK factory returned a base buffer. Query Buffer8 before leaf preparation.
    ComPtr<IDirectSoundBuffer8> raw, quiet;
    result = identity->QueryInterface(IID_IDirectSoundBuffer8, reinterpret_cast<void**>(raw.GetAddressOf()));
    if (FAILED(result)) return nullptr;
    result = quiet::WrapSoundBuffer(raw.Get(), &quiet);
    if (FAILED(result)) return nullptr;
    return std::make_unique<SoundBuffer>(runtime, identity, std::move(quiet));
}
}
