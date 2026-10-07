#include "Runtime.h"

namespace activation {
class Enumerator final : public Node, public IMMDeviceEnumerator {
public:
    Enumerator(std::shared_ptr<Runtime> runtime, IUnknown* identity) : Node(std::move(runtime), identity) {
        identity->QueryInterface(__uuidof(IMMDeviceEnumerator), reinterpret_cast<void**>(raw_.GetAddressOf()));
    }
    HRESULT QueryKnown(REFIID iid, void** output) override { return QueryInterface(iid, output); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (iid != IID_IUnknown && iid != __uuidof(IMMDeviceEnumerator)) return E_NOINTERFACE;
        *output = static_cast<IMMDeviceEnumerator*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return Node::AddRef(); }
    ULONG STDMETHODCALLTYPE Release() override { return Node::Release(); }
    HRESULT STDMETHODCALLTYPE EnumAudioEndpoints(EDataFlow, DWORD, IMMDeviceCollection** output) override { if (!output) return E_POINTER; *output = nullptr; return E_NOINTERFACE; }
    HRESULT STDMETHODCALLTYPE GetDefaultAudioEndpoint(EDataFlow flow, ERole role, IMMDevice** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (flow != eRender || role != eConsole) return E_INVALIDARG;
        ComPtr<IMMDevice> raw;
        const HRESULT result = raw_->GetDefaultAudioEndpoint(flow, role, &raw);
        if (FAILED(result)) return result;
        const HRESULT wrapped = runtime_->Wrap(raw.Get(), Kind::Device, __uuidof(IMMDevice), reinterpret_cast<void**>(output));
        return FAILED(wrapped) ? wrapped : result;
    }
    HRESULT STDMETHODCALLTYPE GetDevice(LPCWSTR, IMMDevice** output) override { if (!output) return E_POINTER; *output = nullptr; return E_NOINTERFACE; }
    HRESULT STDMETHODCALLTYPE RegisterEndpointNotificationCallback(IMMNotificationClient* callback) override { return raw_->RegisterEndpointNotificationCallback(callback); }
    HRESULT STDMETHODCALLTYPE UnregisterEndpointNotificationCallback(IMMNotificationClient* callback) override { return raw_->UnregisterEndpointNotificationCallback(callback); }
private:
    ComPtr<IMMDeviceEnumerator> raw_;
};
class Device final : public Node, public IMMDevice {
public:
    Device(std::shared_ptr<Runtime> runtime, IUnknown* identity) : Node(std::move(runtime), identity) {
        identity->QueryInterface(__uuidof(IMMDevice), reinterpret_cast<void**>(raw_.GetAddressOf()));
    }
    HRESULT QueryKnown(REFIID iid, void** output) override { return QueryInterface(iid, output); }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (iid != IID_IUnknown && iid != __uuidof(IMMDevice)) return E_NOINTERFACE;
        *output = static_cast<IMMDevice*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return Node::AddRef(); }
    ULONG STDMETHODCALLTYPE Release() override { return Node::Release(); }
    HRESULT STDMETHODCALLTYPE Activate(REFIID iid, DWORD context, PROPVARIANT* parameters, void** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (iid != __uuidof(IAudioClient)) return E_NOINTERFACE;
        ComPtr<IAudioClient> raw;
        const HRESULT result = raw_->Activate(iid, context, parameters, reinterpret_cast<void**>(raw.GetAddressOf()));
        if (FAILED(result)) return result;
        const HRESULT wrapped = runtime_->Wrap(raw.Get(), Kind::Audio, iid, output);
        return FAILED(wrapped) ? wrapped : result;
    }
    HRESULT STDMETHODCALLTYPE OpenPropertyStore(DWORD, IPropertyStore** output) override { if (!output) return E_POINTER; *output = nullptr; return E_NOINTERFACE; }
    HRESULT STDMETHODCALLTYPE GetId(LPWSTR* output) override { return raw_->GetId(output); }
    HRESULT STDMETHODCALLTYPE GetState(DWORD* output) override { return raw_->GetState(output); }
private:
    ComPtr<IMMDevice> raw_;
};
std::unique_ptr<Node> MakeEndpointNode(const std::shared_ptr<Runtime>& runtime, IUnknown* identity, Kind kind) {
    if (kind == Kind::Enumerator) return std::make_unique<Enumerator>(runtime, identity);
    return std::make_unique<Device>(runtime, identity);
}
}
