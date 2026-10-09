#include "MemoryCallbacks.h"
#include "../activation/ProviderCommon.h"
using namespace activation_test;
namespace {
class Endpoint final : public Object<IMMNotificationClient> {
public:
    Endpoint(std::shared_ptr<driver_probe::CallbackCounts> counts, CallbackAction action)
        : Object(__uuidof(IMMNotificationClient)), counts_(std::move(counts)), action_(action) { ++counts_->live; }
    HRESULT STDMETHODCALLTYPE OnDeviceStateChanged(LPCWSTR, DWORD) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnDeviceAdded(LPCWSTR) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnDeviceRemoved(LPCWSTR) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnDefaultDeviceChanged(EDataFlow, ERole, LPCWSTR) override { action_(); return S_OK; }
    HRESULT STDMETHODCALLTYPE OnPropertyValueChanged(LPCWSTR, const PROPERTYKEY) override { return S_OK; }
private:
    ~Endpoint() override { --counts_->live; }
    std::shared_ptr<driver_probe::CallbackCounts> counts_;
    CallbackAction action_;
};
class Session final : public Object<IAudioSessionEvents> {
public:
    Session(std::shared_ptr<driver_probe::CallbackCounts> counts, CallbackAction action,
        std::shared_ptr<bool> destroyed, ComPtr<IAudioClient> retained)
        : Object(__uuidof(IAudioSessionEvents)), counts_(std::move(counts)), action_(action),
          destroyed_(std::move(destroyed)), retained_(std::move(retained)) { ++counts_->live; }
    HRESULT STDMETHODCALLTYPE OnDisplayNameChanged(LPCWSTR, LPCGUID) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnIconPathChanged(LPCWSTR, LPCGUID) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnSimpleVolumeChanged(float, BOOL, LPCGUID) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnChannelVolumeChanged(DWORD, float[], DWORD, LPCGUID) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnGroupingParamChanged(LPCGUID, LPCGUID) override { return S_OK; }
    HRESULT STDMETHODCALLTYPE OnStateChanged(AudioSessionState) override { action_(); return S_OK; }
    HRESULT STDMETHODCALLTYPE OnSessionDisconnected(AudioSessionDisconnectReason) override { return S_OK; }
private:
    ~Session() override { *destroyed_ = true; --counts_->live; }
    std::shared_ptr<driver_probe::CallbackCounts> counts_;
    CallbackAction action_;
    std::shared_ptr<bool> destroyed_;
    ComPtr<IAudioClient> retained_;
};
}
ComPtr<IMMNotificationClient> MemoryEndpoint(const std::shared_ptr<driver_probe::CallbackCounts>& counts, CallbackAction action) {
    return Make<IMMNotificationClient, Endpoint>(counts, action);
}
ComPtr<IAudioSessionEvents> MemorySession(const std::shared_ptr<driver_probe::CallbackCounts>& counts, CallbackAction action,
    std::shared_ptr<bool> destroyed, ComPtr<IAudioClient> retained) {
    return Make<IAudioSessionEvents, Session>(counts, action, std::move(destroyed), std::move(retained));
}
