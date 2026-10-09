#include "ProviderCommon.h"
#include <cstring>

namespace activation_test {
void State::Event(const std::string& name, unsigned generation) { events.push_back(name + ":g" + std::to_string(generation)); }
std::shared_ptr<Generation> State::NewGeneration() {
    auto generation = std::make_shared<Generation>();
    generation->id = nextId++;
    generations.push_back(generation);
    Event("provider.generation", generation->id);
    return generation;
}
void State::NotifyEndpoint() {
    auto callbacks = endpointCallbacks;
    for (const auto& callback : callbacks) {
        callbackThread = GetCurrentThreadId();
        Ok(callback->OnDefaultDeviceChanged(eRender, eConsole, L"owned-endpoint"));
    }
}
void State::NotifySession(const std::shared_ptr<Generation>& generation) {
    auto callbacks = generation->callbacks;
    for (const auto& callback : callbacks) {
        callbackThread = GetCurrentThreadId();
        Ok(callback->OnStateChanged(AudioSessionStateActive));
    }
}
bool SameIdentity(IUnknown* first, IUnknown* second) {
    ComPtr<IUnknown> a, b;
    fixture::Ok(first->QueryInterface(IID_IUnknown, reinterpret_cast<void**>(a.GetAddressOf())));
    fixture::Ok(second->QueryInterface(IID_IUnknown, reinterpret_cast<void**>(b.GetAddressOf())));
    return a.Get() == b.Get();
}
bool IsRaw(IUnknown* value) {
    ComPtr<IUnknown> escape;
    return SUCCEEDED(value->QueryInterface(fixture::EscapeId, reinterpret_cast<void**>(escape.GetAddressOf())));
}
void Publish(State& state, IUnknown* value, const char* type, unsigned generation) {
    const bool raw = IsRaw(value);
    state.rawPublications += raw ? 1 : 0;
    state.Event(std::string("consumer.publish.") + type + (raw ? ".raw" : ".wrapped"), generation);
}
class Device final : public Object<IMMDevice> {
public:
    explicit Device(std::shared_ptr<State> state) : Object(__uuidof(IMMDevice)), state_(std::move(state)) {}
    HRESULT STDMETHODCALLTYPE Activate(REFIID iid, DWORD, PROPVARIANT*, void** output) override {
        *output = nullptr;
        state_->Event("provider.device.activate");
        if (FAILED(state_->activateError)) return state_->activateError;
        if (iid != __uuidof(IAudioClient)) return E_NOINTERFACE;
        auto client = MakeClient(state_, state_->NewGeneration());
        return client->QueryInterface(iid, output);
    }
    HRESULT STDMETHODCALLTYPE OpenPropertyStore(DWORD, IPropertyStore** output) override { *output = nullptr; return E_NOINTERFACE; }
    HRESULT STDMETHODCALLTYPE GetId(LPWSTR* output) override {
        *output = static_cast<LPWSTR>(CoTaskMemAlloc(32));
        if (!*output) return E_OUTOFMEMORY;
        wcscpy_s(*output, 16, L"owned-endpoint");
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetState(DWORD* output) override { *output = DEVICE_STATE_ACTIVE; return S_OK; }
private:
    std::shared_ptr<State> state_;
};
class Enumerator final : public Object<IMMDeviceEnumerator> {
public:
    explicit Enumerator(std::shared_ptr<State> state)
        : Object(__uuidof(IMMDeviceEnumerator)), state_(std::move(state)), device_(Make<IMMDevice, Device>(state_)) {}
    HRESULT STDMETHODCALLTYPE EnumAudioEndpoints(EDataFlow, DWORD, IMMDeviceCollection** output) override { *output = nullptr; return E_NOINTERFACE; }
    HRESULT STDMETHODCALLTYPE GetDefaultAudioEndpoint(EDataFlow flow, ERole role, IMMDevice** output) override {
        *output = nullptr;
        state_->Event("provider.default-endpoint");
        if (state_->reenter) { auto action = std::move(state_->reenter); action(); }
        if (flow != eRender || role != eConsole) return E_INVALIDARG;
        return device_.CopyTo(output);
    }
    HRESULT STDMETHODCALLTYPE GetDevice(LPCWSTR, IMMDevice** output) override { return device_.CopyTo(output); }
    HRESULT STDMETHODCALLTYPE RegisterEndpointNotificationCallback(IMMNotificationClient* callback) override {
        ++state_->endpointRegisters;
        state_->lastEndpointCallback = callback;
        state_->endpointCallbacks.emplace_back(callback);
        state_->Event("provider.endpoint.register");
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE UnregisterEndpointNotificationCallback(IMMNotificationClient* callback) override {
        ++state_->endpointUnregisters;
        auto found = std::find_if(state_->endpointCallbacks.begin(), state_->endpointCallbacks.end(), [=](const auto& value) { return value.Get() == callback; });
        if (found == state_->endpointCallbacks.end()) return E_INVALIDARG;
        state_->endpointCallbacks.erase(found);
        state_->Event("provider.endpoint.unregister");
        return S_OK;
    }
private:
    std::shared_ptr<State> state_;
    ComPtr<IMMDevice> device_;
};
ComPtr<IMMDeviceEnumerator> MakeEnumerator(const std::shared_ptr<State>& state) { return Make<IMMDeviceEnumerator, Enumerator>(state); }
MemoryProvider::MemoryProvider(std::shared_ptr<State> value) : state(std::move(value)), enumerator_(MakeEnumerator(state)) {}
HRESULT MemoryProvider::CreateCom(REFCLSID clsid, LPUNKNOWN outer, DWORD, REFIID iid, void** output) {
    *output = nullptr;
    state->Event(clsid == __uuidof(MMDeviceEnumerator) ? "provider.factory.enumerator" : "provider.factory.non-audio");
    if (state->reenterRoot) { auto action = std::move(state->reenterRoot); action(); }
    if (FAILED(state->rootError)) return state->rootError;
    if (outer) return CLASS_E_NOAGGREGATION;
    if (clsid != __uuidof(MMDeviceEnumerator)) return enumerator_->QueryInterface(IID_IUnknown, output);
    if (state->returnSameEnumerator) {
        const HRESULT result = enumerator_->QueryInterface(iid, output);
        FailNextAllocation = state->failAdapterAllocation;
        return result;
    }
    auto enumerator = MakeEnumerator(state);
    return enumerator->QueryInterface(iid, output);
}
HRESULT MemoryProvider::CreateDirectSound(LPCGUID, LPDIRECTSOUND8* output, LPUNKNOWN outer) {
    *output = nullptr;
    state->Event("provider.factory.directsound");
    if (FAILED(state->rootError)) return state->rootError;
    if (outer) return CLASS_E_NOAGGREGATION;
    auto device = MakeDirectSound(state);
    return device.CopyTo(output);
}
[[noreturn]] void MemoryProvider::Abort(HRESULT code, const char* stage) {
    ++state->aborts;
    state->Event(std::string("consumer.abort.") + stage);
    throw Stopped(code);
}
}
