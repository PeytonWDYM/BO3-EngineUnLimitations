#include "OwnedChild.h"
#include "../enhanced/SteamContext.h"
#include "../preentry/Identity.h"
#include <bcrypt.h>
#include <detours.h>
#include <array>
#include <vector>

namespace bo3::late_startup {
std::uint64_t Created(HANDLE process) {
    FILETIME created{},exited{},kernel{},user{};
    Require(GetProcessTimes(process,&created,&exited,&kernel,&user)!=FALSE,"Cannot read owned process creation time.");
    return std::uint64_t{created.dwHighDateTime}<<32|created.dwLowDateTime;
}
std::wstring QuoteArgument(std::wstring_view argument) {
    std::wstring result=L"\""; unsigned int slashes=0;
    for(const wchar_t value:argument) {
        if(value==L'\\') {++slashes;continue;}
        result.append(value==L'"' ? slashes*2+1 : slashes,L'\\'); slashes=0;result+=value;
    }
    result.append(slashes*2,L'\\');return result+L'"';
}
OwnedChild::OwnedChild(const std::filesystem::path& game,std::wstring command,
    std::span<const std::filesystem::path> helpers,DWORD deadlineMs) {
#ifndef BO3_LATE_OWNED_TEST
    Require(deadlineMs==30000,"The production gate deadline is fixed.");
#endif
    std::vector<std::array<char,32768>> names(helpers.size());std::vector<LPCSTR> pointers;
    for(std::size_t i=0;i<helpers.size();++i) {
        BOOL substituted=FALSE;
        Require(WideCharToMultiByte(CP_ACP,WC_NO_BEST_FIT_CHARS,helpers[i].c_str(),-1,names[i].data(),32768,
            nullptr,&substituted)>0 && !substituted,"The helper path cannot use ANSI substitution.");
        pointers.push_back(names[i].data());
    }
    auto environment=enhanced::SteamChildEnvironment();STARTUPINFOW startup{sizeof(startup)};
    Require(DetourCreateProcessWithDllsW(game.c_str(),command.data(),nullptr,nullptr,FALSE,
        CREATE_SUSPENDED|CREATE_UNICODE_ENVIRONMENT|CREATE_NO_WINDOW,environment.data(),game.parent_path().c_str(),
        &startup,&process,static_cast<DWORD>(pointers.size()),pointers.data(),CreateProcessW)!=FALSE,
        "Cannot create the owned suspended child.");
    try {
        ready_=CreateEventW(nullptr,TRUE,FALSE,nullptr);release_=CreateEventW(nullptr,TRUE,FALSE,nullptr);
        Require(ready_ && release_,"Cannot create gate events.");
        payload={startup_gate::Abi,sizeof(payload),process.dwProcessId,process.dwThreadId,GetCurrentProcessId(),
            deadlineMs,Created(process.hProcess),{},0,0,0};
        Require(BCryptGenRandom(nullptr,reinterpret_cast<PUCHAR>(payload.nonce),sizeof(payload.nonce),
            BCRYPT_USE_SYSTEM_PREFERRED_RNG)==0,"Cannot create the gate nonce.");
        const auto duplicate=[&](HANDLE original,DWORD access) {
            HANDLE remote{};
            Require(DuplicateHandle(GetCurrentProcess(),original,process.hProcess,&remote,access,FALSE,0)!=FALSE,
                "Cannot duplicate a child-local gate handle.");
            return reinterpret_cast<std::uint64_t>(remote);
        };
        payload.readyEvent=duplicate(ready_,EVENT_MODIFY_STATE|SYNCHRONIZE);
        payload.releaseEvent=duplicate(release_,SYNCHRONIZE);
        payload.parentProcess=duplicate(GetCurrentProcess(),PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE);
        Require(DetourCopyPayloadToProcess(process.hProcess,startup_gate::PayloadGuid,&payload,sizeof(payload))!=FALSE,
            "Cannot publish the suspended child gate payload.");
    } catch(...) {TerminateProcess(process.hProcess,97);WaitForSingleObject(process.hProcess,5000);
        if(ready_)CloseHandle(ready_);if(release_)CloseHandle(release_);
        CloseHandle(process.hThread);CloseHandle(process.hProcess);process={};throw;}
}
OwnedChild::~OwnedChild() {
    if(process.hProcess) {if(WaitForSingleObject(process.hProcess,0)!=WAIT_OBJECT_0) {
            TerminateProcess(process.hProcess,97);WaitForSingleObject(process.hProcess,5000);}
        CloseHandle(process.hThread);CloseHandle(process.hProcess);}
    if(ready_)CloseHandle(ready_);if(release_)CloseHandle(release_);
}
bool OwnedChild::Exited() const {
    const auto state=WaitForSingleObject(process.hProcess,0);
    Require(state==WAIT_OBJECT_0 || state==WAIT_TIMEOUT,"Cannot observe owned child lifetime.");
    return state==WAIT_OBJECT_0;
}
void OwnedChild::Terminate() {
    if(process.hProcess && WaitForSingleObject(process.hProcess,0)==WAIT_TIMEOUT)
        Require(TerminateProcess(process.hProcess,97)!=FALSE,"Cannot terminate the owned refused child.");
}
void OwnedChild::Resume() {
    Require(!resumed_ && ResumeThread(process.hThread)==1,"Cannot resume the owned suspended child.");resumed_=true;
}
void OwnedChild::WaitReady(ULONGLONG deadline) {
    HANDLE events[]{process.hProcess,ready_};
    for(;;) {
        Require(GetTickCount64()<deadline,"The cooperative gate did not become ready before the deadline.");
        const auto wait=WaitForMultipleObjects(2,events,FALSE,50);
        if(wait==WAIT_OBJECT_0+1)return;
        Require(wait==WAIT_TIMEOUT,"The owned child exited or the gate wait failed.");
    }
}
void OwnedChild::Release() {Require(SetEvent(release_)!=FALSE,"Cannot release the detached cooperative gate.");}
}
