#include "DeviceSnapshot.h"
#include <fstream>
#include <iostream>

namespace {
using namespace driver_probe;
class Physical final : public activation::Provider {
public:
    explicit Physical(Trace& value):trace_(value) {}
    HRESULT CreateCom(REFCLSID clsid,LPUNKNOWN outer,DWORD context,REFIID iid,void** output) override {
        const HRESULT result=CoCreateInstance(clsid,outer,context,iid,output);
        trace_.Call("provider.CoCreateInstance",result); return result;
    }
    HRESULT CreateDirectSound(LPCGUID device,LPDIRECTSOUND8* output,LPUNKNOWN outer) override {
        const HRESULT result=DirectSoundCreate8(device,output,outer);
        trace_.Call("provider.DirectSoundCreate8",result); return result;
    }
    // This exception stays on the owned outbound C++ stack. It is not a stock abort mechanism.
    [[noreturn]] void Abort(HRESULT code,const char* stage) override {
        trace_.Call(stage,code); throw Failure(code,stage);
    }
private:
    Trace& trace_;
};
class Apartment {
public:
    explicit Apartment(Trace& trace) { Check(trace,"CoInitializeEx.STA",CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED)); }
    ~Apartment() { CoUninitialize(); }
};
int Probe(const std::filesystem::path& path) {
    Trace trace;
    bool passed=true,canUnload=false,unchanged=false;
    unsigned wasapiStarts=0,soundStarts=0;
    std::string before="null",after="null";
    try {
        Apartment apartment(trace);
        before=DeviceSnapshot(trace);
        {
            auto provider=std::make_shared<Physical>(trace);
            activation::Boundary boundary(provider);
            for(unsigned generation=1;generation<=2;++generation) {
                trace.generation=generation;
                const bool complete=RunWasapi(boundary,trace,nullptr,true);
                passed &= complete;
                if(!complete) break;
                ++wasapiStarts;
                if(!boundary.CanUnload()) { passed=false; break; }
            }
            for(unsigned generation=1;generation<=2;++generation) {
                trace.generation=generation;
                const bool complete=RunDirectSound(boundary,trace,Wave(WAVE_FORMAT_PCM,16),true);
                passed &= complete;
                if(!complete) break;
                ++soundStarts;
                if(!boundary.CanUnload()) { passed=false; break; }
            }
            canUnload=boundary.CanUnload(); passed &= canUnload;
            trace.Fact("boundary.canUnload",canUnload ? "true" : "false");
        }
        trace.generation=0;
        after=DeviceSnapshot(trace);
        unchanged=before==after;
        passed &= unchanged && wasapiStarts==2 && soundStarts==2;
    } catch(const Failure& error) { passed=false; trace.Call(error.what(),error.code); }
      catch(const std::exception& error) { passed=false; trace.Fact("owned.exception",Quote(error.what())); }
    std::ofstream out(path,std::ios::binary);
    if(!out) return 2;
    out<<"{\n  \"schema\":1,\n  \"scope\":\"Owned silent streams on current default routes. No BO3 or first-output coverage claim.\",\n";
    out<<"  \"physicalPayload\":\"Format-correct silence only. No nonzero physical baseline.\",\n";
    out<<"  \"passed\":"<<(passed ? "true" : "false")<<",\n  \"wasapiCompletedGenerations\":"<<wasapiStarts<<",\n  \"directSoundCompletedGenerations\":"<<soundStarts<<",\n";
    out<<"  \"boundaryCanUnload\":"<<(canUnload ? "true" : "false")<<",\n  \"endpointControlsAndDefaultsUnchanged\":"<<(unchanged ? "true" : "false")<<",\n";
    out<<"  \"before\":"<<before<<",\n  \"after\":"<<after<<",\n  \"events\":[\n";
    for(size_t index=0;index<trace.events.size();++index) out<<"    "<<trace.events[index]<<(index+1<trace.events.size() ? "," : "")<<'\n';
    out<<"  ]\n}\n";
    if(!out) return 2;
    return passed ? 0 : 1;
}
}
int wmain(int argc,wchar_t** argv) {
    if(!driver_probe::ExplicitPhysicalMode(argc,argv)) {
        std::wcerr<<L"Use --physical-silent and a new private evidence path. No hardware was opened.\n";
        return 2;
    }
    try { return Probe(driver_probe::EvidencePath(argv[2])); }
    catch(const std::exception& error) { std::cerr<<error.what()<<'\n'; return 2; }
}
