#pragma once
#include "Providers.h"

namespace activation_test {
template<typename Interface> class Object : public Interface {
public:
    explicit Object(const IID& iid) : iid_(iid) {}
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if (!output) return E_POINTER;
        *output = nullptr;
        if (iid != IID_IUnknown && iid != iid_ && iid != fixture::EscapeId) return E_NOINTERFACE;
        *output = static_cast<Interface*>(this);
        AddRef();
        return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references_; }
    ULONG STDMETHODCALLTYPE Release() override {
        const ULONG remaining = --references_;
        if (!remaining) delete this;
        return remaining;
    }
protected:
    virtual ~Object() = default;
private:
    IID iid_;
    std::atomic<ULONG> references_{1};
};
template<typename Interface, typename Concrete, typename... Arguments>
ComPtr<Interface> Make(Arguments&&... arguments) {
    ComPtr<Interface> result;
    result.Attach(new Concrete(std::forward<Arguments>(arguments)...));
    return result;
}
class SessionMethods {
public:
    SessionMethods(std::shared_ptr<State> state, std::shared_ptr<Generation> generation)
        : state_(std::move(state)), generation_(std::move(generation)) {}
    HRESULT Register(IAudioSessionEvents* callback) {
        state_->Event("provider.session.register", generation_->id);
        state_->lastSessionCallback = callback;
        ++generation_->sessionRegisters;
        if (SUCCEEDED(state_->sessionRegisterResult)) generation_->callbacks.emplace_back(callback);
        return state_->sessionRegisterResult;
    }
    HRESULT Unregister(IAudioSessionEvents* callback) {
        state_->Event("provider.session.unregister", generation_->id);
        ++generation_->sessionUnregisters;
        const auto found = std::find_if(generation_->callbacks.begin(), generation_->callbacks.end(), [=](const auto& value) { return value.Get() == callback; });
        if (found == generation_->callbacks.end()) return E_INVALIDARG;
        generation_->callbacks.erase(found);
        return S_OK;
    }
private:
    std::shared_ptr<State> state_;
    std::shared_ptr<Generation> generation_;
};
}
