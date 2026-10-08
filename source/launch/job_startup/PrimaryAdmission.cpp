#include "PrimaryAdmission.h"
#include "RuntimeUnwind.h"
#include "../preentry/Identity.h"
#include "GateWaitProfile.h"
#include <DbgHelp.h>
#include <TlHelp32.h>
#include <Psapi.h>
#include <array>
#include <algorithm>
#include <cstring>

namespace bo3::job_startup {
namespace {
struct Handle {HANDLE value;~Handle(){if(value!=INVALID_HANDLE_VALUE)CloseHandle(value);}};
struct Modules {
    std::vector<std::pair<DWORD64,HMODULE>> values;
    ~Modules(){for(const auto& [base,module]:values){(void)base;FreeLibrary(module);}}
};
Modules* unwindModules{};
bool unwindRefused{};
Receipt* unwindReceipt{};
std::uintptr_t runtimeImageBase{};
DWORD64 waitLeafStart{},waitLeafEnd{};
struct UnwindScope {~UnwindScope(){unwindModules=nullptr;unwindReceipt=nullptr;runtimeImageBase=0;waitLeafStart=waitLeafEnd=0;}};
BOOL CALLBACK ReadMemory(HANDLE process,DWORD64 address,PVOID output,DWORD size,LPDWORD read) {
    SIZE_T count{};const BOOL result=ReadProcessMemory(process,reinterpret_cast<void*>(address),output,size,&count);
    *read=static_cast<DWORD>(count);
    if(result && count==size && unwindReceipt) {
        const auto mask=RuntimeMetadataReadMask(runtimeImageBase,address,size);
        if(mask){++unwindReceipt->runtimeMetadataReads;unwindReceipt->runtimeMetadataMask|=mask;}
    }
    return result && count==size;
}
BOOL CALLBACK SymbolCallback(HANDLE process,ULONG action,ULONG64 data,ULONG64) {
    if(action!=CBA_READ_MEMORY)return FALSE;
    auto& request=*reinterpret_cast<IMAGEHLP_CBA_READ_MEMORY*>(data);
    return ReadMemory(process,request.addr,request.buf,request.bytes,request.bytesread);
}
PVOID CALLBACK FunctionTable(HANDLE process,DWORD64 pc) {
    try {
        unwindReceipt->unwindLookupPc=pc;
        const auto base=SymGetModuleBase64(process,pc);
        const auto found=std::find_if(unwindModules->values.begin(),unwindModules->values.end(),
            [&](const auto& row){return row.first==base;});
        Require(found!=unwindModules->values.end(),"An unwind module was not admitted.");
        const auto* local=reinterpret_cast<const unsigned char*>(found->second);
        if(base==runtimeImageBase) {
            const auto runtime=RuntimeFunction(process,base,local,pc);
            if(runtime)return runtime;
        }
        const auto* function=static_cast<const RUNTIME_FUNCTION*>(SymFunctionTableAccess64(process,pc));
        if(!function) {
            Require(pc>=waitLeafStart && pc<waitLeafEnd,"A native frame has no admitted unwind row.");
            return nullptr;
        }
        const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(local);
        const auto* pe=reinterpret_cast<const IMAGE_NT_HEADERS64*>(local+dos->e_lfanew);
        const auto& table=pe->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXCEPTION];
        Require(table.Size%sizeof(RUNTIME_FUNCTION)==0,"An unwind table has invalid size.");
        const auto* first=reinterpret_cast<const RUNTIME_FUNCTION*>(local+table.VirtualAddress);
        bool matched=false;
        for(DWORD i=0;i<table.Size/sizeof(RUNTIME_FUNCTION);++i) {
            if(std::memcmp(first+i,function,sizeof(*function)))continue;
            Require(vm_startup::ReadStopped(process,base+table.VirtualAddress+i*sizeof(*function),sizeof(*function))
                ==std::vector<unsigned char>(reinterpret_cast<const unsigned char*>(function),
                    reinterpret_cast<const unsigned char*>(function)+sizeof(*function)),"The native unwind table differs.");
            matched=true;break;
        }
        Require(matched,"A native unwind entry differs.");
        auto current=*function;bool complete=false;
        for(unsigned int depth=0;depth<8;++depth) {
            Require(current.UnwindData<pe->OptionalHeader.SizeOfImage-4 && !(current.UnwindData&3),
                "A chained native unwind entry differs.");
            const auto* info=local+current.UnwindData;
            Require((info[0]&7)==1 || (info[0]&7)==2,"Unsupported native unwind version.");
            const auto flags=info[0]>>3;
            const std::size_t codes=4+((info[2]+1u)&~1u)*2u;
            const std::size_t size=codes+((flags&4)?12u:((flags&3)?4u:0u));
            Require(size<=pe->OptionalHeader.SizeOfImage-current.UnwindData
                && vm_startup::ReadStopped(process,base+current.UnwindData,size)==std::vector<unsigned char>(info,info+size),
                "The native unwind metadata differs.");
            if(!(flags&4)){complete=true;break;}
            Require(!(flags&3),"A native unwind chain has handler flags.");
            std::memcpy(&current,info+codes,sizeof(current));
            Require(current.BeginAddress<current.EndAddress && current.EndAddress<=pe->OptionalHeader.SizeOfImage,
                "A native unwind chain exceeds its image.");
        }
        Require(complete,"The native unwind chain exceeds its bound.");
        return const_cast<RUNTIME_FUNCTION*>(function);
    }catch(const std::exception& error) {
        unwindRefused=true;unwindReceipt->unwindReason=std::string(error.what()).substr(0,512);return nullptr;
    }catch(...) {unwindRefused=true;unwindReceipt->unwindReason="Unknown native unwind refusal.";return nullptr;}
}
struct Symbols {HANDLE process;bool ready=false;~Symbols(){if(ready)SymCleanup(process);}};
void LoadModules(HANDLE process,Modules& local) {
    std::array<HMODULE,2048> modules{};DWORD bytes{};
    Require(K32EnumProcessModulesEx(process,modules.data(),sizeof(modules),&bytes,LIST_MODULES_64BIT)
        && bytes<=sizeof(modules) && bytes%sizeof(HMODULE)==0,"Cannot inspect frozen modules.");
    for(std::size_t i=0;i<bytes/sizeof(HMODULE);++i) {
        std::array<wchar_t,32768> path{};
        Require(K32GetModuleFileNameExW(process,modules[i],path.data(),static_cast<DWORD>(path.size()))!=0,
            "Cannot identify a frozen module.");
        const auto mapped=LoadLibraryExW(path.data(),nullptr,DONT_RESOLVE_DLL_REFERENCES);
        Require(mapped!=nullptr,"Cannot read a frozen module unwind image.");
        const auto base=reinterpret_cast<DWORD64>(modules[i]);local.values.push_back({base,mapped});
        const auto* data=reinterpret_cast<const unsigned char*>(mapped);
        const auto* dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(data);
        const auto* pe=reinterpret_cast<const IMAGE_NT_HEADERS64*>(data+dos->e_lfanew);
        const auto observed=vm_startup::ReadStopped(process,base+dos->e_lfanew,sizeof(*pe));
        IMAGE_NT_HEADERS64 remote{};std::memcpy(&remote,observed.data(),sizeof(remote));
        Require(remote.Signature==pe->Signature && remote.FileHeader.Machine==IMAGE_FILE_MACHINE_AMD64
            && remote.FileHeader.TimeDateStamp==pe->FileHeader.TimeDateStamp
            && remote.OptionalHeader.SizeOfImage==pe->OptionalHeader.SizeOfImage,"A frozen unwind image identity differs.");
        Require(SymLoadModuleExW(process,nullptr,path.data(),nullptr,base,pe->OptionalHeader.SizeOfImage,nullptr,0)==base,
            "Cannot load a native unwind table.");
    }
}
}
std::uintptr_t ImageBase(HANDLE process) {
    HMODULE image{};DWORD bytes{};
    Require(K32EnumProcessModulesEx(process,&image,sizeof(image),&bytes,LIST_MODULES_64BIT)!=FALSE && image,
        "Cannot find the owned image base.");
    return reinterpret_cast<std::uintptr_t>(image);
}
void AdmitPrimary(const late_startup::OwnedChild& child,late_startup::MappedGate& gate,Receipt& receipt) {
    Handle snapshot{CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD,0)};
    Require(snapshot.value!=INVALID_HANDLE_VALUE,"Cannot enumerate frozen threads.");
    THREADENTRY32 entry{sizeof(entry)};
    Require(Thread32First(snapshot.value,&entry)!=FALSE,"Cannot read frozen thread inventory.");
    do {
        if(entry.th32OwnerProcessID!=child.process.dwProcessId)continue;
        Require(receipt.threads.size()<64,"The frozen thread inventory exceeds its bound.");
        ++receipt.threadsObserved;
        Handle observed{OpenThread(THREAD_GET_CONTEXT|THREAD_QUERY_INFORMATION,FALSE,entry.th32ThreadID)};
        Require(observed.value!=nullptr && GetProcessIdOfThread(observed.value)==child.process.dwProcessId,
            "Cannot identify a frozen thread.");
        CONTEXT stopped{};stopped.ContextFlags=CONTEXT_CONTROL;
        using Query=NTSTATUS(NTAPI*)(HANDLE,ULONG,PVOID,ULONG,PULONG);
        const auto query=reinterpret_cast<Query>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"NtQueryInformationThread"));
        std::uintptr_t start{};
        Require(query && query(observed.value,9,&start,sizeof(start),nullptr)==0
            && GetThreadContext(observed.value,&stopped)!=FALSE,"Cannot read a frozen thread observation.");
        receipt.threads.push_back({entry.th32ThreadID,stopped.Rip,start});
    }while(Thread32Next(snapshot.value,&entry));
    Require(GetLastError()==ERROR_NO_MORE_FILES && receipt.threadsObserved==1
        && GetProcessIdOfThread(child.process.hThread)==child.process.dwProcessId
        && GetThreadId(child.process.hThread)==child.process.dwThreadId
        && receipt.threads.front().id==child.process.dwThreadId,"The original primary thread inventory differs.");
    CONTEXT context{};context.ContextFlags=CONTEXT_CONTROL|CONTEXT_INTEGER|CONTEXT_DEBUG_REGISTERS;
    Require(GetThreadContext(child.process.hThread,&context)!=FALSE,"Cannot read the frozen primary context.");
    Require(!context.Dr0 && !context.Dr1 && !context.Dr2 && !context.Dr3 && !(context.Dr7&0xff),
        "The primary thread has hardware breakpoints.");
    receipt.primaryPc=context.Rip;
    SymSetOptions(SYMOPT_DEFERRED_LOADS|SYMOPT_FAIL_CRITICAL_ERRORS|SYMOPT_NO_PROMPTS|SYMOPT_IGNORE_NT_SYMPATH);
    Symbols symbols{child.process.hProcess};
    Require(SymInitializeW(symbols.process,L"",FALSE)!=FALSE,"Cannot initialize native unwind reading.");symbols.ready=true;
    Require(SymRegisterCallback64(symbols.process,SymbolCallback,0)!=FALSE,"Cannot register frozen native memory reads.");
    Modules modules;LoadModules(symbols.process,modules);unwindModules=&modules;unwindRefused=false;
    unwindReceipt=&receipt;runtimeImageBase=receipt.patch.imageBase;
    UnwindScope unwindScope;
    const auto ntdll=GetModuleHandleW(L"ntdll.dll");
    const auto wait=reinterpret_cast<const unsigned char*>(GetProcAddress(ntdll,"NtWaitForMultipleObjects"));
    Require(wait!=nullptr,"The native wait export is missing.");
    const auto native=std::find_if(modules.values.begin(),modules.values.end(),[&](const auto& row){return row.second==ntdll;});
    Require(native!=modules.values.end(),"The native wait image was not admitted.");
    waitLeafStart=native->first+reinterpret_cast<DWORD64>(wait)-reinterpret_cast<DWORD64>(ntdll);waitLeafEnd=waitLeafStart+32;
    // This exact syscall stub does not change RSP. Native leaf unwind may read its return slot.
    Require(wait[0]==0x4c && wait[1]==0x8b && wait[2]==0xd1 && wait[3]==0xb8
        && wait[18]==0x0f && wait[19]==0x05 && wait[20]==0xc3
        && vm_startup::ReadStopped(symbols.process,waitLeafStart,32)==std::vector<unsigned char>(wait,wait+32)
        && context.Rip>=waitLeafStart && context.Rip<waitLeafEnd,"The primary is outside the verified native wait syscall.");
    STACKFRAME64 frame{};
    frame.AddrPC={context.Rip,0,AddrModeFlat};frame.AddrStack={context.Rsp,0,AddrModeFlat};frame.AddrFrame={context.Rbp,0,AddrModeFlat};
    for(unsigned int count=0;count<64;++count) {
        const auto walked=StackWalk64(IMAGE_FILE_MACHINE_AMD64,symbols.process,child.process.hThread,&frame,&context,
            ReadMemory,FunctionTable,SymGetModuleBase64,nullptr);
        Require(!unwindRefused,receipt.unwindReason.c_str());
        Require(walked!=FALSE,"The native unwind stopped before the verified entry anchor.");
        if(!frame.AddrPC.Offset)break;
        if(!receipt.frames.empty())Require(frame.AddrPC.Offset!=receipt.frames.back(),"Native unwind did not advance.");
        receipt.frames.push_back(frame.AddrPC.Offset);
        const auto state=gate.Read(child.process.hProcess);
        if(frame.AddrPC.Offset>=state.entryAnchorStart && frame.AddrPC.Offset<state.entryAnchorEnd)break;
    }
    unwindModules=nullptr;
    const auto state=gate.Read(child.process.hProcess);
    const std::array<std::uintptr_t,4> chain{gate.Base()+kGateWaitReturnRva,gate.Base()+kGateWrapperReturnRva,
        state.returnSite,state.wrapperCallerReturn};
    bool chainPresent=false,anchorPresent=false;
    for(std::size_t i=0;i+chain.size()<=receipt.frames.size();++i)
        if(std::equal(chain.begin(),chain.end(),receipt.frames.begin()+i))chainPresent=true;
    for(const auto pc:receipt.frames)if(pc>=state.entryAnchorStart && pc<state.entryAnchorEnd)anchorPresent=true;
    Require(!unwindRefused && chainPresent && anchorPresent,"The frozen primary is outside the exact native gate wait chain.");
    Require(receipt.runtimeMetadataMask==3,"DbgHelp did not read both pinned runtime CRT records through the frozen reader.");
    receipt.primaryAdmitted=true;
}
void AdmitEditFrames(const Receipt& receipt,std::span<const vm_startup::AddressEdit> edits) {
    const auto outside=[&](std::uintptr_t pc) {
        for(const auto& edit:edits)Require(pc<edit.address || pc>=edit.address+edit.original.size(),
            "A stopped PC or native frame overlaps a publication span.");
    };
    outside(receipt.primaryPc);for(const auto pc:receipt.frames)outside(pc);
}
}
