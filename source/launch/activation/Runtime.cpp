#include "Runtime.h"
#include <new>

namespace activation {
Node::Node(std::shared_ptr<Runtime> runtime, IUnknown* identity) : runtime_(std::move(runtime)), identity_(identity) {
    std::lock_guard<std::mutex> guard(runtime_->mutex_);
    ++runtime_->liveNodes_;
}
Node::~Node() {
    identity_.Reset();
    std::lock_guard<std::mutex> guard(runtime_->mutex_);
    --runtime_->liveNodes_;
}
ULONG Node::AddRef() { return ++references_; }
ULONG Node::Release() {
    ULONG remaining;
    {
        std::lock_guard<std::mutex> guard(runtime_->mutex_);
        remaining = --references_;
        if (!remaining) {
            const auto found = runtime_->nodes_.find(identity_.Get());
            if (found != runtime_->nodes_.end() && found->second.node == this) runtime_->nodes_.erase(found);
        }
    }
    if (!remaining) delete this;
    return remaining;
}
HRESULT Runtime::Wrap(IUnknown* raw, Kind kind, REFIID iid, void** output) {
    *output = nullptr;
    ComPtr<IUnknown> identity;
    HRESULT result = raw->QueryInterface(IID_IUnknown, reinterpret_cast<void**>(identity.GetAddressOf()));
    if (FAILED(result)) return result;
    Node* node = nullptr;
    bool reserved = false;
    try {
        {
            std::lock_guard<std::mutex> guard(mutex_);
            const auto found = nodes_.find(identity.Get());
            if (found != nodes_.end()) {
                if (found->second.kind != kind) return E_NOINTERFACE;
                if (!found->second.node) return E_PENDING;
                node = found->second.node;
                node->AddRef();
            } else {
                nodes_.emplace(identity.Get(), Entry{kind, nullptr});
                reserved = true;
            }
        }
        if (reserved) {
            // Provider and leaf calls occur outside the registry lock.
            std::unique_ptr<Node> candidate;
            if (kind == Kind::Enumerator || kind == Kind::Device) candidate = MakeEndpointNode(shared_from_this(), identity.Get(), kind);
            else if (kind == Kind::Audio) candidate = MakeAudioNode(shared_from_this(), identity.Get(), result);
            else if (kind == Kind::DirectSound) candidate = MakeDirectSoundNode(shared_from_this(), identity.Get());
            else candidate = MakeSoundNode(shared_from_this(), identity.Get(), result);
            {
                std::lock_guard<std::mutex> guard(mutex_);
                if (FAILED(result)) nodes_.erase(identity.Get());
                else nodes_.at(identity.Get()).node = candidate.get();
            }
            if (FAILED(result)) return result;
            node = candidate.release();
        }
        result = node->QueryKnown(iid, output);
        node->Release();
        return result;
    } catch (const std::bad_alloc&) {
        if (reserved) { std::lock_guard<std::mutex> guard(mutex_); nodes_.erase(identity.Get()); }
        return E_OUTOFMEMORY;
    }
}
[[noreturn]] void Runtime::Abort(HRESULT code, const char* stage) {
    provider->Abort(code, stage);
    std::terminate();
}
bool Runtime::CanUnload() const {
    std::lock_guard<std::mutex> guard(mutex_);
    return liveNodes_ == 0 && nodes_.empty() && activeCalls == 0;
}
Boundary::Boundary(std::shared_ptr<Provider> provider) : runtime_(std::make_shared<Runtime>(std::move(provider))) {}
HRESULT Boundary::CreateCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output) {
    if (!output) return E_POINTER;
    *output = nullptr;
    Activity activity(*runtime_);
    if (clsid != __uuidof(MMDeviceEnumerator)) return runtime_->provider->CreateCom(clsid, outer, context, iid, output);
    if (outer) return CLASS_E_NOAGGREGATION;
    if (iid != IID_IUnknown && iid != __uuidof(IMMDeviceEnumerator)) return E_NOINTERFACE;
    void* value = nullptr;
    const HRESULT factory = runtime_->provider->CreateCom(clsid, nullptr, context, iid, &value);
    if (FAILED(factory)) return factory;
    ComPtr<IUnknown> raw;
    raw.Attach(static_cast<IUnknown*>(value));
    const HRESULT wrapped = runtime_->Wrap(raw.Get(), Kind::Enumerator, iid, output);
    return FAILED(wrapped) ? wrapped : factory;
}
HRESULT Boundary::CreateDirectSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer) {
    if (!output) return E_POINTER;
    *output = nullptr;
    Activity activity(*runtime_);
    if (outer) return CLASS_E_NOAGGREGATION;
    ComPtr<IDirectSound8> raw;
    const HRESULT factory = runtime_->provider->CreateDirectSound(device, &raw, nullptr);
    if (FAILED(factory)) return factory;
    const HRESULT wrapped = runtime_->Wrap(raw.Get(), Kind::DirectSound, IID_IDirectSound8, reinterpret_cast<void**>(output));
    return FAILED(wrapped) ? wrapped : factory;
}
bool Boundary::CanUnload() const { return runtime_->CanUnload(); }
}
