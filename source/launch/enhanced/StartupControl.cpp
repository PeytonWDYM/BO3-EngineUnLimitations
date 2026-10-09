#include "StartupControl.h"
#include "StartupObservation.h"
#include "../preentry/Identity.h"
#include <array>
#include <map>
#include <sstream>
#include <stdexcept>

namespace bo3::startup_control {
Timeline::Timeline(const std::filesystem::path& path) : file_(path), start_(GetTickCount64()) {
    Require(file_.good(), "Cannot open private diagnostic timeline.");
}
void Timeline::Event(const char* kind, const char* fields) {
    file_ << "{\"event\":\"" << kind << "\",\"elapsedMs\":" << GetTickCount64() - start_;
    if (*fields) file_ << ',' << fields;
    file_ << "}\n";
    file_.flush();
    Require(file_.good(), "Cannot save private diagnostic timeline.");
}
namespace {
struct Threads {
    std::map<DWORD,HANDLE> values;
    ~Threads() { for (const auto& [id, handle] : values) { (void)id; CloseHandle(handle); } }
    void Add(DWORD id, HANDLE handle, Timeline& trace) {
        HANDLE copy{};
        Require(DuplicateHandle(GetCurrentProcess(),handle,GetCurrentProcess(),&copy,0,FALSE,DUPLICATE_SAME_ACCESS)!=FALSE,
            "Cannot retain diagnostic thread.");
        const auto [position, inserted] = values.emplace(id,copy);
        (void)position;
        if (!inserted) { CloseHandle(copy); throw std::runtime_error("Duplicate diagnostic thread identity."); }
        CONTEXT context{};
        context.ContextFlags=CONTEXT_DEBUG_REGISTERS|CONTEXT_CONTROL;
        Require(GetThreadContext(handle,&context)!=FALSE,"Cannot observe stopped diagnostic thread.");
        std::ostringstream fields;
        fields << "\"threadId\":" << id << ",\"rip\":" << context.Rip
            << ",\"dr0\":" << context.Dr0 << ",\"dr1\":" << context.Dr1
            << ",\"dr2\":" << context.Dr2 << ",\"dr3\":" << context.Dr3 << ",\"dr7\":" << context.Dr7;
        trace.Event("thread",fields.str().c_str());
    }
};
std::wstring FileName(HANDLE file) {
    std::array<wchar_t,32768> path{};
    const DWORD length=GetFinalPathNameByHandleW(file,path.data(),static_cast<DWORD>(path.size()),FILE_NAME_NORMALIZED);
    Require(length && length<path.size(),"Cannot identify a diagnostic module file.");
    return std::filesystem::path(path.data()).filename().wstring();
}
}
Outcome Observe(const PROCESS_INFORMATION& child,const Profile& profile,Timeline& trace,Mode mode,ObservationLimit limit) {
    Require(profile.imageSize>=8 && profile.poolPointerRva<=profile.imageSize-8
        && profile.hashPointerRva<=profile.imageSize-8,"Invalid diagnostic pool bounds.");
    if(mode==Mode::Passive) return ObservePassive(child,profile,trace,limit);
    Threads threads;
    std::uintptr_t image{},helper{};
    bool initialBreakpoint=false;
    Outcome result;
    const auto deadlineMs=static_cast<DWORD>(limit);
    const ULONGLONG start=GetTickCount64(),deadline=start+deadlineMs;
    ULONGLONG nextObservation=start;
    for (;;) {
        const auto now=GetTickCount64();
        Require(!result.timedOut || now<deadline+5000,"Diagnostic child did not drain to exit.");
        if(!result.timedOut && now>=deadline) {
            if(RecordSignaledExit(child.hProcess,result,trace)) return result;
            const auto fields="\"deadlineMs\":"+std::to_string(deadlineMs)+",\"activated\":false,\"editsWritten\":0";
            trace.Event("timeout",fields.c_str());
            if(!TerminateProcess(child.hProcess,97)) {
                if(RecordSignaledExit(child.hProcess,result,trace)) return result;
                Require(false,"Cannot terminate diagnostic child at deadline.");
            }
            result.timedOut=true;
        }
        DEBUG_EVENT event{};
        if (!WaitForDebugEvent(&event,100)) {
            const DWORD waitError=GetLastError();
            if(RecordSignaledExit(child.hProcess,result,trace)) return result;
            Require(waitError==ERROR_SEM_TIMEOUT,"Cannot wait for a diagnostic debug event.");
            if (GetTickCount64()>=nextObservation && !result.timedOut) {
                RecordObservation(child.hProcess,image,helper,profile,trace);
                nextObservation=GetTickCount64()+250;
            }
            continue;
        }
        Require(event.dwProcessId==child.dwProcessId,"Unexpected diagnostic debug process.");
        std::ostringstream fields;
        fields << "\"code\":" << event.dwDebugEventCode << ",\"threadId\":" << event.dwThreadId;
        DWORD continuation=DBG_CONTINUE;
        bool exited=false;
        if (event.dwDebugEventCode==CREATE_PROCESS_DEBUG_EVENT) {
            const auto& created=event.u.CreateProcessInfo;
            image=reinterpret_cast<std::uintptr_t>(created.lpBaseOfImage);
            threads.Add(event.dwThreadId,created.hThread,trace);
            if (created.hFile) CloseHandle(created.hFile);
        } else if (event.dwDebugEventCode==CREATE_THREAD_DEBUG_EVENT) {
            threads.Add(event.dwThreadId,event.u.CreateThread.hThread,trace);
        } else if (event.dwDebugEventCode==EXIT_THREAD_DEBUG_EVENT) {
            auto thread=threads.values.find(event.dwThreadId);
            Require(thread!=threads.values.end(),"Unknown diagnostic thread exit.");
            CloseHandle(thread->second);
            threads.values.erase(thread);
        } else if (event.dwDebugEventCode==LOAD_DLL_DEBUG_EVENT) {
            const auto& loaded=event.u.LoadDll;
            const auto address=reinterpret_cast<std::uintptr_t>(loaded.lpBaseOfDll);
            bool isHelper=false;
            if (loaded.hFile) {
                const auto name=FileName(loaded.hFile);
                isHelper=CompareStringOrdinal(name.c_str(),-1,L"Bo3EnhancedHelper.dll",-1,TRUE)==CSTR_EQUAL;
                CloseHandle(loaded.hFile);
            }
            if (isHelper) { Require(!helper,"Duplicate diagnostic helper module."); helper=address; }
            fields << ",\"moduleBase\":" << address << ",\"helper\":" << (isHelper?"true":"false");
        } else if (event.dwDebugEventCode==EXCEPTION_DEBUG_EVENT) {
            const auto& exception=event.u.Exception;
            const auto code=exception.ExceptionRecord.ExceptionCode;
            fields << ",\"exceptionCode\":" << code << ",\"exceptionAddress\":"
                << reinterpret_cast<std::uintptr_t>(exception.ExceptionRecord.ExceptionAddress)
                << ",\"firstChance\":" << exception.dwFirstChance;
            if (code==EXCEPTION_BREAKPOINT && !initialBreakpoint) initialBreakpoint=true;
            else continuation=DBG_EXCEPTION_NOT_HANDLED;
            fields << ",\"continuation\":" << continuation;
        } else if (event.dwDebugEventCode==EXIT_PROCESS_DEBUG_EVENT) {
            result.exitCode=event.u.ExitProcess.dwExitCode;
            result.debugExitSeen=true;
            fields << ",\"exitCode\":" << result.exitCode;
            exited=true;
        }
        trace.Event("debug",fields.str().c_str());
        if (!exited) RecordObservation(child.hProcess,image,helper,profile,trace);
        Require(ContinueDebugEvent(event.dwProcessId,event.dwThreadId,continuation)!=FALSE,
            "Cannot continue diagnostic debug event.");
        if (exited) return result;
    }
}
}
