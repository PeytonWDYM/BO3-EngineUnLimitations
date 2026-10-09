#include "ContainedSound.h"
#include "SoundIdentity.h"
#include <cstring>

namespace {
thread_local ScopeFacts scope{};
bool LiveBytesMatch() {
    auto* trace=SdkTrace();
    const auto& module=trace->sdkModules[1];
    BYTE expected[sizeof(kSoundCallBytes)];
    memcpy(expected,kSoundCallBytes,sizeof(expected));
    if(trace->mode==Mode::Memory && trace->scenario==Scenario::ContainedLiveBytes) expected[0]^=1;
    return kSoundCallRva<=module.imageSize && sizeof(expected)<=module.imageSize-kSoundCallRva
        && memcmp(reinterpret_cast<const BYTE*>(static_cast<std::uintptr_t>(module.base))+kSoundCallRva,
            expected,sizeof(expected))==0;
}
bool PinnedModule(const ModuleIdentity& module) {
    DWORD expected=kSoundTimestamp;
    if(SdkTrace()->mode==Mode::Memory && SdkTrace()->scenario==Scenario::ContainedIdentity) expected^=1;
    return module.imageSize==kSoundImageSize && module.timestamp==expected
        && CompareStringOrdinal(module.path,-1,kSoundPath,-1,TRUE)==CSTR_EQUAL;
}
}
ScopeFacts CurrentSoundScope() { return scope; }
void InitializeSoundIdentity() {
    DWORD failed=0;
    if(!PinnedModule(SdkTrace()->sdkModules[1])) failed|=WrongWindowsIdentity;
    if(!LiveBytesMatch()) failed|=WrongLiveBytes;
    RootArguments.failed=failed;
    SdkRecord(Stage::LiveIdentity,Api::Sound,0,failed ? 0 : 1,nullptr,nullptr);
    RequireSdk(!failed);
    InterlockedExchange(&SdkTrace()->identityReady,1);
}
OriginalSoundScope::OriginalSoundScope() {
    RequireSdk(SdkTrace()->mode==Mode::PhysicalSilent && !scope.serial && AudioDepth==1 && OuterApi==Api::Sound);
    scope={GetCurrentThreadId(),InterlockedIncrement(&SdkTrace()->soundScopes),0,0};
    SdkRecord(Stage::SoundScopeEnter,Api::Sound,0,1,nullptr,nullptr);
}
OriginalSoundScope::~OriginalSoundScope() {
    SdkRecord(Stage::SoundScopeExit,Api::Sound,0,scope.count,nullptr,nullptr);
    scope={};
}
bool ForwardContainedCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output, HRESULT& result) {
    auto* trace=SdkTrace();
    DWORD failed=0;
    if(trace->mode!=Mode::PhysicalSilent) failed|=WrongMode;
    if(!scope.serial) failed|=MissingScope;
    if(scope.thread!=GetCurrentThreadId()) failed|=WrongThread;
    if(AudioDepth!=1) failed|=WrongDepth;
    if(OuterApi!=Api::Sound) failed|=WrongOuter;
    if(scope.active) failed|=ContainedActive;
    if(clsid!=__uuidof(MMDeviceEnumerator)) failed|=WrongClass;
    if(iid!=__uuidof(IMMDeviceEnumerator)) failed|=WrongIid;
    if(context!=CLSCTX_ALL) failed|=WrongContext;
    if(outer) failed|=Aggregation;
    if(!output) failed|=MissingOutput;
    ModuleIdentity caller{};
    RequireSdk(DescribeAddress(RootCaller,caller));
    if(caller.base!=trace->sdkModules[1].base || !PinnedModule(caller)) failed|=WrongModule;
    if(RootCaller!=trace->sdkModules[1].base+kSoundReturnRva) failed|=WrongCallsite;
    if(!LiveBytesMatch()) failed|=WrongLiveBytes;
    if(!trace->identityReady || !PinnedModule(trace->sdkModules[1])) failed|=WrongWindowsIdentity;
    // Only the audited SDK stack slot has a known initially-null storage contract.
    if(!failed) {
        RootArguments.outputNull=*output==nullptr;
        if(!RootArguments.outputNull) failed|=NonNullOutput;
    }
    RootArguments.failed=failed;
    SdkRecord(Stage::AdmissionChecked,Api::Com,0,static_cast<LONG>(failed),&clsid,&iid);
    if(failed) return false;
    struct Active {
        Active() { scope.active=1; ++scope.count; }
        ~Active() { scope.active=0; }
    } active;
    InterlockedIncrement(&trace->containedCalls);
    SdkRecord(Stage::ContainedEnter,Api::Com,0,S_OK,&clsid,&iid);
    InterlockedIncrement(&trace->originalComCalls);
    result=OriginalCom(clsid,outer,context,iid,output);
    SdkRecord(Stage::ContainedReturn,Api::Com,0,result,&clsid,&iid);
    return true;
}
