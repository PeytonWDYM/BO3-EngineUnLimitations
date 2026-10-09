#include "Harness.h"
#include <cstring>

namespace activation_test {
void WasapiScenarios(fixture::Report& report) {
    Run(report, "known-wasapi-first-output-order", [](fixture::Scenario& test, State& state, Harness& harness) {
        bool activeFactoryBlocksUnload = false;
        state.reenterRoot = [&] { activeFactoryBlocksUnload = !harness.CanUnload(); };
        auto chain = CreateChain(harness, state);
        UINT32 capacity = 0, padding = 1;
        Ok(chain.client->GetBufferSize(&capacity));
        Ok(chain.client->GetCurrentPadding(&padding));
        BYTE* samples = nullptr;
        Ok(chain.render->GetBuffer(8, &samples));
        memset(samples, 0x41, 64);
        Ok(chain.render->ReleaseBuffer(8, AUDCLNT_BUFFERFLAGS_SILENT));
        Ok(chain.client->Start());
        Render(chain.render.Get(), state, chain.generation);
        Ok(chain.client->Stop());
        const auto& packets = state.generations.back()->render->packets;
        test.Number("initialFlags", packets.front().flags);
        test.Number("ordinaryFlags", packets.back().flags);
        test.String("ordinaryOutputHex", fixture::Hex(packets.back().bytes));
        test.Boolean("activeFirstFactoryBlocksUnload", activeFactoryBlocksUnload);
        Require(activeFactoryBlocksUnload && capacity == 8 && padding == 0 && packets.front().silent && packets.back().silent, "The first ordinary packet or factory lifetime is unsafe");
    });
    Run(report, "repeated-roots-devices-and-separate-service-identities", [](fixture::Scenario& test, State& state, Harness& harness) {
        auto chain = CreateChain(harness, state);
        ComPtr<IMMDeviceEnumerator> root;
        Ok(harness.CreateCom(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), reinterpret_cast<void**>(root.GetAddressOf())));
        ComPtr<IMMDevice> device;
        Ok(root->GetDefaultAudioEndpoint(eRender, eConsole, &device));
        ComPtr<IAudioRenderClient> render;
        ComPtr<IAudioSessionControl> session;
        Ok(chain.client->GetService(__uuidof(IAudioRenderClient), reinterpret_cast<void**>(render.GetAddressOf())));
        Ok(chain.client->GetService(__uuidof(IAudioSessionControl), reinterpret_cast<void**>(session.GetAddressOf())));
        Publish(state, render.Get(), "render", chain.generation);
        test.Boolean("sameRoot", SameIdentity(root.Get(), chain.enumerator.Get()));
        test.Boolean("sameDevice", SameIdentity(device.Get(), chain.device.Get()));
        test.Boolean("sameRepeatedRender", SameIdentity(render.Get(), chain.render.Get()));
        test.Boolean("sameRepeatedSession", SameIdentity(session.Get(), chain.session.Get()));
        test.Boolean("distinctServiceFamilies", !SameIdentity(render.Get(), chain.client.Get()) && !SameIdentity(session.Get(), chain.client.Get()) && !SameIdentity(render.Get(), session.Get()));
        Require(SameIdentity(root.Get(), chain.enumerator.Get()) && SameIdentity(device.Get(), chain.device.Get()) && SameIdentity(render.Get(), chain.render.Get()) && SameIdentity(session.Get(), chain.session.Get()), "Repeated factory identity changed");
        Require(!SameIdentity(render.Get(), session.Get()) && !SameIdentity(render.Get(), chain.client.Get()), "Separate provider identities merged");
        Render(render.Get(), state, chain.generation);
    });
    Run(report, "shared-family-static-queryinterface", [](fixture::Scenario& test, State& state, Harness& harness) {
        state.sharedIdentity = true;
        auto chain = CreateChain(harness, state, false);
        ComPtr<IAudioRenderClient> early;
        ComPtr<IAudioSessionControl> earlySession;
        Ok(chain.client.As(&early));
        Ok(early.As(&earlySession));
        BYTE* pointer = nullptr;
        Require(early->GetBuffer(1, &pointer) == AUDCLNT_E_NOT_INITIALIZED, "Early render initialization error changed");
        void* unsupported = reinterpret_cast<void*>(1);
        const HRESULT before = chain.client->QueryInterface(fixture::EscapeId, &unsupported);
        if (SUCCEEDED(before)) static_cast<IUnknown*>(unsupported)->Release();
        Initialize(chain.client.Get());
        Ok(chain.client->GetService(__uuidof(IAudioRenderClient), reinterpret_cast<void**>(chain.render.GetAddressOf())));
        Ok(chain.client->GetService(__uuidof(IAudioSessionControl), reinterpret_cast<void**>(chain.session.GetAddressOf())));
        Publish(state, chain.render.Get(), "render", chain.generation);
        ComPtr<IAudioClient> roundTrip;
        Ok(chain.session.As(&roundTrip));
        unsupported = reinterpret_cast<void*>(1);
        const HRESULT after = chain.render->QueryInterface(fixture::EscapeId, &unsupported);
        if (SUCCEEDED(after)) static_cast<IUnknown*>(unsupported)->Release();
        const bool identity = SameIdentity(chain.client.Get(), chain.render.Get()) && SameIdentity(chain.render.Get(), chain.session.Get()) && SameIdentity(roundTrip.Get(), chain.client.Get());
        test.Boolean("sharedIdentity", identity);
        test.String("unknownBefore", fixture::Hresult(before));
        test.String("unknownAfter", fixture::Hresult(after));
        Render(early.Get(), state, chain.generation);
        Require(identity && before == E_NOINTERFACE && after == E_NOINTERFACE, "COM family identity or static IID set changed");
    });
    Run(report, "two-live-generations-services-survive-parent", [](fixture::Scenario& test, State& state, Harness& harness) {
        auto first = CreateChain(harness, state);
        auto second = CreateChain(harness, state);
        Require(first.generation != second.generation && !SameIdentity(first.client.Get(), second.client.Get()), "Recreated client reused an old generation");
        first.client.Reset(); second.client.Reset();
        first.device.Reset(); second.device.Reset();
        first.enumerator.Reset(); second.enumerator.Reset();
        Render(first.render.Get(), state, first.generation);
        Render(second.render.Get(), state, second.generation);
        const bool liveBlocked = !harness.CanUnload();
        first.render.Reset(); second.render.Reset(); first.session.Reset(); second.session.Reset();
        test.Boolean("liveServicesBlockUnload", liveBlocked);
        test.Boolean("emptyBoundaryAllowsUnload", harness.CanUnload());
        test.Boolean("bothGenerationsSilent", state.generations[0]->render->packets.back().silent && state.generations[1]->render->packets.back().silent);
        Require(liveBlocked && harness.CanUnload() && state.generations[0]->render->packets.back().silent && state.generations[1]->render->packets.back().silent, "Outstanding service lifetime failed");
    });
    Run(report, "endpoint-callback-reentrancy-and-recreation", [](fixture::Scenario& test, State& state, Harness& harness) {
        auto chain = CreateChain(harness, state);
        unsigned callbacks = 0;
        auto callback = Make<IMMNotificationClient, EndpointCallback>([&] {
            ++callbacks;
            auto recreated = CreateChain(harness, state);
            Render(recreated.render.Get(), state, recreated.generation);
        });
        state.callbackExpectedThread = GetCurrentThreadId();
        Ok(chain.enumerator->RegisterEndpointNotificationCallback(callback.Get()));
        const bool sameCallback = state.lastEndpointCallback == callback.Get();
        state.NotifyEndpoint();
        state.reenter = [&] {
            auto nested = CreateChain(harness, state);
            Render(nested.render.Get(), state, nested.generation);
        };
        ComPtr<IMMDevice> repeated;
        Ok(chain.enumerator->GetDefaultAudioEndpoint(eRender, eConsole, &repeated));
        Ok(chain.enumerator->UnregisterEndpointNotificationCallback(callback.Get()));
        test.Number("callbacks", callbacks);
        test.Boolean("callbackIdentityPreserved", sameCallback);
        test.Boolean("callbackThreadPreserved", state.callbackThread == state.callbackExpectedThread);
        test.Number("registers", state.endpointRegisters);
        test.Number("unregisters", state.endpointUnregisters);
        Require(callbacks == 1 && sameCallback && state.callbackThread == state.callbackExpectedThread && state.generations.size() == 3 && state.endpointCallbacks.empty(), "Endpoint callback or reentrant recreation changed");
    });
    Run(report, "session-callback-identity-counts-thread-and-lifetime", [](fixture::Scenario& test, State& state, Harness& harness) {
        auto chain = CreateChain(harness, state);
        auto generation = state.generations.back();
        unsigned callbacks = 0;
        auto destroyed = std::make_shared<bool>(false);
        auto callback = Make<IAudioSessionEvents, SessionCallback>([&] {
            ++callbacks;
            ComPtr<IMMDeviceEnumerator> root;
            Ok(harness.CreateCom(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), reinterpret_cast<void**>(root.GetAddressOf())));
        }, destroyed, chain.client);
        auto* identity = callback.Get();
        state.sessionRegisterResult = S_FALSE;
        const HRESULT first = chain.session->RegisterAudioSessionNotification(identity);
        const HRESULT teardownRegister = chain.session->RegisterAudioSessionNotification(identity);
        callback.Reset();
        state.callbackExpectedThread = GetCurrentThreadId();
        state.NotifySession(generation);
        chain.client.Reset(); chain.render.Reset(); chain.device.Reset(); chain.enumerator.Reset();
        const bool retained = !*destroyed && !harness.CanUnload();
        Ok(chain.session->UnregisterAudioSessionNotification(identity));
        Ok(chain.session->UnregisterAudioSessionNotification(identity));
        chain.session.Reset();
        test.Number("callbackCalls", callbacks);
        test.Number("registers", generation->sessionRegisters);
        test.Number("unregisters", generation->sessionUnregisters);
        test.Boolean("identityPreserved", state.lastSessionCallback == identity);
        test.Boolean("callbackThreadPreserved", state.callbackThread == state.callbackExpectedThread);
        test.Boolean("callbackHeldClient", retained);
        test.Boolean("callbackDestroyedAfterUnregister", *destroyed);
        test.String("registrationResult", fixture::Hresult(first));
        Require(first == S_FALSE && teardownRegister == S_FALSE && callbacks == 2 && retained && *destroyed && harness.CanUnload() && generation->sessionRegisters == 2 && generation->sessionUnregisters == 2, "Session callback contract changed");
    });
}
}
