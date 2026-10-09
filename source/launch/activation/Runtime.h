#pragma once
#include "ActivationBoundary.h"
#include <wrl/client.h>
#include <atomic>
#include <mutex>
#include <unordered_map>

namespace activation {
using Microsoft::WRL::ComPtr;
enum class Kind { Enumerator, Device, Audio, DirectSound, SoundBuffer };
class Node;
class Runtime final : public std::enable_shared_from_this<Runtime> {
public:
    explicit Runtime(std::shared_ptr<Provider> value) : provider(std::move(value)) {}
    HRESULT Wrap(IUnknown* raw, Kind kind, REFIID iid, void** output);
    [[noreturn]] void Abort(HRESULT code, const char* stage);
    bool CanUnload() const;
    std::shared_ptr<Provider> provider;
    std::atomic<unsigned> activeCalls{0};
private:
    friend class Node;
    mutable std::mutex mutex_;
    // Weak entries. Live nodes own the runtime, not the other way around.
    struct Entry { Kind kind; Node* node; };
    std::unordered_map<IUnknown*, Entry> nodes_;
    unsigned liveNodes_ = 0;
};
class Activity {
public:
    explicit Activity(Runtime& runtime) : runtime_(runtime) { ++runtime_.activeCalls; }
    ~Activity() { --runtime_.activeCalls; }
private:
    Runtime& runtime_;
};
class Node {
public:
    Node(std::shared_ptr<Runtime> runtime, IUnknown* identity);
    virtual ~Node();
    ULONG AddRef();
    ULONG Release();
    virtual HRESULT QueryKnown(REFIID iid, void** output) = 0;
protected:
    std::shared_ptr<Runtime> runtime_;
    ComPtr<IUnknown> identity_;
private:
    std::atomic<ULONG> references_{1};
};
std::unique_ptr<Node> MakeEndpointNode(const std::shared_ptr<Runtime>& runtime, IUnknown* identity, Kind kind);
std::unique_ptr<Node> MakeAudioNode(const std::shared_ptr<Runtime>& runtime, IUnknown* identity, HRESULT& result);
std::unique_ptr<Node> MakeDirectSoundNode(const std::shared_ptr<Runtime>& runtime, IUnknown* identity);
std::unique_ptr<Node> MakeSoundNode(const std::shared_ptr<Runtime>& runtime, IUnknown* identity, HRESULT& result);
}
