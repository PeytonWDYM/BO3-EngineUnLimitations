#include "Fixture.h"
#include "../../patches/code_integrity/Plan.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include "../../launch/process_freeze/NativeJobFreeze.h"
#include "Profile.h"
#include <fstream>
#include <filesystem>
#include <stdexcept>
#include <string>

void Check(bool,const char*);
struct Handle {
    HANDLE value{};
    ~Handle(){if(value)CloseHandle(value);}
};
void Change(HANDLE process,std::uintptr_t address,const void* bytes,size_t size) {
    SIZE_T written{};
    Check(WriteProcessMemory(process,reinterpret_cast<void*>(address),bytes,size,&written) && written==size,"Owned mutation failed.");
}
int wmain(int argc,wchar_t** argv) {
    try {
        Check(argc==3,"Use case and new private receipt path.");
        const std::wstring scenario=argv[1];
        std::string caseName;
        for(const auto character:scenario) {Check(character>=L'a'&&character<=L'z',"Invalid owned case name.");caseName.push_back(static_cast<char>(character));}
        const std::filesystem::path output=argv[2];
        Check(!std::filesystem::exists(output),"Receipt already exists.");
        ProveSemantics();
        wchar_t executable[MAX_PATH]{};
        Check(GetModuleFileNameW(nullptr,executable,MAX_PATH)>0,"Cannot locate owned runner.");
        const auto directory=std::filesystem::path(executable).parent_path();
        const auto imagePath=directory/L"IntegrityOwnedImage.dll";
        const auto target=directory/L"IntegrityOwnedTarget.exe";
        const auto suffix=std::to_wstring(GetCurrentProcessId())+L"-"+scenario;
        const auto mappingName=L"Local\\IntegrityProof-map-"+suffix;
        const auto readyName=L"Local\\IntegrityProof-ready-"+suffix;
        const auto doneName=L"Local\\IntegrityProof-done-"+suffix;
        Handle mapping{CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(FixtureState),mappingName.c_str())};
        Handle ready{CreateEventW(nullptr,TRUE,FALSE,readyName.c_str())};
        Handle done{CreateEventW(nullptr,TRUE,FALSE,doneName.c_str())};
        Handle job{CreateJobObjectW(nullptr,nullptr)};
        Check(mapping.value && ready.value && done.value && job.value,"Cannot create owned proof objects.");
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        Check(SetInformationJobObject(job.value,JobObjectExtendedLimitInformation,&limits,sizeof(limits))!=FALSE,"Cannot configure owned job.");
        auto* state=static_cast<FixtureState*>(MapViewOfFile(mapping.value,FILE_MAP_ALL_ACCESS,0,0,sizeof(FixtureState)));
        Check(state!=nullptr,"Cannot map owned state.");
        std::wstring command=L"\""+target.wstring()+L"\" \""+mappingName+L"\" \""+readyName+L"\" \""+doneName+L"\" \""+imagePath.wstring()+L"\"";
        STARTUPINFOW startup{sizeof(startup)};PROCESS_INFORMATION info{};
        Check(CreateProcessW(target.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_SUSPENDED|CREATE_NO_WINDOW,nullptr,directory.c_str(),&startup,&info)!=FALSE,"Cannot create owned inert child.");
        Handle process{info.hProcess};Handle thread{info.hThread};
        Check(AssignProcessToJobObject(job.value,process.value)!=FALSE,"Cannot assign owned child.");
        const auto identity=process_freeze::ReadIdentity(process.value);
        Check(ResumeThread(thread.value)!=static_cast<DWORD>(-1),"Cannot start owned child.");
        Check(WaitForSingleObject(ready.value,10000)==WAIT_OBJECT_0,"Owned child did not become ready.");
        process_freeze::NativeJobApi api;
        Check(process_freeze::ChangeOwnedJobFreeze(api,job.value,process.value,identity,true)>=0,"Cannot freeze owned job.");
        auto imageBase=state->imageBase;
        if(scenario==L"private") {
            auto* clone=VirtualAllocEx(process.value,nullptr,bo3::code_integrity::kImageSize,MEM_COMMIT|MEM_RESERVE,PAGE_EXECUTE_READWRITE);
            Check(clone!=nullptr,"Cannot allocate owned private-memory refusal fixture.");
            const auto cloneBase=reinterpret_cast<std::uintptr_t>(clone);
            const auto header=vm_startup::ReadStopped(process.value,imageBase,4096);
            Change(process.value,cloneBase,header.data(),header.size());
            for(const auto& region:bo3::code_integrity::kRegions) {
                const auto bytes=vm_startup::ReadStopped(process.value,imageBase+region.rva,region.size);
                Change(process.value,cloneBase+region.rva,bytes.data(),bytes.size());
            }
            imageBase=cloneBase;
        }
        const auto first=imageBase+bo3::code_integrity::kRecords.front().rva;
        const auto baseline=vm_startup::ReadStopped(process.value,first,8);
        std::vector<vm_startup::AddressEdit> existing;
        auto digest=bo3::code_integrity::kExecutableDigest;
        if(scenario==L"identity")digest[0]^=1;
        if(scenario==L"guard" || scenario==L"original") {
            const unsigned char changed=0xcc;
            Change(process.value,scenario==L"guard" ? first+6 : first,&changed,1);
        }
        if(scenario==L"context") {const unsigned char changed=0xcc;Change(process.value,first-1,&changed,1);}
        if(scenario==L"pointer") {const std::uintptr_t changed=imageBase+1;Change(process.value,first+8,&changed,sizeof(changed));}
        if(scenario==L"timestamp" || scenario==L"machine" || scenario==L"size") {
            IMAGE_DOS_HEADER dos{};
            const auto bytes=vm_startup::ReadStopped(process.value,imageBase,sizeof(dos));
            std::memcpy(&dos,bytes.data(),sizeof(dos));
            DWORD prior{};
            Check(VirtualProtectEx(process.value,reinterpret_cast<void*>(imageBase),4096,PAGE_READWRITE,&prior)!=FALSE,"Cannot change owned PE header.");
            auto pe=vm_startup::ReadStopped(process.value,imageBase+dos.e_lfanew,sizeof(IMAGE_NT_HEADERS64));
            IMAGE_NT_HEADERS64 header{};std::memcpy(&header,pe.data(),sizeof(header));
            if(scenario==L"timestamp")header.FileHeader.TimeDateStamp^=1;
            if(scenario==L"machine")header.FileHeader.Machine=IMAGE_FILE_MACHINE_I386;
            if(scenario==L"size")header.OptionalHeader.SizeOfImage^=4096;
            Change(process.value,imageBase+dos.e_lfanew,&header,sizeof(header));
            DWORD discarded{};Check(VirtualProtectEx(process.value,reinterpret_cast<void*>(imageBase),4096,prior,&discarded)!=FALSE,"Cannot restore owned header protection.");
        }
        if(scenario==L"protection") {DWORD prior{};Check(VirtualProtectEx(process.value,reinterpret_cast<void*>(first),1,PAGE_EXECUTE_READ,&prior)!=FALSE,"Cannot change owned protection.");}
        if(scenario==L"overlap")existing.push_back({first,{baseline[0]},{0x90}});
        vm_startup::Receipt receipt;
        bool refused=false,committed=false,restored=false;
        std::string failure;
        std::vector<vm_startup::AddressEdit> edits;
        try {
            const auto planBase=scenario==L"overflow"||scenario==L"production" ? UINTPTR_MAX-bo3::code_integrity::kImageSize+1 : imageBase;
            if(scenario==L"production")digest.fill(0);
            edits=bo3::code_integrity::PrepareStopped(scenario==L"production" ? nullptr : process.value,planBase,digest,existing);
            Check(edits.size()==1353,"Owned endpoint count differs.");
            {
                vm_startup::PausedPatch transaction(process.value,edits,receipt);
                transaction.Apply();
                if(scenario==L"rollback")throw std::runtime_error("Injected later transaction failure.");
                if(scenario==L"rollbackfailed") {
                    using Unmap=NTSTATUS(NTAPI*)(HANDLE,PVOID);
                    const auto unmap=reinterpret_cast<Unmap>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"NtUnmapViewOfSection"));
                    Check(unmap!=nullptr&&unmap(process.value,reinterpret_cast<void*>(imageBase))>=0,"Cannot unmap the owned refusal fixture.");
                    throw std::runtime_error("Injected owned image loss before rollback.");
                }
                transaction.Commit();committed=true;
            }
        } catch(const std::exception& error) {refused=true;failure=error.what();}
        for(const auto& edit:edits)if(scenario!=L"rollbackfailed") {
            Check(vm_startup::ReadStopped(process.value,edit.address,edit.original.size())==(committed ? edit.replacement : edit.original),"Owned readback differs.");
            MEMORY_BASIC_INFORMATION memory{};
            Check(VirtualQueryEx(process.value,reinterpret_cast<void*>(edit.address),&memory,sizeof(memory))==sizeof(memory) && memory.Protect==PAGE_EXECUTE_READWRITE,"Owned protection differs after transaction.");
        }
        // Input-transform fingerprints remain original after both commit and rollback.
        for(const auto& record:bo3::code_integrity::kRecords)if(scenario!=L"rollbackfailed"&&record.family==bo3::code_integrity::Family::InputTransform) {
            const auto original=bo3::code_integrity::Original(record.family);
            Check(vm_startup::ReadStopped(process.value,imageBase+record.rva,original.size())==std::vector<unsigned char>(original.begin(),original.end()),"Input transform changed.");
        }
        restored=receipt.rollbackCompleted;
        if(scenario==L"success")Check(committed&&!refused&&receipt.editsWritten==1353,"Owned success failed.");
        else if(scenario==L"rollback")Check(refused&&!committed&&restored&&receipt.editsWritten==1353,"Owned rollback failed.");
        else if(scenario==L"rollbackfailed")Check(refused&&!committed&&!restored&&receipt.editsWritten==1353,"Owned failed rollback was not retained.");
        else {
            Check(refused&&!committed&&receipt.editsWritten==0,"A refused case wrote bytes.");
            const char* expected="";
            if(scenario==L"identity")expected="executable identity";
            else if(scenario==L"guard"||scenario==L"original"||scenario==L"context")expected="context differs";
            else if(scenario==L"pointer")expected="transport address";
            else if(scenario==L"timestamp"||scenario==L"machine"||scenario==L"size")expected="PE identity";
            else if(scenario==L"protection"||scenario==L"private")expected="image memory or protection";
            else if(scenario==L"overlap")expected="overlaps an engine edit";
            else if(scenario==L"overflow")expected="image address overflows";
            else if(scenario==L"production")expected="attributed exclusively";
            else Check(false,"Unknown owned case.");
            Check(failure.find(expected)!=std::string::npos,"The owned refusal reason differs.");
        }
        if(scenario==L"rollbackfailed")Check(TerminateJobObject(job.value,97)!=FALSE,"Cannot terminate the still-frozen owned child.");
        else {
            Check(process_freeze::ChangeOwnedJobFreeze(api,job.value,process.value,identity,false)>=0,"Cannot thaw owned job.");
            Check(SetEvent(done.value)!=FALSE,"Cannot finish owned child.");
        }
        Check(WaitForSingleObject(process.value,10000)==WAIT_OBJECT_0,"Owned child did not exit.");
        DWORD exit{};Check(GetExitCodeProcess(process.value,&exit)&&exit==(scenario==L"rollbackfailed"?97u:0u),"Owned child exit differs.");
        UnmapViewOfFile(state);
        std::ofstream stream(output);
        stream<<"{\"passed\":true,\"case\":\""<<caseName<<"\",\"admittedRecords\":"<<(edits.empty()?0:1365)<<",\"editsWritten\":"<<receipt.editsWritten<<",\"committed\":"<<(committed?"true":"false")<<",\"rollbackCompleted\":"<<(restored?"true":"false")<<",\"terminatedWhileFrozen\":"<<(scenario==L"rollbackfailed"?"true":"false")<<",\"semanticsPairs\":27,\"gameExecution\":false}";
        Check(stream.good(),"Cannot write owned receipt.");
        return 0;
    }catch(const std::exception& error){fprintf(stderr,"%s\n",error.what());return 1;}
}
