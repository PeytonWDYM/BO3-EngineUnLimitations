#include "../preentry/Identity.h"
#include "BuildIdentity.h"
#include "../../tests/intercept/Contract.h"
#include "../../tests/audio-driver/DeviceSnapshot.h"
#include <detours.h>
#include <algorithm>
#include <iostream>
#include <sstream>

namespace {
std::wstring target;
BOOL WINAPI CreateOwned(LPCWSTR application, LPWSTR command, LPSECURITY_ATTRIBUTES processAttributes,
    LPSECURITY_ATTRIBUTES threadAttributes, BOOL inherit, DWORD flags, LPVOID environment, LPCWSTR directory,
    LPSTARTUPINFOW startup, LPPROCESS_INFORMATION information) {
    if (!application || target != application) { SetLastError(ERROR_ACCESS_DENIED); return FALSE; }
    return CreateProcessW(application, command, processAttributes, threadAttributes, inherit, flags, environment, directory, startup, information);
}
Scenario Parse(const wchar_t* text) {
    const std::pair<const wchar_t*, Scenario> choices[] = {{L"baseline",Scenario::Baseline},{L"entry",Scenario::Entry},
        {L"worker",Scenario::Worker},{L"wrong-entry",Scenario::WrongEntry},{L"wrong-context",Scenario::WrongContext},
        {L"denied",Scenario::Denied},{L"import-com",Scenario::ImportCom},{L"import-sound",Scenario::ImportSound},
        {L"tls-com",Scenario::TlsCom},{L"tls-sound",Scenario::TlsSound},{L"no-buffer8",Scenario::NoBuffer8},
        {L"clear-failed",Scenario::ClearFailed},{L"reentrant",Scenario::Reentrant},{L"missing-handshake",Scenario::MissingHandshake}};
    for (const auto& choice : choices) if (std::wstring(text) == choice.first) return choice.second;
    throw std::runtime_error("Use a fixed owned SDK scenario.");
}
const char* StageName(Stage stage) {
    constexpr const char* names[] = {"restore","hooks-ready","imported","tls","entry","thread-create","thread-returned",
        "suspended","priority","resume","match","unmatched","gate","runtime-ready","setup","dispatch","joined",
        "factory-requested","root-enter","provider-enter","root-return","cold-stop","unsupported-stop","recursive-stop",
        "non-audio","render-publish","buffer-publish","format","first-silent","start","full-clear","split-clear","play",
        "callback","removal-denied","references-released","runtime-closed","hooks-removed","retained","detach","error"};
    const auto index = static_cast<size_t>(stage);
    return index < std::size(names) ? names[index] : "invalid";
}
void Guid(std::ostringstream& out, const GUID& guid) {
    out << '[' << guid.Data1 << ',' << guid.Data2 << ',' << guid.Data3;
    for (const auto byte : guid.Data4) out << ',' << static_cast<unsigned>(byte);
    out << ']';
}
void Module(std::ostringstream& out, const ModuleIdentity& module) {
    out<<"{\"path\":"<<driver_probe::Quote(driver_probe::Utf8(module.path))<<",\"base\":"<<module.base
        <<",\"rva\":"<<module.rva<<",\"imageSize\":"<<module.imageSize<<",\"timestamp\":"<<module.timestamp<<'}';
}
struct Apartment {
    bool active = false;
    ~Apartment() { if (active) CoUninitialize(); }
};
}
int wmain(int argc, wchar_t** argv) {
    try {
        Require(argc == 4, "Use SdkLauncher memory|physical-silent SCENARIO PRIVATE_TRACE_JSON.");
        const auto output = PrivateOutput(argv[3]);
        const auto scenario = Parse(argv[2]);
        const std::wstring modeText = argv[1];
        Require(modeText == L"memory" || modeText == L"physical-silent", "Use an explicit owned mode.");
        const auto mode = modeText == L"memory" ? Mode::Memory : Mode::PhysicalSilent;
        Require(mode == Mode::Memory || scenario == Scenario::Entry || scenario == Scenario::Worker,
            "Physical-silent accepts only the fixed silent entry or worker consumer.");
        wchar_t path[32768]{};
        const DWORD length = GetModuleFileNameW(nullptr, path, 32768);
        Require(length && length < 32768, "Cannot find the fixed launcher directory.");
        const auto directory = std::filesystem::path(path).parent_path();
        struct Locks { std::vector<HANDLE> values; ~Locks() { for (auto file : values) CloseHandle(file); } } locks;
        locks.values.reserve(3);
        VerifyFile(directory/L"SdkTarget.exe",kTargetHash,locks.values);
        VerifyFile(directory/L"SdkInterceptConsumer.dll",kConsumerHash,locks.values);
        VerifyFile(directory/L"SdkInterceptHelper.dll",kHelperHash,locks.values);
        Handle file(CreateFileW(output.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr));
        Require(file.value != INVALID_HANDLE_VALUE,"Cannot create the private trace.");
        SECURITY_ATTRIBUTES attributes{sizeof(attributes),nullptr,TRUE};
        Handle mapping(CreateFileMappingW(INVALID_HANDLE_VALUE,&attributes,PAGE_READWRITE,0,sizeof(Shared),nullptr));
        Require(mapping.value != nullptr,"Cannot create the owned trace mapping.");
        struct View { Shared* value; ~View() { if(value) UnmapViewOfFile(value); } } view{
            static_cast<Shared*>(MapViewOfFile(mapping.value,FILE_MAP_WRITE,0,0,sizeof(Shared)))};
        Require(view.value != nullptr,"Cannot map the owned trace.");
        ZeroMemory(view.value,sizeof(Shared)); view.value->magic=kSdkMagic; view.value->mode=mode; view.value->scenario=scenario;
        const auto mappingText=std::to_wstring(reinterpret_cast<std::uintptr_t>(mapping.value));
        Require(SetEnvironmentVariableW(L"OWNED_SDK_INTERCEPT_TRACE",mappingText.c_str()) != FALSE,"Cannot set the mapping contract.");
        SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
        Apartment apartment;
        driver_probe::Trace snapshotTrace;
        std::string before="null",after="null";
        if(mode==Mode::PhysicalSilent) {
            Require(SUCCEEDED(CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED)),"Cannot initialize the getter-only parent apartment.");
            apartment.active=true; before=driver_probe::DeviceSnapshot(snapshotTrace);
        }
        target=(directory/L"SdkTarget.exe").wstring();
        std::wstring command=L"\""+target+L"\"";
        const auto helperWide=(directory/L"SdkInterceptHelper.dll").wstring();
        const int count=WideCharToMultiByte(CP_ACP,WC_NO_BEST_FIT_CHARS,helperWide.c_str(),-1,nullptr,0,nullptr,nullptr);
        Require(count>0,"Cannot encode the fixed helper path.");
        std::string helper(static_cast<size_t>(count),'\0'); BOOL substituted=FALSE;
        Require(WideCharToMultiByte(CP_ACP,WC_NO_BEST_FIT_CHARS,helperWide.c_str(),-1,helper.data(),count,nullptr,&substituted)>0
            && !substituted,"The helper path cannot use the native ANSI contract.");
        LPCSTR helpers[]={helper.c_str()};
        STARTUPINFOW startup{}; startup.cb=sizeof(startup); PROCESS_INFORMATION information{};
        Require(DetourCreateProcessWithDllsW(target.c_str(),command.data(),nullptr,nullptr,TRUE,CREATE_NO_WINDOW,nullptr,
            directory.c_str(),&startup,&information,1,helpers,CreateOwned) != FALSE,"Cannot create the fixed owned SDK consumer.");
        Handle process(information.hProcess),thread(information.hThread);
        if(WaitForSingleObject(process.value,30000)!=WAIT_OBJECT_0) {
            TerminateProcess(process.value,30); WaitForSingleObject(process.value,5000);
            throw std::runtime_error("The owned SDK consumer did not exit in time.");
        }
        DWORD exit=0; Require(GetExitCodeProcess(process.value,&exit) != FALSE,"Cannot read the child exit.");
        if(mode==Mode::PhysicalSilent) after=driver_probe::DeviceSnapshot(snapshotTrace);
        std::ostringstream out;
        out<<"{\"targetPid\":"<<information.dwProcessId<<",\"targetExit\":"<<exit<<",\"mode\":"<<static_cast<DWORD>(mode);
#define FIELD(name) out<<",\"" #name "\":"<<view.value->name
        FIELD(errors); FIELD(constructors); FIELD(providerCalls); FIELD(physicalAudioCalls); FIELD(rawPublications); FIELD(generations);
        FIELD(renderPackets); FIELD(silentRenderPackets); FIELD(soundObservations); FIELD(silentSoundObservations);
        FIELD(callbackCalls); FIELD(callbackLive); FIELD(callbackTid); FIELD(creatorTid); FIELD(workerTid); FIELD(returnedTid);
        FIELD(matched); FIELD(unmatched); FIELD(nativeSetups); FIELD(nativeContext); FIELD(priorityResult); FIELD(resumeResult);
        FIELD(aborted); FIELD(abortHresult); FIELD(fullClears); FIELD(plays); FIELD(silentReleases); FIELD(nonAudioCalls);
        FIELD(flags); FIELD(attributesPresent); FIELD(stackSize); FIELD(originalEntry); FIELD(parameter); FIELD(returnedHandle);
        FIELD(sdkCom); FIELD(sdkSound); FIELD(sdkThread);
#undef FIELD
        out<<",\"sdkModules\":[";
        for(size_t index=0;index<3;++index) {
            const auto& module=view.value->sdkModules[index]; if(index) out<<',';
            Module(out,module);
        }
        out<<']';
        out<<",\"parentSnapshotBefore\":"<<before<<",\"parentSnapshotAfter\":"<<after<<",\"events\":[";
        const LONG total=std::clamp(static_cast<LONG>(view.value->count),0L,kSdkEvents);
        for(LONG i=0;i<total;++i) {
            const auto& event=view.value->events[i]; if(i) out<<',';
            out<<"{\"stage\":\""<<StageName(event.stage)<<"\",\"api\":"<<static_cast<DWORD>(event.api)<<",\"phase\":"<<static_cast<LONG>(event.phase)
                <<",\"pid\":"<<event.pid<<",\"tid\":"<<event.tid<<",\"generation\":"<<event.generation<<",\"value\":"<<event.value
                <<",\"hooksReady\":"<<event.hooksReady<<",\"runtimeReady\":"<<event.runtimeReady<<",\"depth\":"<<event.depth
                <<",\"outer\":"<<static_cast<DWORD>(event.outer)<<",\"caller\":"<<event.caller<<",\"clsid\":";
            Guid(out,event.clsid); out<<",\"iid\":"; Guid(out,event.iid);
            out<<",\"callerModule\":"; Module(out,event.callerModule); out<<'}';
        }
        out<<"]}\n"; const auto text=out.str(); DWORD written=0;
        Require(WriteFile(file.value,text.data(),static_cast<DWORD>(text.size()),&written,nullptr)!=FALSE&&written==text.size(),"Cannot write the private trace.");
        return exit==0&&view.value->errors==0&&view.value->rawPublications==0&&before==after ? 0 : 2;
    } catch(const std::exception& error) { std::cerr<<"Owned SDK interception: "<<error.what()<<'\n'; return 2; }
}
