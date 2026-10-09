#include "Callbacks.h"

namespace driver_probe {
template<typename Interface> class Callback : public Interface {
public:
    explicit Callback(std::shared_ptr<CallbackCounts> counts) : counts_(std::move(counts)) { ++counts_->live; }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        if(!output) return E_POINTER;
        *output=nullptr;
        if(iid!=IID_IUnknown && iid!=__uuidof(Interface)) return E_NOINTERFACE;
        *output=static_cast<Interface*>(this); AddRef(); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return ++references_; }
    ULONG STDMETHODCALLTYPE Release() override { const ULONG remaining=--references_; if(!remaining) delete this; return remaining; }
protected:
    virtual ~Callback() { --counts_->live; }
    std::shared_ptr<CallbackCounts> counts_;
private:
    std::atomic<ULONG> references_{1};
};
class Session final : public Callback<IAudioSessionEvents> {
public:
    using Callback::Callback;
    HRESULT STDMETHODCALLTYPE OnDisplayNameChanged(LPCWSTR,LPCGUID) override { return Hit(); }
    HRESULT STDMETHODCALLTYPE OnIconPathChanged(LPCWSTR,LPCGUID) override { return Hit(); }
    HRESULT STDMETHODCALLTYPE OnSimpleVolumeChanged(float,BOOL,LPCGUID) override { return Hit(); }
    HRESULT STDMETHODCALLTYPE OnChannelVolumeChanged(DWORD,float*,DWORD,LPCGUID) override { return Hit(); }
    HRESULT STDMETHODCALLTYPE OnGroupingParamChanged(LPCGUID,LPCGUID) override { return Hit(); }
    HRESULT STDMETHODCALLTYPE OnStateChanged(AudioSessionState) override { return Hit(); }
    HRESULT STDMETHODCALLTYPE OnSessionDisconnected(AudioSessionDisconnectReason) override { return Hit(); }
private:
    HRESULT Hit() { ++counts_->session; return S_OK; }
};
class Endpoint final : public Callback<IMMNotificationClient> {
public:
    using Callback::Callback;
    HRESULT STDMETHODCALLTYPE OnDeviceStateChanged(LPCWSTR,DWORD) override { return Hit(); }
    HRESULT STDMETHODCALLTYPE OnDeviceAdded(LPCWSTR) override { return Hit(); }
    HRESULT STDMETHODCALLTYPE OnDeviceRemoved(LPCWSTR) override { return Hit(); }
    HRESULT STDMETHODCALLTYPE OnDefaultDeviceChanged(EDataFlow,ERole,LPCWSTR) override { return Hit(); }
    HRESULT STDMETHODCALLTYPE OnPropertyValueChanged(LPCWSTR,const PROPERTYKEY) override { return Hit(); }
private:
    HRESULT Hit() { ++counts_->endpoint; return S_OK; }
};
ComPtr<IAudioSessionEvents> SessionCallback(const std::shared_ptr<CallbackCounts>& counts) {
    ComPtr<IAudioSessionEvents> result; result.Attach(new Session(counts)); return result;
}
ComPtr<IMMNotificationClient> EndpointCallback(const std::shared_ptr<CallbackCounts>& counts) {
    ComPtr<IMMNotificationClient> result; result.Attach(new Endpoint(counts)); return result;
}
}
