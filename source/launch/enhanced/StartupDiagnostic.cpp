#include "StartupControl.h"
#include "SteamContext.h"
#include "LaunchLease.h"
#include "../preentry/Identity.h"
#include "BuildIdentity.h"
#include "ControlProfile.h"
#include <detours.h>
#include <array>
#include <iostream>
#include <sstream>

namespace {
struct Locks { std::vector<HANDLE> values; ~Locks() { for(auto value:values) CloseHandle(value); } };
struct Child {
    PROCESS_INFORMATION info{};
    bool done=false;
    bool debugger=false;
    ~Child() {
        if(!info.hProcess) return;
        if(!done && WaitForSingleObject(info.hProcess,0)==WAIT_TIMEOUT) {
            TerminateProcess(info.hProcess,97);
            if(debugger) DebugActiveProcessStop(info.dwProcessId);
            WaitForSingleObject(info.hProcess,5000);
        }
        CloseHandle(info.hThread); CloseHandle(info.hProcess);
    }
};
std::wstring Quote(std::wstring_view argument) {
    std::wstring text=L"\""; unsigned int slashes{};
    for(wchar_t c:argument) {
        if(c==L'\\') { ++slashes; continue; }
        text.append(c==L'"' ? slashes*2+1 : slashes,L'\\'); slashes=0; text+=c;
    }
    text.append(slashes*2,L'\\'); return text+L'"';
}
}
int wmain(int argc,wchar_t** argv) {
    try {
        const bool noDebugger=argc>1 && std::wstring_view(argv[1])==L"--no-debugger";
        const int first=noDebugger ? 2 : 1;
        Require(argc>=first+2,"Use BO3-Startup-Control.exe [--no-debugger] <BlackOps3.exe> <new-private.jsonl> [game arguments].");
        bo3::enhanced::LaunchLease lease;
        const auto game=std::filesystem::canonical(argv[first]);
        Require(game.filename()==kControlTargetName,"This diagnostic accepts only its build-pinned target.");
        const auto output=PrivateOutput(argv[first+1]);
        std::array<wchar_t,32768> own{};
        const DWORD length=GetModuleFileNameW(nullptr,own.data(),static_cast<DWORD>(own.size()));
        Require(length && length<own.size(),"Cannot locate startup diagnostic.");
        const auto helper=std::filesystem::canonical(std::filesystem::path(own.data()).parent_path()/L"Bo3EnhancedHelper.dll");
        Locks locks; locks.values.reserve(2);
        VerifyFile(game,kGameHash,locks.values); VerifyFile(helper,kHelperHash,locks.values);
        std::array<char,32768> helperPath{}; BOOL substituted{};
        Require(WideCharToMultiByte(CP_ACP,WC_NO_BEST_FIT_CHARS,helper.c_str(),-1,helperPath.data(),
            static_cast<int>(helperPath.size()),nullptr,&substituted)>0 && !substituted,"Use a lossless Detours helper path.");
        LPCSTR helpers[]{helperPath.data()};
        auto environment=enhanced::SteamChildEnvironment();
        std::wstring command=Quote(game.wstring());
        for(int i=first+2;i<argc;++i) command+=L" "+Quote(argv[i]);
        bo3::startup_control::Timeline trace(output);
        const auto config=std::string("\"debugger\":")+(noDebugger?"false":"true")
            +",\"diagnosticOnly\":true,\"hardwareGate\":false,\"activated\":false,\"editsWritten\":0,\"deadlineMs\":30000";
        trace.Event("configuration",config.c_str());
        std::cout << "Stock-capacity startup diagnostic. No VM expansion. Child stops after 30 seconds.\n";
        STARTUPINFOW startup{sizeof(startup)}; Child child;
        child.debugger=!noDebugger;
        const DWORD creationFlags=CREATE_UNICODE_ENVIRONMENT|(noDebugger ? 0 : DEBUG_ONLY_THIS_PROCESS);
        Require(DetourCreateProcessWithDllsW(game.c_str(),command.data(),nullptr,nullptr,FALSE,
            creationFlags,environment.data(),game.parent_path().c_str(),
            &startup,&child.info,1,helpers,CreateProcessW)!=FALSE,"Cannot create pinned diagnostic child.");
        FILETIME created{},exited{},kernel{},user{};
        Require(GetProcessTimes(child.info.hProcess,&created,&exited,&kernel,&user)!=FALSE,"Cannot bind diagnostic process identity.");
        std::ostringstream fields;
        fields << "\"processId\":" << child.info.dwProcessId << ",\"processCreatedFileTime\":"
            << ((static_cast<std::uint64_t>(created.dwHighDateTime)<<32)|created.dwLowDateTime);
        trace.Event("identity",fields.str().c_str());
        const auto result=bo3::startup_control::Observe(child.info,kControlProfile,trace,
            noDebugger ? bo3::startup_control::Mode::Passive : bo3::startup_control::Mode::Debugger);
        Require(WaitForSingleObject(child.info.hProcess,5000)==WAIT_OBJECT_0,"Diagnostic child exit was not signaled.");
        child.done=true;
        fields.str({}); fields.clear();
        fields << "\"timedOut\":" << (result.timedOut?"true":"false") << ",\"exitCode\":" << result.exitCode
            << ",\"debugExitSeen\":" << (result.debugExitSeen?"true":"false")
            << ",\"activated\":false,\"editsWritten\":0,\"childExited\":true";
        trace.Event("outcome",fields.str().c_str());
        std::wcout << L"Diagnostic evidence: " << output.wstring() << L'\n';
        return 0;
    } catch(const std::exception& error) { std::cerr<<error.what()<<'\n'; return 2; }
}
