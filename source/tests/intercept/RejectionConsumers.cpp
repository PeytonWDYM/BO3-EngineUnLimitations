#include "Consumer.h"
#include "MemoryCallbacks.h"

namespace {
class AggregationObject final : public IUnknown {
public:
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void** output) override {
        *output=nullptr;
        if(iid!=IID_IUnknown) return E_NOINTERFACE;
        *output=static_cast<IUnknown*>(this); return S_OK;
    }
    ULONG STDMETHODCALLTYPE AddRef() override { return 1; }
    ULONG STDMETHODCALLTYPE Release() override { return 1; }
};
void RejectCom() noexcept {
    const auto scenario=SdkTrace()->scenario;
    AggregationObject aggregate;
    void* output=scenario==Scenario::ContainedOutput ? &aggregate : nullptr;
    const CLSID& clsid=scenario==Scenario::ContainedClass ? CLSID_DirectSound8 : __uuidof(MMDeviceEnumerator);
    const IID& iid=scenario==Scenario::ContainedIid ? IID_IUnknown : __uuidof(IMMDeviceEnumerator);
    SdkRecord(Stage::RejectionRequested,Api::Com,0,output ? 1 : 0,&clsid,&iid);
    CoCreateInstance(clsid,scenario==Scenario::ContainedAggregation ? &aggregate : nullptr,
        scenario==Scenario::ContainedContext ? CLSCTX_INPROC_SERVER : CLSCTX_ALL,iid,
        scenario==Scenario::ContainedNullOutput ? nullptr : &output);
    ConsumerStop(E_UNEXPECTED);
}
DWORD WINAPI OtherAudioThread(LPVOID) {
    ConsumerGood(CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED));
    IMMDeviceEnumerator* root=nullptr;
    ConsumerGood(CoCreateInstance(__uuidof(MMDeviceEnumerator),nullptr,CLSCTX_ALL,__uuidof(IMMDeviceEnumerator),
        reinterpret_cast<void**>(&root)));
    SdkObserve(root,Api::Com,0);
    root->Release();
    InterlockedIncrement(&SdkTrace()->otherThreadWrapped);
    SdkRecord(Stage::OtherThreadWrapped,Api::Com,0,S_OK,nullptr,nullptr);
    CoUninitialize();
    return 0;
}
}
// The helper resolves this fixed export only in owned memory rejection scenarios.
extern "C" __declspec(dllexport) void WINAPI SdkRejectNested() {
    ConsumerCheck(SdkTrace()->mode==Mode::Memory);
    if(SdkTrace()->scenario==Scenario::ContainedThread) {
        DWORD id=0;
        const HANDLE thread=CreateThread(nullptr,0,OtherAudioThread,nullptr,0,&id);
        ConsumerCheck(thread && id && WaitForSingleObject(thread,10000)==WAIT_OBJECT_0);
        DWORD result=1;
        ConsumerCheck(GetExitCodeThread(thread,&result) && result==0 && CloseHandle(thread));
        return;
    }
    if(SdkTrace()->scenario==Scenario::ContainedCallback) {
        auto counts=std::make_shared<driver_probe::CallbackCounts>();
        auto callback=MemoryEndpoint(counts,RejectCom);
        callback->OnDefaultDeviceChanged(eRender,eConsole,L"owned-negative-callback");
        ConsumerStop(E_UNEXPECTED);
    }
    RejectCom();
}
void RunRejectionConsumer() {
    ConsumerCheck(SdkTrace()->mode==Mode::Memory && SdkTrace()->hooksReady==1 && SdkTrace()->runtimeReady==1);
    SdkRecord(Stage::RejectionRequested,Api::Sound,0,static_cast<LONG>(SdkTrace()->scenario),nullptr,nullptr);
    Microsoft::WRL::ComPtr<IDirectSound8> root;
    ConsumerGood(DirectSoundCreate8(nullptr,&root,nullptr));
    ConsumerCheck(SdkTrace()->scenario==Scenario::ContainedThread && SdkTrace()->otherThreadWrapped==1);
}
