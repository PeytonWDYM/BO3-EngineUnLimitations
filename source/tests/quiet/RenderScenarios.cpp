#include "Fixture.h"
#include <cstring>

namespace fixture {
void RenderScenarios(Report& report) {
    report.Run("wasapi-first-nonzero-packet", [](Scenario& test) {
        auto state = std::make_shared<RenderState>();
        auto sink = MakeRender(state);
        ComPtr<IAudioRenderClient> caller;
        Ok(RenderBoundary(sink.Get(), &caller));
        BYTE* samples = nullptr;
        Ok(caller->GetBuffer(4, &samples));
        memset(samples, 0x3f, 32);
        Ok(caller->ReleaseBuffer(4, 0));
        test.Number("firstFrames", state->packets.front().frames);
        test.Number("firstFlags", state->packets.front().flags);
        test.String("firstOutputHex", Hex(state->packets.front().bytes));
        test.Boolean("silent", state->packets.front().silent);
        Require(state->packets.front().silent, "First packet contains nonzero output");
    });
    report.Run("wasapi-eight-channels-repeated-and-zero-frames", [](Scenario& test) {
        auto state = std::make_shared<RenderState>();
        state->channels = 8;
        auto sink = MakeRender(state);
        ComPtr<IAudioRenderClient> caller;
        Ok(RenderBoundary(sink.Get(), &caller));
        BYTE sentinel = 0;
        BYTE* samples = &sentinel;
        Ok(caller->GetBuffer(0, &samples));
        Require(samples == &sentinel, "Zero-frame GetBuffer changed the pointer");
        Ok(caller->ReleaseBuffer(0, 0));
        for (unsigned index = 0; index < 64; ++index) {
            Ok(caller->GetBuffer(8, &samples));
            memset(samples, 0x7f, 8 * 8 * 4);
            Ok(caller->ReleaseBuffer(8, index % 2 ? AUDCLNT_BUFFERFLAGS_SILENT : 0));
        }
        const bool silent = std::all_of(state->packets.begin(), state->packets.end(), [](const Packet& packet) { return packet.silent; });
        test.Number("channels", state->channels);
        test.Number("packets", static_cast<unsigned>(state->packets.size()));
        test.Boolean("allSilent", silent);
        Require(silent, "A repeated packet contains nonzero output");
    });
    report.Run("wasapi-errors-and-retry", [](Scenario& test) {
        auto state = std::make_shared<RenderState>();
        auto sink = MakeRender(state);
        ComPtr<IAudioRenderClient> caller;
        Ok(RenderBoundary(sink.Get(), &caller));
        const HRESULT order = caller->ReleaseBuffer(1, 0);
        Require(order == AUDCLNT_E_OUT_OF_ORDER, "Release order error changed");
        state->getError = AUDCLNT_E_DEVICE_INVALIDATED;
        BYTE* samples = nullptr;
        Require(caller->GetBuffer(2, &samples) == state->getError, "GetBuffer error changed");
        state->getError = S_OK;
        Ok(caller->GetBuffer(2, &samples));
        memset(samples, 0x22, 16);
        Require(caller->ReleaseBuffer(3, 0) == AUDCLNT_E_INVALID_SIZE, "Size error changed");
        Require(caller->ReleaseBuffer(2, 0x4) == E_INVALIDARG, "Invalid flags became valid");
        state->releaseError = AUDCLNT_E_DEVICE_INVALIDATED;
        const HRESULT failure = caller->ReleaseBuffer(2, 0);
        Require(failure == state->releaseError && state->pending, "Release failure lost the pending packet");
        state->releaseError = S_OK;
        Ok(caller->ReleaseBuffer(2, 0));
        Require(caller->ReleaseBuffer(2, 0) == AUDCLNT_E_OUT_OF_ORDER, "Repeated release succeeded");
        test.String("orderError", Hresult(order));
        test.String("underlyingError", Hresult(failure));
        test.Boolean("retrySilent", state->packets.back().silent);
        Require(state->packets.back().silent, "Successful retry contains nonzero output");
    });
    report.Run("wasapi-identity-escape-and-lifetime", [](Scenario& test) {
        auto state = std::make_shared<RenderState>();
        auto sink = MakeRender(state);
        ComPtr<IAudioRenderClient> caller;
        Ok(RenderBoundary(sink.Get(), &caller));
        sink.Reset();
        ComPtr<IUnknown> identity;
        ComPtr<IAudioRenderClient> alias;
        Ok(caller.As(&identity));
        Ok(identity.As(&alias));
        ComPtr<IUnknown> other;
        Ok(alias.As(&other));
        const bool same = identity.Get() == other.Get();
        void* escape = reinterpret_cast<void*>(1);
        const HRESULT escapeResult = caller->QueryInterface(EscapeId, &escape);
        const bool blocked = escapeResult == E_NOINTERFACE && escape == nullptr;
        if (SUCCEEDED(escapeResult)) static_cast<IUnknown*>(escape)->Release();
        test.Boolean("sameIdentity", same);
        test.String("escapeHRESULT", Hresult(escapeResult));
        test.Boolean("escapeBlocked", blocked);
        other.Reset(); alias.Reset(); identity.Reset();
        const ULONG increased = caller->AddRef();
        const ULONG decreased = caller->Release();
        test.Number("addRef", increased);
        test.Number("release", decreased);
        caller.Reset();
        test.Boolean("sinkDestroyed", state->destroyed);
        Require(same && increased == 2 && decreased == 1 && state->destroyed, "COM identity or lifetime failed");
        Require(blocked, "Unknown interface escaped the boundary");
    });
}
}
