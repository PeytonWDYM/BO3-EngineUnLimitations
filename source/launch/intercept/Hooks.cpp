#include "Internal.h"
#include "ContainedSound.h"
#include <detours.h>
#include <intrin.h>

ComFactory OriginalCom = CoCreateInstance;
SoundFactory OriginalSound = DirectSoundCreate8;
ThreadFactory OriginalThread = CreateThread;
extern "C" __declspec(dllexport) void SdkDetoursOrdinal() {}
namespace {
struct Caller {
    std::uint64_t old = RootCaller;
    explicit Caller(void* address) { RootCaller = reinterpret_cast<std::uintptr_t>(address); }
    ~Caller() { RootCaller = old; }
};
struct AudioCall {
    Api old = OuterApi;
    explicit AudioCall(Api api) { ++AudioDepth; OuterApi = api; }
    ~AudioCall() { --AudioDepth; OuterApi = old; }
};
struct Arguments {
    CallArguments old=RootArguments;
    Arguments(DWORD context,LPUNKNOWN outer,void** output) {
        RootArguments={context,outer!=nullptr,output!=nullptr,2,0};
    }
    ~Arguments() { RootArguments=old; }
};
void Admit() {
    if (AudioDepth) StopSdk(E_PENDING, Stage::RecursiveStop);
    if (!SdkTrace()->runtimeReady) StopSdk(E_UNEXPECTED, Stage::ColdStop);
}
HRESULT WINAPI InterceptCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output) noexcept {
    Caller caller(_ReturnAddress());
    Arguments arguments(context,outer,output);
    const bool mmdevice = clsid == __uuidof(MMDeviceEnumerator);
    const bool directSoundCom = clsid == CLSID_DirectSound || clsid == CLSID_DirectSound8;
    if (!mmdevice && !directSoundCom) {
        InterlockedIncrement(&SdkTrace()->nonAudioCalls);
        const HRESULT result = OriginalCom(clsid, outer, context, iid, output);
        SdkRecord(Stage::NonAudio, Api::Com, 0, result, &clsid, &iid);
        return result;
    }
    SdkRecord(Stage::RootEnter, Api::Com, 0, 0, &clsid, &iid);
    if(AudioDepth) {
        try {
            HRESULT result=S_OK;
            if(ForwardContainedCom(clsid,outer,context,iid,output,result)) {
                SdkRecord(Stage::RootReturn,Api::Com,0,result,&clsid,&iid);
                return result;
            }
        } catch (...) { StopSdk(E_UNEXPECTED,Stage::UnsupportedStop); }
    }
    Admit();
    if (directSoundCom) StopSdk(E_NOINTERFACE, Stage::UnsupportedStop);
    AudioCall audio(Api::Com);
    try {
        const HRESULT result = ProviderCom(clsid, outer, context, iid, output);
        SdkRecord(Stage::RootReturn, Api::Com, 0, result, &clsid, &iid);
        if (FAILED(result)) StopSdk(result, Stage::UnsupportedStop);
        return result;
    } catch (...) { StopSdk(E_UNEXPECTED, Stage::UnsupportedStop); }
}
HRESULT WINAPI InterceptSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer) noexcept {
    Caller caller(_ReturnAddress());
    SdkRecord(Stage::RootEnter, Api::Sound, 0, 0, nullptr, &IID_IDirectSound8);
    Admit();
    AudioCall audio(Api::Sound);
    try {
        const HRESULT result = ProviderSound(device, output, outer);
        SdkRecord(Stage::RootReturn, Api::Sound, 0, result, nullptr, &IID_IDirectSound8);
        if (FAILED(result)) StopSdk(result, Stage::UnsupportedStop);
        return result;
    } catch (...) { StopSdk(E_UNEXPECTED, Stage::UnsupportedStop); }
}
}
bool ChangeHooks(bool attach) {
    if (DetourTransactionBegin() != NO_ERROR) return false;
    LONG error = DetourUpdateThread(GetCurrentThread());
    if (error == NO_ERROR) error = attach ? DetourAttach(reinterpret_cast<PVOID*>(&OriginalCom), InterceptCom)
        : DetourDetach(reinterpret_cast<PVOID*>(&OriginalCom), InterceptCom);
    if (error == NO_ERROR) error = attach ? DetourAttach(reinterpret_cast<PVOID*>(&OriginalSound), InterceptSound)
        : DetourDetach(reinterpret_cast<PVOID*>(&OriginalSound), InterceptSound);
    if (error == NO_ERROR) error = attach ? DetourAttach(reinterpret_cast<PVOID*>(&OriginalThread), InterceptThread)
        : DetourDetach(reinterpret_cast<PVOID*>(&OriginalThread), InterceptThread);
    if (error != NO_ERROR) { DetourTransactionAbort(); return false; }
    return DetourTransactionCommit() == NO_ERROR;
}
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        if (!MapTrace() || !DetourRestoreAfterWith()) return FALSE;
        OriginalSound = reinterpret_cast<SoundFactory>(GetProcAddress(GetModuleHandleW(L"dsound.dll"), "DirectSoundCreate8"));
        if (!OriginalSound) return FALSE;
        auto* trace = SdkTrace(); trace->phase = static_cast<LONG>(Phase::Helper);
        trace->sdkCom = reinterpret_cast<std::uintptr_t>(OriginalCom);
        trace->sdkSound = reinterpret_cast<std::uintptr_t>(OriginalSound);
        trace->sdkThread = reinterpret_cast<std::uintptr_t>(OriginalThread);
        SdkRecord(Stage::Restore, Api::None, 0, 1, nullptr, nullptr);
        if (trace->scenario == Scenario::MissingHandshake) return TRUE;
        if (!ChangeHooks(true)) return FALSE;
        InterlockedExchange(&trace->hooksReady, 1);
        SdkRecord(Stage::HooksReady, Api::None, 0, 1, nullptr, nullptr);
    } else if (reason == DLL_PROCESS_DETACH) {
        SdkRecord(Stage::Detach, Api::None, 0, 0, nullptr, nullptr);
        if (SdkTrace()->mode == Mode::Memory && !SdkTrace()->hooksReady) CloseTrace();
    }
    return TRUE;
}
