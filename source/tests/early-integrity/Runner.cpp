#include "Fixture.h"
#include "../../patches/early_integrity/Plan.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include "../../launch/process_freeze/NativeJobFreeze.h"
#include "EarlyIntegrityProfile.h"
#include <algorithm>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <chrono>

namespace integrity=bo3::early_integrity;
namespace {
void Check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
struct Handle {HANDLE value{};~Handle(){if(value)CloseHandle(value);}};
void Change(HANDLE process,std::uintptr_t address,const void* bytes,size_t size) {
    SIZE_T count{};
    Check(WriteProcessMemory(process,reinterpret_cast<void*>(address),bytes,size,&count)&&count==size,"Owned mutation failed.");
}
}
int wmain(int argc,wchar_t** argv) {
    try {
        Check(argc==3,"Use case and private receipt path.");
        const std::wstring scenario=argv[1];
        const std::filesystem::path output=argv[2];
        Check(!std::filesystem::exists(output),"Receipt already exists.");
        if(scenario==L"semantics") {
            ProveRelays();
            std::ofstream stream(output);stream<<"{\"passed\":true,\"case\":\"semantics\",\"descriptors\":1069,\"executions\":6414,\"gameExecution\":false}";
            Check(stream.good(),"Cannot write relay proof.");return 0;
        }
        std::string caseName;
        for(const auto c:scenario){Check(c>=L'a'&&c<=L'z',"Invalid case name.");caseName.push_back(static_cast<char>(c));}
        wchar_t executable[MAX_PATH]{};Check(GetModuleFileNameW(nullptr,executable,MAX_PATH)>0,"Cannot locate runner.");
        const auto directory=std::filesystem::path(executable).parent_path();
        const auto target=directory/L"EarlyIntegrityOwnedTarget.exe";
        const auto image=directory/L"EarlyIntegrityOwnedImage.dll";
        const auto suffix=std::to_wstring(GetCurrentProcessId())+L"-"+scenario;
        const auto mapName=L"Local\\EarlyIntegrity-map-"+suffix;
        const auto readyName=L"Local\\EarlyIntegrity-ready-"+suffix;
        const auto doneName=L"Local\\EarlyIntegrity-done-"+suffix;
        Handle mapping{CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(FixtureState),mapName.c_str())};
        Handle ready{CreateEventW(nullptr,TRUE,FALSE,readyName.c_str())},done{CreateEventW(nullptr,TRUE,FALSE,doneName.c_str())};
        Handle job{CreateJobObjectW(nullptr,nullptr)};
        Check(mapping.value&&ready.value&&done.value&&job.value,"Cannot create owned proof objects.");
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        Check(SetInformationJobObject(job.value,JobObjectExtendedLimitInformation,&limits,sizeof(limits))!=FALSE,"Cannot configure owned job.");
        auto* state=static_cast<FixtureState*>(MapViewOfFile(mapping.value,FILE_MAP_ALL_ACCESS,0,0,sizeof(FixtureState)));
        Check(state!=nullptr,"Cannot map fixture state.");
        std::wstring command=L"\""+target.wstring()+L"\" \""+mapName+L"\" \""+readyName+L"\" \""+doneName+L"\" \""+image.wstring()+L"\"";
        STARTUPINFOW startup{sizeof(startup)};PROCESS_INFORMATION info{};
        Check(CreateProcessW(target.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_SUSPENDED|CREATE_NO_WINDOW,nullptr,directory.c_str(),&startup,&info)!=FALSE,"Cannot create owned child.");
        Handle process{info.hProcess},thread{info.hThread};
        Check(AssignProcessToJobObject(job.value,process.value)!=FALSE,"Cannot assign owned child.");
        const auto identity=process_freeze::ReadIdentity(process.value);
        Check(ResumeThread(thread.value)!=static_cast<DWORD>(-1),"Cannot start owned child.");
        Check(WaitForSingleObject(ready.value,10000)==WAIT_OBJECT_0,"Owned child did not become ready.");
        process_freeze::NativeJobApi api;
        Check(process_freeze::ChangeOwnedJobFreeze(api,job.value,process.value,identity,true)>=0,"Cannot freeze owned child.");
        auto base=state->imageBase;
        auto digest=integrity::kExecutableDigest;
        std::vector<vm_startup::AddressEdit> existing;
        const auto& first=integrity::kSites.front();
        auto changeByte=[&](std::uint32_t rva){auto byte=vm_startup::ReadStopped(process.value,base+rva,1)[0];byte^=1;Change(process.value,base+rva,&byte,1);};
        if(scenario==L"identity")digest[0]^=1;
        if(scenario==L"source")changeByte(first.leaRva);
        if(scenario==L"store")changeByte(first.storeRva);
        if(scenario==L"context")changeByte(integrity::kGuards.front().rva);
        if(scenario==L"pointer") {
            const auto& g=*std::find_if(integrity::kGuards.begin(),integrity::kGuards.end(),[](const auto& v){return v.pointerCount>0;});
            const auto pointer=base+1;Change(process.value,base+g.rva+integrity::kImagePointers[g.firstPointer].offset,&pointer,8);
        }
        if(scenario==L"scan") {
            const auto& site=*std::find_if(integrity::kSites.begin(),integrity::kSites.end(),[](const auto& v){return v.splitInstaller;});
            changeByte(site.storeRva+63);
        }
        if(scenario==L"expected") {
            const std::uint32_t changed=0xabc12345;
            for(const auto& site:integrity::kSites)Change(process.value,base+site.expectedRva,&changed,4);
        }
        if(scenario==L"overlap" || scenario==L"expectedoverlap" || scenario==L"chainoverlap") {
            const auto rva=scenario==L"overlap"?first.leaRva:scenario==L"expectedoverlap"?first.expectedRva:first.chainDestinationRva;
            const auto byte=vm_startup::ReadStopped(process.value,base+rva,1)[0];existing.push_back({base+rva,{byte},{0x90}});
        }
        if(scenario==L"protection") {DWORD prior{};Check(VirtualProtectEx(process.value,reinterpret_cast<void*>(base+first.leaRva),7,PAGE_EXECUTE_READ,&prior)!=FALSE,"Cannot change owned protection.");}
        if(scenario==L"machine" || scenario==L"timestamp" || scenario==L"size") {
            const auto offset=vm_startup::ReadStopped(process.value,base+0x3c,4);DWORD pe{};std::memcpy(&pe,offset.data(),4);
            DWORD prior{};Check(VirtualProtectEx(process.value,reinterpret_cast<void*>(base),4096,PAGE_READWRITE,&prior)!=FALSE,"Cannot change owned header.");
            changeByte(pe+(scenario==L"machine"?4:scenario==L"timestamp"?8:24+56));
            DWORD discarded{};Check(VirtualProtectEx(process.value,reinterpret_cast<void*>(base),4096,prior,&discarded)!=FALSE,"Cannot restore owned header.");
        }
        if(scenario==L"private") {
            const auto clone=VirtualAllocEx(process.value,nullptr,integrity::kImageSize,MEM_RESERVE,PAGE_EXECUTE_READWRITE);
            Check(clone!=nullptr,"Cannot allocate private refusal fixture.");
            const auto header=vm_startup::ReadStopped(process.value,base,4096);
            const auto firstRva=integrity::kGuards.front().rva;
            const auto guard=vm_startup::ReadStopped(process.value,base+firstRva,integrity::kGuards.front().size);
            base=reinterpret_cast<std::uintptr_t>(clone);
            Check(VirtualAllocEx(process.value,clone,4096,MEM_COMMIT,PAGE_EXECUTE_READWRITE)==clone,"Cannot commit private fixture header.");
            const auto page=base+(firstRva&~4095u);
            Check(VirtualAllocEx(process.value,reinterpret_cast<void*>(page),4096,MEM_COMMIT,PAGE_EXECUTE_READWRITE)==reinterpret_cast<void*>(page),"Cannot commit private fixture guard.");
            Change(process.value,base,header.data(),header.size());Change(process.value,base+firstRva,guard.data(),guard.size());
        }
        std::vector<std::vector<unsigned char>> installerBefore;
        if(scenario==L"success" || scenario==L"expected" || scenario==L"rollback")
            for(const auto& site:integrity::kSites)installerBefore.push_back(vm_startup::ReadStopped(process.value,base+site.storeRva,site.splitInstaller?67:7));
        const auto begin=std::chrono::steady_clock::now();
        bool refused=false,committed=false,arenaFreed=false;
        std::string failure;
        vm_startup::Receipt receipt;
        integrity::PreparedPlan plan;
        std::uintptr_t arenaAddress{};
        try {
            plan=integrity::PrepareStopped(process.value,scenario==L"overflow"?UINTPTR_MAX-integrity::kImageSize+1:base,digest,existing);
            arenaAddress=plan.arena->address();
            Check(plan.edits.size()==integrity::kPublicationCount,"Owned publication count differs.");
            {
                vm_startup::PausedPatch transaction(process.value,plan.edits,receipt);transaction.Apply();
                if(scenario==L"rollback")throw std::runtime_error("Injected later failure.");
                transaction.Commit();plan.arena->Commit();committed=true;
            }
        } catch(const std::exception& error){refused=true;failure=error.what();fprintf(stderr,"%s\n",failure.c_str());}
        const auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-begin).count();
        Check(elapsed<30000,"Owned preparation exceeds stopped budget.");
        for(const auto& edit:plan.edits) {
            Check(vm_startup::ReadStopped(process.value,edit.address,edit.original.size())==(committed?edit.replacement:edit.original),"Owned transaction readback differs.");
            MEMORY_BASIC_INFORMATION memory{};Check(VirtualQueryEx(process.value,reinterpret_cast<void*>(edit.address),&memory,sizeof(memory))==sizeof(memory),"Cannot query owned readback.");
            Check(memory.Protect==static_cast<DWORD>(edit.address>=arenaAddress && edit.address<arenaAddress+integrity::kArenaSize?PAGE_EXECUTE_READ:PAGE_EXECUTE_READWRITE),"Owned protection changed.");
        }
        if(committed || scenario==L"rollback") {
            for(size_t index=0;index<integrity::kSites.size();++index) {
                const auto& site=integrity::kSites[index];
                Check(vm_startup::ReadStopped(process.value,base+site.storeRva,site.splitInstaller?67:7)==installerBefore[index],"AAE installer inputs changed.");
                const unsigned char bytes[]{0x89,0x04,0x8a};
                Check(vm_startup::ReadStopped(process.value,base+site.storeRva,3)==std::vector<unsigned char>(std::begin(bytes),std::end(bytes)),"Original AAE store changed.");
                if(!site.splitInstaller) {
                    const auto bytesAfter=vm_startup::ReadStopped(process.value,base+site.storeRva+3,4);DWORD word{};std::memcpy(&word,bytesAfter.data(),4);
                    Check((word&0xff00ffff)==0xff004583 && ((word>>16)&0xff)==site.indexSlot,"AAE intact installer admission changed.");
                } else {
                    const auto& bytesAfter=installerBefore[index];
                    const auto matches=[&](size_t offset){return (bytesAfter[offset+3]&0xf0)==0x40 && bytesAfter[offset+4]==0x8d && (bytesAfter[offset+5]&0xc7)==5;};
                    size_t offset=0;while(offset<61 && !matches(offset))++offset;
                    Check(offset<61 && offset+10<=bytesAfter.size(),"AAE split installer target is absent.");
                    std::int32_t displacement{};std::memcpy(&displacement,bytesAfter.data()+offset+6,4);
                    const auto destination=static_cast<std::uintptr_t>(static_cast<std::int64_t>(base+site.storeRva+offset+10)+displacement);
                    Check(destination>=base && destination<base+integrity::kImageSize,"AAE split installer target leaves the image.");
                }
            }
        }
        plan.arena.reset();
        if(arenaAddress) {
            MEMORY_BASIC_INFORMATION memory{};Check(VirtualQueryEx(process.value,reinterpret_cast<void*>(arenaAddress),&memory,sizeof(memory))==sizeof(memory),"Cannot inspect arena lifetime.");
            arenaFreed=memory.State==MEM_FREE;
            Check(committed?!arenaFreed:arenaFreed,"Owned arena lifetime differs.");
        }
        if(scenario==L"success" || scenario==L"expected")Check(committed&&!refused&&receipt.editsWritten==1079,"Owned commit failed.");
        else if(scenario==L"rollback")Check(refused&&!committed&&receipt.rollbackCompleted&&arenaFreed,"Owned rollback failed.");
        else Check(refused&&!committed&&receipt.editsWritten==0&&!arenaAddress,"Owned refusal allocated or wrote.");
        Check(process_freeze::ChangeOwnedJobFreeze(api,job.value,process.value,identity,false)>=0,"Cannot thaw owned child.");
        Check(SetEvent(done.value)!=FALSE&&WaitForSingleObject(process.value,10000)==WAIT_OBJECT_0,"Owned child did not exit.");
        DWORD exit{};Check(GetExitCodeProcess(process.value,&exit)&&exit==0,"Owned child exit differs.");
        UnmapViewOfFile(state);
        std::ofstream stream(output);
        stream<<"{\"passed\":true,\"case\":\""<<caseName<<"\",\"preparationMilliseconds\":"<<elapsed
              <<",\"editsWritten\":"<<receipt.editsWritten<<",\"committed\":"<<(committed?"true":"false")
              <<",\"rollbackCompleted\":"<<(receipt.rollbackCompleted?"true":"false")<<",\"arenaFreed\":"<<(arenaFreed?"true":"false")
              <<",\"originalAAEStores\":1069,\"gameExecution\":false}";
        Check(stream.good(),"Cannot write owned receipt.");return 0;
    }catch(const std::exception& error){fprintf(stderr,"%s\n",error.what());return 1;}
}
