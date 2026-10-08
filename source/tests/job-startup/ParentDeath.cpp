#include "../../patches/vm_startup/PausedPatch.h"
#include "ParentDeath.h"
#include "../../launch/preentry/Identity.h"
#include <fstream>
#include <intrin.h>

namespace {
struct Identity {DWORD pid,reserved;std::uint64_t created;};
static_assert(sizeof(Identity)==16);
struct Handles {PROCESS_INFORMATION child{};HANDLE target{};
    ~Handles(){if(target)CloseHandle(target);if(child.hThread)CloseHandle(child.hThread);
        if(child.hProcess){if(WaitForSingleObject(child.hProcess,0)!=WAIT_OBJECT_0)TerminateProcess(child.hProcess,97);CloseHandle(child.hProcess);}}};
}
[[noreturn]] void DieAfterPartialWrite(const bo3::late_startup::OwnedChild& child,const std::filesystem::path& output,
    const std::vector<vm_startup::AddressEdit>& edits) {
    const Identity identity{child.process.dwProcessId,0,child.payload.processCreatedFileTime};
    {std::ofstream file(output.wstring()+L".identity.bin",std::ios::binary);
        file.write(reinterpret_cast<const char*>(&identity),sizeof(identity));Require(file.good(),"Cannot save owned death identity.");}
    const auto deadline=GetTickCount64()+10000;
    while(!std::filesystem::exists(output.wstring()+L".go")) {
        Require(GetTickCount64()<deadline,"Owned death verifier did not retain the target.");Sleep(10);
    }
    vm_startup::Receipt receipt;vm_startup::PausedPatch partial(child.process.hProcess,{edits.front()},receipt);partial.Apply();
    const auto actual=vm_startup::ReadStopped(child.process.hProcess,edits.front().address,edits.front().replacement.size());
    Require(actual==edits.front().replacement,"Owned partial write readback differs.");
    {std::ofstream file(output.wstring()+L".partial.bin",std::ios::binary);
        file.write(reinterpret_cast<const char*>(actual.data()),actual.size());Require(file.good(),"Cannot save partial publication evidence.");}
    TerminateProcess(GetCurrentProcess(),86);__fastfail(7);
}
int VerifyOwnedParentDeath(const std::filesystem::path& executable,const std::filesystem::path& output) {
    auto command=bo3::late_startup::QuoteArgument(executable.wstring())+L" death-child "+
        bo3::late_startup::QuoteArgument(output.wstring());
    STARTUPINFOW startup{sizeof(startup)};Handles handles;
    Require(CreateProcessW(executable.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,
        executable.parent_path().c_str(),&startup,&handles.child)!=FALSE,"Cannot create the owned death controller.");
    const auto deadline=GetTickCount64()+15000;Identity identity{};
    for(;;) {
        std::ifstream file(output.wstring()+L".identity.bin",std::ios::binary);
        file.read(reinterpret_cast<char*>(&identity),sizeof(identity));if(file.good())break;
        Require(GetTickCount64()<deadline && WaitForSingleObject(handles.child.hProcess,0)==WAIT_TIMEOUT,
            "The owned death controller did not publish its identity.");Sleep(10);
    }
    handles.target=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION|SYNCHRONIZE,FALSE,identity.pid);
    Require(handles.target && bo3::late_startup::Created(handles.target)==identity.created,"The retained death target identity differs.");
    {std::ofstream go(output.wstring()+L".go");go<<"retained";Require(go.good(),"Cannot release owned abrupt death.");}
    Require(WaitForSingleObject(handles.child.hProcess,10000)==WAIT_OBJECT_0
        && WaitForSingleObject(handles.target,10000)==WAIT_OBJECT_0,"Owned death cleanup exceeded its bound.");
    DWORD controllerExit{},targetExit{};
    Require(GetExitCodeProcess(handles.child.hProcess,&controllerExit) && GetExitCodeProcess(handles.target,&targetExit),
        "Cannot read owned parent-death exits.");
    const bool passed=controllerExit==86 && targetExit==0
        && std::filesystem::file_size(output.wstring()+L".partial.bin")>0
        && !std::filesystem::exists(output.wstring()+L".target.json");
    std::ofstream result(output);result<<"{\"passed\":"<<(passed?"true":"false")<<",\"controllerExitCode\":"<<controllerExit
        <<",\"targetExitCode\":"<<targetExit<<",\"partialEdits\":1,\"gateReturned\":false,\"ownedProcessId\":"<<identity.pid
        <<",\"processCreatedFileTime\":"<<identity.created<<",\"scope\":\"Abrupt controller death after one uncommitted edit under real job freeze.\"}";
    Require(result.good(),"Cannot save owned parent-death proof.");return passed?0:1;
}
