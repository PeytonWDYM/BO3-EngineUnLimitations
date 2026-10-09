#pragma once
#include "../quiet/Fixture.h"
#include <mmdeviceapi.h>
#include <audiopolicy.h>
#include <functional>

namespace activation_test {
using fixture::ComPtr;
using fixture::Ok;
using fixture::Require;
struct Stopped final : std::exception {
    HRESULT code;
    explicit Stopped(HRESULT value) : code(value) {}
    const char* what() const noexcept override { return "Owned consumer stopped"; }
};
struct Generation {
    unsigned id;
    std::shared_ptr<fixture::RenderState> render = std::make_shared<fixture::RenderState>();
    std::shared_ptr<fixture::SoundState> sound;
    bool initialized = false;
    bool started = false;
    HANDLE event = nullptr;
    std::vector<ComPtr<IAudioSessionEvents>> callbacks;
    unsigned sessionRegisters = 0;
    unsigned sessionUnregisters = 0;
};
struct State {
    bool sharedIdentity = false;
    bool buffer8 = true;
    bool returnSameEnumerator = true;
    bool failAdapterAllocation = false;
    HRESULT rootError = S_OK;
    HRESULT activateError = S_OK;
    HRESULT initializeError = S_OK;
    HRESULT serviceError = S_OK;
    HRESULT bufferError = S_OK;
    HRESULT clearError = S_OK;
    HRESULT sessionRegisterResult = S_OK;
    bool unsafeBranchReached = false;
    unsigned rawPublications = 0;
    unsigned aborts = 0;
    unsigned nextId = 1;
    unsigned endpointRegisters = 0;
    unsigned endpointUnregisters = 0;
    DWORD callbackThread = 0;
    DWORD callbackExpectedThread = 0;
    IAudioSessionEvents* lastSessionCallback = nullptr;
    IMMNotificationClient* lastEndpointCallback = nullptr;
    std::function<void()> reenter;
    std::function<void()> reenterRoot;
    std::vector<std::string> events;
    std::vector<std::shared_ptr<Generation>> generations;
    std::vector<ComPtr<IMMNotificationClient>> endpointCallbacks;
    void Event(const std::string& name, unsigned generation = 0);
    std::shared_ptr<Generation> NewGeneration();
    void NotifyEndpoint();
    void NotifySession(const std::shared_ptr<Generation>& generation);
};
class MemoryProvider {
public:
    explicit MemoryProvider(std::shared_ptr<State> state);
    HRESULT CreateCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output);
    HRESULT CreateDirectSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer);
    [[noreturn]] void Abort(HRESULT code, const char* stage);
    std::shared_ptr<State> state;
private:
    ComPtr<IMMDeviceEnumerator> enumerator_;
};
ComPtr<IMMDeviceEnumerator> MakeEnumerator(const std::shared_ptr<State>& state);
ComPtr<IAudioClient> MakeClient(const std::shared_ptr<State>& state, const std::shared_ptr<Generation>& generation);
ComPtr<IDirectSound8> MakeDirectSound(const std::shared_ptr<State>& state);
bool SameIdentity(IUnknown* first, IUnknown* second);
bool IsRaw(IUnknown* value);
void Publish(State& state, IUnknown* value, const char* type, unsigned generation);
extern thread_local bool FailNextAllocation;
}
