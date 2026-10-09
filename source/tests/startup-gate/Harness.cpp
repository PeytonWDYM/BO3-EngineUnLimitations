#include "../../launch/startup_gate/GateContract.h"
#include "../../launch/preentry/Identity.h"
#include "../../launch/enhanced/SteamContext.h"
#include "BuildIdentity.h"
#include <detours.h>
#include <Psapi.h>
#include <array>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
namespace {
struct Child {
    PROCESS_INFORMATION info{};
    ~Child() {
        if(info.hProcess) {
            if(WaitForSingleObject(info.hProcess,0)==WAIT_TIMEOUT) { TerminateProcess(info.hProcess,98); WaitForSingleObject(info.hProcess,5000); }
            CloseHandle(info.hProcess); CloseHandle(info.hThread);
        }
    }
};
std::wstring Quote(const std::wstring& value) {
    std::wstring result=L"\""; unsigned int slashes{};
    for(const auto c:value) {
        if(c==L'\\') { ++slashes; continue; }
        if(c==L'\"') result.append(slashes*2+1,L'\\'); else result.append(slashes,L'\\');
        slashes=0; result+=c;
    }
    result.append(slashes*2,L'\\'); return result+L'\"';
}
std::uint64_t Duplicate(HANDLE process,HANDLE handle,DWORD rights) {
    HANDLE remote{};
    Require(DuplicateHandle(GetCurrentProcess(),handle,process,&remote,rights,FALSE,0)!=FALSE,"Cannot duplicate gate handle.");
    return reinterpret_cast<std::uint64_t>(remote);
}
std::uintptr_t FindHelper(HANDLE process) {
    std::array<HMODULE,128> modules{}; DWORD count{};
    Require(K32EnumProcessModulesEx(process,modules.data(),sizeof(modules),&count,LIST_MODULES_64BIT)!=FALSE
        && count<=sizeof(modules),"Cannot inspect owned helper modules.");
    for(std::size_t i=0;i<count/sizeof(HMODULE);++i) {
        wchar_t name[MAX_PATH]{};
        if(K32GetModuleBaseNameW(process,modules[i],name,MAX_PATH) && std::wstring(name)==L"Bo3StartupGate.dll")
            return reinterpret_cast<std::uintptr_t>(modules[i]);
    }
    Require(false,"Owned gate helper absent."); return 0;
}
}
int wmain(int argc,wchar_t** argv) {
    try {
        Require(argc==3,"Use a fixed owned scenario and new private receipt.");
        const std::wstring scenario=argv[1];
        const std::array<const wchar_t*,24> scenarios{L"success",L"repeated",L"nonmatch",L"noncrt",L"wrongthread",L"changedcaller",L"unwind",
            L"timeout",L"prerelease",L"parentloss",L"missing",L"duplicate",L"abi",L"size",L"pid",L"tid",L"created",L"nonce",L"deadline",L"alias",L"dupalias",L"type",L"missingquery",L"missinganchor"};
        bool known{}; for(const auto* s:scenarios) known=known || scenario==s;
        Require(known,"Unknown owned gate scenario.");
        const auto receipt=PrivateOutput(argv[2]);
        const auto proof=PrivateOutput((receipt.wstring()+L"-child.json").c_str());
        wchar_t self[32768]{}; Require(GetModuleFileNameW(nullptr,self,32768)!=0,"Cannot locate owned harness.");
        const auto bin=std::filesystem::path(self).parent_path();
        const auto target=bin/L"VmStartupControlTarget.exe";
        const auto helper=bin/(scenario==L"missingquery" ? L"missing-query/Bo3StartupGate.dll" : scenario==L"missinganchor" ? L"missing-anchor/Bo3StartupGate.dll" : L"Bo3StartupGate.dll");
        std::vector<HANDLE> locks; locks.reserve(4);
        VerifyFile(target,kGameHash,locks); VerifyFile(helper,scenario==L"missingquery" ? kMissingQueryHash : scenario==L"missinganchor" ? kMissingAnchorHash : kHelperHash,locks);
        VerifyFile(bin/L"GateConsumer.dll",kConsumerHash,locks);
        VerifyFile(bin/L"GateGuardian.exe",kGuardianHash,locks);
        struct Locks { std::vector<HANDLE>& values; ~Locks() { for(auto h:values) CloseHandle(h); } } held{locks};
        Handle ready(CreateEventW(nullptr,TRUE,FALSE,nullptr)),release(CreateEventW(nullptr,TRUE,FALSE,nullptr));
        Require(ready.value && release.value,"Cannot create gate events.");
        auto environment=enhanced::SteamChildEnvironment();
        const std::wstring childScenario=scenario==L"prerelease" || scenario==L"parentloss" || scenario==L"timeout" ? L"success" : scenario;
        auto command=Quote(target.wstring())+L" "+Quote(childScenario)+L" "+Quote(proof.wstring())+L" "+Quote(L"quoted \"value\" \\");
        STARTUPINFOW startup{}; startup.cb=sizeof(startup);
        Child child;
        const auto helperString=helper.string(); const char* helpers[]{helperString.c_str()};
        Require(DetourCreateProcessWithDllsW(target.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_SUSPENDED|CREATE_UNICODE_ENVIRONMENT|CREATE_NO_WINDOW,
            environment.data(),bin.c_str(),&startup,&child.info,1,helpers,CreateProcessW)!=FALSE,"Cannot create owned gate child.");
        FILETIME created{},exited{},kernel{},user{};
        Require(GetProcessTimes(child.info.hProcess,&created,&exited,&kernel,&user)!=FALSE,"Cannot bind child creation.");
        bo3::startup_gate::Payload payload{1,sizeof(payload),child.info.dwProcessId,child.info.dwThreadId,GetCurrentProcessId(),1000,
            (std::uint64_t(created.dwHighDateTime)<<32)|created.dwLowDateTime,{0x173cbe39d920a432,0x4ee1b9a2df86c017},
            Duplicate(child.info.hProcess,ready.value,EVENT_MODIFY_STATE|SYNCHRONIZE),Duplicate(child.info.hProcess,release.value,SYNCHRONIZE),
            Duplicate(child.info.hProcess,GetCurrentProcess(),PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE)};
        Child guardian;
        if(scenario==L"parentloss") {
            // Owned parent-loss fault: substitute a pinned inert guardian before payload publication.
            auto waitCommand=Quote(bin/L"GateGuardian.exe");
            Require(CreateProcessW((bin/L"GateGuardian.exe").c_str(),waitCommand.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,bin.c_str(),&startup,&guardian.info)!=FALSE,"Cannot create owned guardian.");
            payload.parentProcessId=guardian.info.dwProcessId;
            payload.parentProcess=Duplicate(child.info.hProcess,guardian.info.hProcess,PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE);
        }
        if(scenario==L"abi") ++payload.abi;
        if(scenario==L"size") ++payload.bytes;
        if(scenario==L"pid") ++payload.processId;
        if(scenario==L"tid") ++payload.primaryThreadId;
        if(scenario==L"created") ++payload.processCreatedFileTime;
        if(scenario==L"nonce") payload.nonce[0]=payload.nonce[1]=0;
        if(scenario==L"deadline") ++payload.deadlineMs;
        if(scenario==L"alias") payload.releaseEvent=payload.readyEvent;
        if(scenario==L"dupalias") payload.releaseEvent=Duplicate(child.info.hProcess,ready.value,SYNCHRONIZE);
        if(scenario==L"type") payload.releaseEvent=Duplicate(child.info.hProcess,GetCurrentProcess(),SYNCHRONIZE);
        if(scenario!=L"missing") Require(DetourCopyPayloadToProcess(child.info.hProcess,bo3::startup_gate::PayloadGuid,&payload,sizeof(payload))!=FALSE,"Cannot publish owned payload.");
        if(scenario==L"duplicate") Require(DetourCopyPayloadToProcess(child.info.hProcess,bo3::startup_gate::PayloadGuid,&payload,sizeof(payload))!=FALSE,"Cannot publish duplicate fault payload.");
        if(scenario==L"prerelease") SetEvent(release.value);
        const auto begin=GetTickCount64();
        Require(ResumeThread(child.info.hThread)!=DWORD(-1),"Cannot resume owned gate child.");
        const HANDLE waits[]{ready.value,child.info.hProcess};
        const DWORD arrival=WaitForMultipleObjects(2,waits,FALSE,5000);
        bo3::startup_gate::State state{};
        if(arrival==WAIT_OBJECT_0) {
            SIZE_T count{};
            const auto base=FindHelper(child.info.hProcess);
            Require(ReadProcessMemory(child.info.hProcess,reinterpret_cast<void*>(base+kStateRva),&state,sizeof(state),&count)!=FALSE && count==sizeof(state),"Cannot read waiting gate state.");
            Require(state.phase==static_cast<LONG>(bo3::startup_gate::Phase::Waiting) && state.processId==child.info.dwProcessId
                && state.primaryThreadId==child.info.dwThreadId && state.nonce[0]==payload.nonce[0] && state.nonce[1]==payload.nonce[1]
                && state.processCreatedFileTime==payload.processCreatedFileTime && state.generation==1 && state.observationCount==1
                && state.entryAnchorPresent==1 && state.entryFrameCount>=1 && state.entryFrameCount<=64
                && state.entryAnchorStart<state.entryAnchorEnd,"Waiting gate identity differs.");
            if(scenario==L"parentloss") TerminateProcess(guardian.info.hProcess,42);
            else if(scenario!=L"timeout") Require(SetEvent(release.value)!=FALSE,"Cannot release owned gate.");
        }
        Require(WaitForSingleObject(child.info.hProcess,5000)==WAIT_OBJECT_0,"Owned gate child failed bounded exit.");
        DWORD code{}; Require(GetExitCodeProcess(child.info.hProcess,&code)!=FALSE,"Cannot query owned gate exit.");
        std::ofstream out(receipt);
        out << "{\"processId\":" << child.info.dwProcessId << ",\"primaryThreadId\":" << child.info.dwThreadId
            << ",\"createdFileTime\":" << payload.processCreatedFileTime << ",\"readySeen\":" << (arrival==WAIT_OBJECT_0?"true":"false")
            << ",\"phaseAtReady\":" << state.phase << ",\"generation\":" << state.generation << ",\"observationCount\":" << state.observationCount
            << ",\"callbackThreadId\":" << state.callbackThreadId << ",\"loaderCallout\":" << state.loaderCallout
            << ",\"entryAnchorPresent\":" << state.entryAnchorPresent << ",\"entryFrameCount\":" << state.entryFrameCount
            << ",\"entryAnchorStart\":" << state.entryAnchorStart << ",\"entryAnchorEnd\":" << state.entryAnchorEnd
            << ",\"exitCode\":" << code << ",\"elapsedMs\":" << GetTickCount64()-begin << "}\n";
        return 0;
    } catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
