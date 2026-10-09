#include "Contract.h"
#include "../../patches/vm_startup/DebugGate.h"
#include "../../launch/preentry/Identity.h"
#include "BuildIdentity.h"
#ifdef VM_STARTUP_COMPOSED
#include "ComposedPlan.h"
#include <detours.h>
#endif
#include <fstream>
#include <iostream>
#include <string>

namespace {
Shared* observed;
void Ready(const vm_startup::Receipt&) {
    if(observed->scenario==Scenario::ReadyDenied) throw std::runtime_error("Owned readiness refusal after paused edits.");
    ++observed->readyCalls;
    observed->readyBeforeCount = observed->calls == 0 && observed->done == 0;
}
struct LockedFiles {
    std::vector<HANDLE> values;
    ~LockedFiles() { for (const auto value : values) CloseHandle(value); }
};
struct Child {
    PROCESS_INFORMATION info{};
    bool finished = false;
    ~Child() {
        if (info.hProcess) {
            if (!finished) {
                TerminateProcess(info.hProcess, 97);
                DebugActiveProcessStop(info.dwProcessId);
                WaitForSingleObject(info.hProcess, 5000);
            }
            CloseHandle(info.hProcess);
            CloseHandle(info.hThread);
        }
    }
};
Scenario Parse(const std::wstring& name) {
    const std::pair<const wchar_t*, Scenario> names[]{
        {L"entry",Scenario::Entry},{L"tls",Scenario::Tls},{L"worker",Scenario::Worker},
        {L"concurrent",Scenario::Concurrent},{L"mismatch",Scenario::Mismatch},{L"existing",Scenario::Existing},
        {L"no-call",Scenario::NoCall},{L"fault",Scenario::Fault},{L"client-first",Scenario::ClientFirst},{L"foreign",Scenario::Foreign},
        {L"single-step",Scenario::SingleStep},{L"trace-gate",Scenario::TraceGate},{L"repeated",Scenario::Repeated},
        {L"existing-hash",Scenario::ExistingHash},{L"missing-readiness",Scenario::HelperNoReady},
        {L"absent",Scenario::HelperAbsent},{L"dirty-binding",Scenario::HelperDirty},
        {L"hook-mismatch",Scenario::HookMismatch},{L"ready-denied",Scenario::ReadyDenied}};
    for (const auto& [text, value] : names) if (name == text) return value;
    throw std::runtime_error("Use a fixed owned scenario.");
}
std::vector<unsigned char> Count(DWORD count) {
    return {static_cast<unsigned char>(count),static_cast<unsigned char>(count >> 8),
        static_cast<unsigned char>(count >> 16),static_cast<unsigned char>(count >> 24)};
}
}
int wmain(int argc, wchar_t** argv) {
    try {
        Require(argc == 4, "Use VmStartupFixture SCENARIO TOTAL PRIVATE_JSON.");
        const std::wstring name = argv[1];
        const bool composed=name.starts_with(L"helper-");
        const bool baseline = name == L"baseline";
        const auto scenario = baseline ? Scenario::Entry : Parse(composed ? name.substr(7) : name);
        const auto total = static_cast<DWORD>(std::stoul(argv[2]));
        Require(total == 130000 || total == 500001 || total == 1000001, "Use a declared fixture count.");
        const auto output = PrivateOutput(argv[3]);
        wchar_t path[32768]{};
        Require(GetModuleFileNameW(nullptr, path, 32768) != 0, "Cannot find the fixture directory.");
        const auto directory = std::filesystem::path(path).parent_path();
        const auto target = directory / L"VmStartupTarget.exe";
        LockedFiles files; files.values.reserve(3);
        VerifyFile(target, kTargetHash, files.values);
#ifdef VM_STARTUP_COMPOSED
        VerifyFile(directory/L"VmStartupConsumer.dll",kConsumerHash,files.values);
        if(composed) VerifyFile(directory/L"VmStartupHelper.dll",kHelperHash,files.values);
#else
        Require(!composed,"Build the fixed composition before using helper scenarios.");
#endif
        const HMODULE mapped = LoadLibraryExW(target.c_str(), nullptr, DONT_RESOLVE_DLL_REFERENCES);
        Require(mapped != nullptr, "Cannot inspect the fixed owned PE exports.");
        const auto base = reinterpret_cast<std::uintptr_t>(mapped);
        const auto gate = reinterpret_cast<std::uintptr_t>(GetProcAddress(mapped, "GateCode"));
        const auto pool = reinterpret_cast<std::uintptr_t>(GetProcAddress(mapped, "PoolPointer"));
        const auto hash = reinterpret_cast<std::uintptr_t>(GetProcAddress(mapped, "HashPointer"));
        Require(gate > base && pool > base && hash > base, "The fixed owned exports are missing.");
        const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
        const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
        vm_startup::Profile profile{nt->OptionalHeader.SizeOfImage,static_cast<DWORD>(gate-base),static_cast<DWORD>(pool-base),
            static_cast<DWORD>(hash-base),{}, {}};
        const std::vector<unsigned char> plain{0xb8,0xd0,0xfb,0x01,0x00,0xc3};
        for (const DWORD offset : {0ul,64ul}) {
            profile.checks.push_back({profile.entryRva + offset, plain});
            profile.edits.push_back({profile.entryRva + offset + 1,Count(130000),Count(total)});
        }
        SECURITY_ATTRIBUTES attributes{sizeof(attributes),nullptr,TRUE};
        Handle mapping(CreateFileMappingW(INVALID_HANDLE_VALUE,&attributes,PAGE_READWRITE,0,sizeof(Shared),nullptr));
        Require(mapping.value != nullptr, "Cannot create owned trace mapping.");
        auto* shared = static_cast<Shared*>(MapViewOfFile(mapping.value,FILE_MAP_WRITE,0,0,sizeof(Shared)));
        Require(shared != nullptr, "Cannot map owned trace.");
        ZeroMemory(shared,sizeof(*shared)); shared->scenario=scenario; shared->expectedTotal=total;
        shared->wantHelper=composed;
        observed = shared;
#ifdef VM_STARTUP_COMPOSED
        if(composed) {
            const auto helper=LoadLibraryExW((directory/L"VmStartupHelper.dll").c_str(),nullptr,DONT_RESOLVE_DLL_REFERENCES);
            Require(helper!=nullptr,"Cannot inspect the fixed helper exports.");
            SetComposedPlan(shared,mapped,helper,profile.entryRva);
            FreeLibrary(helper);
        }
#endif
        FreeLibrary(mapped);
        const auto mappingText=std::to_wstring(reinterpret_cast<std::uintptr_t>(mapping.value));
        Require(SetEnvironmentVariableW(L"OWNED_VM_STARTUP_MAPPING",mappingText.c_str()) != FALSE,"Cannot set owned trace.");
        SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
        STARTUPINFOW startup{}; startup.cb=sizeof(startup);
        Child child;
        std::wstring command=L"\""+target.wstring()+L"\"";
        BOOL created=FALSE;
#ifdef VM_STARTUP_COMPOSED
        if(composed && scenario!=Scenario::HelperAbsent) {
            const auto helperWide=(directory/L"VmStartupHelper.dll").wstring();
            BOOL substituted=FALSE;
            char helperPath[32768]{};
            Require(WideCharToMultiByte(CP_ACP,WC_NO_BEST_FIT_CHARS,helperWide.c_str(),-1,helperPath,32768,nullptr,&substituted)>0
                && !substituted,"The fixed helper path cannot use Detours ANSI encoding.");
            LPCSTR helpers[]{helperPath};
            created=DetourCreateProcessWithDllsW(target.c_str(),command.data(),nullptr,nullptr,TRUE,
                CREATE_NO_WINDOW|DEBUG_ONLY_THIS_PROCESS,nullptr,directory.c_str(),&startup,&child.info,1,helpers,CreateProcessW);
        } else
#endif
        created=CreateProcessW(target.c_str(),command.data(),nullptr,nullptr,TRUE,
            CREATE_NO_WINDOW | (baseline ? 0 : DEBUG_ONLY_THIS_PROCESS),nullptr,directory.c_str(),&startup,&child.info);
        Require(created != FALSE,
            "Cannot create fixed owned child.");
        vm_startup::Receipt receipt;
        std::string rejection;
        DWORD observedBeforeTermination[2]{};
        bool compositionRestored=false;
        if (!baseline) {
            try {
#ifdef VM_STARTUP_COMPOSED
                vm_startup::Activate(child.info,profile,receipt,Ready,composed ? PrepareComposed : nullptr);
#else
                vm_startup::Activate(child.info,profile,receipt,Ready);
#endif
            }
            catch (const std::exception& error) {
                rejection=error.what();
                SIZE_T read=0;
                for (DWORD index=0;index<2;++index)
                    ReadProcessMemory(child.info.hProcess,reinterpret_cast<void*>(receipt.imageBase+profile.entryRva+index*64+1),
                        &observedBeforeTermination[index],sizeof(DWORD),&read);
#ifdef VM_STARTUP_COMPOSED
                if(composed) compositionRestored=CompositionOriginal(child.info.hProcess,receipt.imageBase);
#endif
                TerminateProcess(child.info.hProcess,97);
                DebugActiveProcessStop(child.info.dwProcessId);
            }
        }
        Require(WaitForSingleObject(child.info.hProcess,30000)==WAIT_OBJECT_0,"The owned child did not stop.");
        child.finished=true;
        DWORD exit=0;
        Require(GetExitCodeProcess(child.info.hProcess,&exit) != FALSE,"Cannot read the owned child exit.");
        const bool negative = scenario==Scenario::Mismatch || scenario==Scenario::Existing || scenario==Scenario::Foreign
            || scenario==Scenario::Repeated || scenario==Scenario::ExistingHash || scenario==Scenario::HelperNoReady
            || scenario==Scenario::HelperAbsent || scenario==Scenario::HelperDirty || scenario==Scenario::HookMismatch
            || scenario==Scenario::ReadyDenied;
        const bool noGate = scenario==Scenario::NoCall || scenario==Scenario::Fault;
        std::uint64_t expectedReceipt = 14695981039346656037ull;
        for (DWORD id=1; id<total; ++id) expectedReceipt=(expectedReceipt^id)*1099511628211ull;
        bool passed = false;
        if (negative) passed = !rejection.empty() && receipt.editsWritten==(scenario==Scenario::ReadyDenied ? 5ul : 0ul) && !shared->done
            && observedBeforeTermination[0]==(scenario==Scenario::Repeated ? total : 130000)
            && observedBeforeTermination[1]==(scenario==Scenario::Repeated ? total : 130000);
        else if (noGate) passed=!receipt.activated && receipt.exited && receipt.editsWritten==0
            && (scenario==Scenario::NoCall ? exit==0 : exit==0xe0427654);
        else passed=exit==0 && shared->done==1 && shared->errors==0 && shared->visited==total-1
            && shared->allocationBytes==static_cast<std::uint64_t>(total)*64
            && shared->idReceipt==expectedReceipt
            && (baseline || (receipt.activated && receipt.editsWritten==(composed ? 5ul : 2ul) && receipt.restoredThreads>0));
        if(composed) {
            if(negative) passed &= compositionRestored && !receipt.activated;
            else passed &= shared->helperAtImport==1 && shared->helperAtTls==1 && shared->configZeroAtLoad==1
                && shared->hookReads==shared->calls && shared->hookWrites==shared->calls
                && shared->originalReads==shared->calls && shared->originalWrites==shared->calls
                && shared->originalInserts==shared->calls;
        }
        if(scenario==Scenario::ReadyDenied) passed &= receipt.rollbackCompleted && shared->readyCalls==0;
        if (!baseline && !negative && !noGate)
            passed &= shared->readyCalls==1 && shared->readyBeforeCount==1 && shared->debuggerPresent==1
                && receipt.restoredThreads==receipt.armedThreads;
        if (scenario==Scenario::Tls) passed &= shared->beforeEntry==1;
        if (scenario==Scenario::Worker) passed &= shared->workerId==shared->returnedId
            && shared->resumeCount==1 && shared->priority==THREAD_PRIORITY_BELOW_NORMAL;
        if (scenario==Scenario::Concurrent) passed &= shared->calls==8 && receipt.retainedThreads>=9;
        if (scenario==Scenario::ClientFirst) passed &= shared->clientTotal==65000 && shared->calls==2;
        if (scenario==Scenario::SingleStep || scenario==Scenario::TraceGate) passed &= shared->forwarded==1;
        std::ofstream out(output);
        out << "{\"passed\":" << (passed?"true":"false") << ",\"scenario\":\"";
        for (const auto character : name) out<<static_cast<char>(character);
        out << "\",\"total\":"<<total<<",\"targetExit\":"<<exit<<",\"activated\":"<<receipt.activated
            <<",\"armedThreads\":"<<receipt.armedThreads<<",\"restoredThreads\":"<<receipt.restoredThreads
            <<",\"retainedThreads\":"<<receipt.retainedThreads
            <<",\"editsWritten\":"<<receipt.editsWritten<<",\"rejection\":\""<<rejection<<"\""
            <<",\"pendingTraps\":"<<receipt.pendingTraps
            <<",\"rollbackCompleted\":"<<receipt.rollbackCompleted<<",\"compositionRestored\":"<<compositionRestored
            <<",\"allocationBytes\":"<<shared->allocationBytes<<",\"visited\":"<<shared->visited
            <<",\"idReceipt\":"<<shared->idReceipt<<",\"calls\":"<<shared->calls
            <<",\"expectedIdReceipt\":"<<expectedReceipt
            <<",\"beforeEntry\":"<<shared->beforeEntry<<",\"clientTotal\":"<<shared->clientTotal
            <<",\"readyCalls\":"<<shared->readyCalls<<",\"readyBeforeCount\":"<<shared->readyBeforeCount
            <<",\"debuggerPresent\":"<<shared->debuggerPresent<<",\"forwarded\":"<<shared->forwarded
            <<",\"helperAtImport\":"<<shared->helperAtImport<<",\"helperAtTls\":"<<shared->helperAtTls
            <<",\"configZeroAtLoad\":"<<shared->configZeroAtLoad<<",\"hookReads\":"<<shared->hookReads
            <<",\"hookWrites\":"<<shared->hookWrites<<",\"originalReads\":"<<shared->originalReads
            <<",\"originalWrites\":"<<shared->originalWrites<<",\"originalInserts\":"<<shared->originalInserts
            <<",\"oldCounts\":["<<observedBeforeTermination[0]<<','<<observedBeforeTermination[1]<<"]}\n";
        Require(out.good(),"Cannot write the private receipt.");
        UnmapViewOfFile(shared);
        std::cout << (passed?"PASS ":"FAIL ") << output.string() << '\n';
        return passed?0:2;
    } catch (const std::exception& error) { std::cerr<<error.what()<<'\n'; return 2; }
}
