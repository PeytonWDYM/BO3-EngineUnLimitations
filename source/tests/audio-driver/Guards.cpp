#include "Probe.h"
#include "../activation/Providers.h"
#include <iostream>

namespace activation_test { thread_local bool FailNextAllocation = false; }
namespace {
using namespace driver_probe;
using fixture::Require;
class Memory final : public activation::Provider {
public:
    explicit Memory(std::shared_ptr<activation_test::State> state) : provider(std::move(state)) {}
    HRESULT CreateCom(REFCLSID a, LPUNKNOWN b, DWORD c, REFIID d, void** e) override { return provider.CreateCom(a,b,c,d,e); }
    HRESULT CreateDirectSound(LPCGUID a, LPDIRECTSOUND8* b, LPUNKNOWN c) override { return provider.CreateDirectSound(a,b,c); }
    [[noreturn]] void Abort(HRESULT code, const char* stage) override { provider.Abort(code, stage); }
    activation_test::MemoryProvider provider;
};
struct Harness {
    std::shared_ptr<activation_test::State> state = std::make_shared<activation_test::State>();
    std::shared_ptr<Memory> provider = std::make_shared<Memory>(state);
    activation::Boundary boundary{provider};
    Trace trace;
    Harness() { trace.publication = [this](IUnknown* object) { state->rawPublications += activation_test::IsRaw(object) ? 1 : 0; }; }
    void Closed(fixture::Scenario& test, const std::string& prefix = "") {
        Require(boundary.CanUnload(), "A wrapped adapter remains live");
        Require(!state->rawPublications, "A raw output reached the consumer");
        Require(state->endpointCallbacks.empty(), "An endpoint callback remains registered");
        for (const auto& generation : state->generations) {
            Require(!generation->started && generation->callbacks.empty(), "A stream or callback remains active");
            if (generation->sound) Require(!generation->sound->playing && generation->sound->destroyed, "A sound buffer remains active");
            else Require(generation->render->destroyed, "A render leaf remains live");
        }
        Require(!state->unsafeBranchReached, "The unsafe output branch ran");
        test.Boolean(prefix+"canUnload", true);
        test.Number(prefix+"rawPublications", state->rawPublications);
        test.Number(prefix+"generations", static_cast<unsigned>(state->generations.size()));
        std::string events = "[";
        for (size_t i = 0; i < trace.events.size(); ++i) { if (i) events += ','; events += trace.events[i]; }
        test.evidence.emplace_back(prefix+"consumerEvents", events + ']');
    }
    void NoStart() {
        for (const auto& event : state->events)
            Require(event.find("provider.client.start:") == std::string::npos && event.find("provider.buffer.play:") == std::string::npos, "Preparation failure reached Start or Play");
    }
};
void Wasapi(fixture::Report& report, const char* name, const std::function<void(Harness&)>& prepare, bool expected) {
    report.Run(name, [&](fixture::Scenario& test) {
        Harness harness; prepare(harness);
        Require(RunWasapi(harness.boundary, harness.trace) == expected, "Unexpected WASAPI result");
        if (!expected) harness.NoStart();
        else {
            Require(harness.state->generations.size() == 1, "Wrong stream generation count");
            const auto& generation = harness.state->generations.front();
            Require(generation->render->packets.size() == 1 && generation->render->packets.front().silent, "The first render packet was not silent");
            Require(generation->sessionRegisters == 1 && generation->sessionUnregisters == 1, "Session callback cleanup changed");
        }
        harness.Closed(test);
    });
}
}
int wmain(int argc, wchar_t** argv) {
    if (argc != 2) return 2;
    const auto path = driver_probe::EvidencePath(argv[1]);
    fixture::Report report;
    Wasapi(report, "wrapped first WASAPI packet and callbacks", [](Harness&) {}, true);
    Wasapi(report, "factory failure stops before output", [](Harness& h) { h.state->rootError = E_ACCESSDENIED; }, false);
    Wasapi(report, "activation failure stops before output", [](Harness& h) { h.state->activateError = E_FAIL; }, false);
    Wasapi(report, "initialize failure releases event and adapters", [](Harness& h) { h.state->initializeError = AUDCLNT_E_UNSUPPORTED_FORMAT; }, false);
    Wasapi(report, "service failure stops before Start", [](Harness& h) { h.state->serviceError = E_NOINTERFACE; }, false);
    Wasapi(report, "callback registration failure stops before Start", [](Harness& h) { h.state->sessionRegisterResult = E_FAIL; }, false);
    report.Run("all admitted formats submit format-correct silence", [](fixture::Scenario& test) {
        for (const auto& format : {Wave(WAVE_FORMAT_PCM,8), Wave(WAVE_FORMAT_PCM,16), Wave(WAVE_FORMAT_IEEE_FLOAT,32)}) {
            Harness h;
            Require(RunWasapi(h.boundary,h.trace,&format), "Supported WASAPI format failed");
            const auto& memory = h.state->generations.front()->render->memory;
            const size_t bytes = 8 * format.nBlockAlign;
            const BYTE zero = format.wBitsPerSample == 8 ? 0x80 : 0;
            Require(std::all_of(memory.begin(),memory.begin()+bytes,[=](BYTE value) { return value == zero; }), "Caller payload contains a nonzero sample");
            Require(RunDirectSound(h.boundary,h.trace,format), "Supported DirectSound format failed");
            const auto& sound = h.state->generations.back()->sound;
            Require(fixture::IsSilent(*sound) && !sound->outputs.empty() && std::all_of(sound->outputs.begin(),sound->outputs.end(),[](bool silent) { return silent; }), "Sound sink received a nonzero sample");
            h.Closed(test,"format"+std::to_string(format.wBitsPerSample)+'.');
        }
        test.String("PCM8", "0x80"); test.String("PCM16-and-float32", "0x00");
    });
    report.Run("unsupported and malformed formats stop before Initialize or Play", [](fixture::Scenario& test) {
        std::vector<WAVEFORMATEX> rejected{Wave(WAVE_FORMAT_PCM,24),Wave(WAVE_FORMAT_IEEE_FLOAT,64),Wave(WAVE_FORMAT_PCM,16)};
        rejected.back().nBlockAlign = 1;
        for (const auto& format : rejected) {
            Harness h;
            Require(!RunWasapi(h.boundary,h.trace,&format) && !RunDirectSound(h.boundary,h.trace,format), "Invalid format was admitted");
            h.NoStart();
            for (const auto& event : h.state->events) Require(event.find("provider.client.initialize:") == std::string::npos, "Invalid format reached Initialize");
            h.Closed(test,"rejected"+std::to_string(format.wBitsPerSample)+'.');
        }
    });
    report.Run("DirectSound private Buffer8 failure never returns raw fallback", [](fixture::Scenario& test) {
        Harness h; h.state->buffer8 = false;
        Require(!RunDirectSound(h.boundary,h.trace,Wave(WAVE_FORMAT_PCM,16)), "Unsupported Buffer8 succeeded");
        Require(h.state->aborts == 1, "Controlled abort did not run"); h.NoStart(); h.Closed(test);
    });
    report.Run("DirectSound clear failure stops before Play", [](fixture::Scenario& test) {
        Harness h; h.state->clearError = DSERR_BUFFERLOST;
        Require(!RunDirectSound(h.boundary,h.trace,Wave(WAVE_FORMAT_PCM,16)), "Failed clear succeeded");
        Require(h.state->aborts == 1, "Controlled abort did not run"); h.NoStart(); h.Closed(test);
    });
    report.Run("recreated streams and split buffers retain silence and cleanup", [](fixture::Scenario& test) {
        Harness h;
        for (unsigned i=0;i<2;++i) {
            h.trace.generation=i+1;
            Require(RunWasapi(h.boundary,h.trace) && RunDirectSound(h.boundary,h.trace,Wave(WAVE_FORMAT_PCM,16)), "Recreation failed");
            Require(h.boundary.CanUnload(), "Generation retained an adapter");
        }
        Require(h.state->generations.size()==4, "Recreation did not use new generations");
        for (const auto& g:h.state->generations) if(g->sound) Require(fixture::IsSilent(*g->sound), "Split buffer was not silent");
        h.Closed(test);
    });
    report.Run("physical mode requires exact explicit arguments", [](fixture::Scenario& test) {
        const wchar_t* absent[] = {L"probe.exe"};
        const wchar_t* wrong[] = {L"probe.exe",L"--physical",L"report.json"};
        const wchar_t* valid[] = {L"probe.exe",L"--physical-silent",L"report.json"};
        Require(!ExplicitPhysicalMode(1,absent) && !ExplicitPhysicalMode(3,wrong) && ExplicitPhysicalMode(3,valid), "Physical mode admission changed");
        test.Boolean("hardwareProviderLinked",false);
    });
    return report.Write(path.string().c_str(),false);
}
