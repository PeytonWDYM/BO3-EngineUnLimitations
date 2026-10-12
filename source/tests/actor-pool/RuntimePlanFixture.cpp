#include "../../patches/actor_pool/RuntimePlan.h"
#include "../../patches/actor_pool/RuntimeBinding.h"
#include "../../patches/actor_pool/NativeLoadBridge.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include "RuntimeProfile.generated.h"
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <cstring>

namespace {
void Require(bool value,const char* message) {if(!value)throw std::runtime_error(message);}
}
// A private sparse seed contains guard spans only. The fixture never starts the game.
int main(int argc,char** argv) {
    try {
        Require(argc==3||argc==4,"Use a private seed and a result path.");
        auto process=GetCurrentProcess();
        constexpr std::uint32_t imageSize=494186496;
        const auto requested=argc==4?static_cast<std::uintptr_t>(std::stoull(argv[3],nullptr,0)):0;
        auto* image=VirtualAlloc(reinterpret_cast<void*>(requested),imageSize,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
        auto* helper=VirtualAlloc(nullptr,0x10000,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);
        Require(image&&helper,"Fixture image allocation failed.");
        std::ifstream seed(argv[1],std::ios::binary);
        std::uint32_t count{};seed.read(reinterpret_cast<char*>(&count),sizeof count);
        for(std::uint32_t index=0;index<count;++index) {
            std::uint32_t rva{},size{};seed.read(reinterpret_cast<char*>(&rva),4);seed.read(reinterpret_cast<char*>(&size),4);
            Require(size&&rva<=imageSize-size,"Fixture seed span is invalid.");
            seed.read(static_cast<char*>(image)+rva,size);
        }
        seed.read(reinterpret_cast<char*>(&count),sizeof count);
        for(std::uint32_t index=0;index<count;++index) {
            std::uint32_t rva{},target{};seed.read(reinterpret_cast<char*>(&rva),4);seed.read(reinterpret_cast<char*>(&target),4);
            const auto pointer=reinterpret_cast<std::uintptr_t>(image)+target;
            std::memcpy(static_cast<unsigned char*>(image)+rva,&pointer,8);
        }
        Require(bool(seed),"Fixture seed is incomplete.");
        DWORD originalProtection{};
        Require(VirtualProtect(static_cast<unsigned char*>(image)+0xC7000,0x1000,PAGE_EXECUTE_READ,&originalProtection)!=0&&
            VirtualProtect(static_cast<unsigned char*>(image)+0xC8000,0x1000,PAGE_READONLY,&originalProtection)!=0,
            "Fixture source protection failed.");
        const vm_startup::ImageRange game{reinterpret_cast<std::uintptr_t>(image),imageSize};
        const vm_startup::ImageRange module{reinterpret_cast<std::uintptr_t>(helper),0x10000};
        const bo3::actors::HelperOffsets offsets{0x100,0x200,0x300,0x400,0x500,0x600,0x700,0x800,0x900,0xA00,0xB00,0xC00,0xD00,0xE00,0xF00};
        bool refused=false;try {auto rejected=bo3::actors::BuildRuntimePlan(process,{game.base,game.size-1},module,offsets);}catch(const std::exception&){refused=true;}
        Require(refused,"Fixture unknown image size passed.");
        auto crossing=offsets;crossing.nativeBindings=0xFF8;
        refused=false;try {auto rejected=bo3::actors::BuildRuntimePlan(process,game,module,crossing);}catch(const std::exception&){refused=true;}
        Require(refused,"Fixture crossing helper binding passed.");
        auto plan=bo3::actors::BuildRuntimePlan(process,game,module,offsets);
        Require(plan.edits.size()>254,"Fixture plan omitted source or helper edits.");
        auto arena=plan.arena->Base();
        Require(arena>=game.base+game.size&&arena+plan.arena->Size()<=game.base+0x7FFFFFFF,"Fixture arena exceeds relative reach.");
        MEMORY_BASIC_INFORMATION info{};
        for(const auto [offset,protection]:{std::pair<std::size_t,DWORD>{0,PAGE_EXECUTE_READ},{0x200000,PAGE_READONLY},{0x400000,PAGE_READWRITE}}) {
            Require(VirtualQuery(reinterpret_cast<void*>(arena+offset),&info,sizeof info)==sizeof info&&info.Protect==protection,"Fixture arena protection differs.");
        }
        for(const auto& edit:plan.edits) {
            Require(edit.original.size()==edit.replacement.size(),"Fixture edit extent differs.");
            Require(edit.address/0x1000==(edit.address+edit.replacement.size()-1)/0x1000,"Fixture publication crosses a page.");
            Require(std::memcmp(reinterpret_cast<void*>(edit.address),edit.original.data(),edit.original.size())==0,"Fixture original bytes differ.");
        }
        vm_startup::Receipt rollback{};
        {
        vm_startup::PausedPatch publication(process,plan.edits,rollback);publication.Apply();
        const auto& runtime=*reinterpret_cast<const bo3::actors::RuntimeBindings*>(module.base+offsets.runtimeBindings);
        Require(runtime.functionCount==std::size(bo3::actors::profile::Functions)+bo3::actors::profile::ExtraFunctionCount&&runtime.phaseCount==std::size(bo3::actors::profile::Phases),"Fixture runtime inventory differs.");
        const auto& counts=*reinterpret_cast<const bo3::actors::LoadBindings*>(module.base+offsets.countBindings)->counts;
        Require(std::memcmp(&counts,&bo3::actors::LegacyCounts,sizeof counts)==0,"Fixture initial load counts differ.");
        const auto& bindings=*reinterpret_cast<const bo3::actors::NativeBindings*>(module.base+offsets.nativeBindings);
        const auto& branches=*reinterpret_cast<const bo3::actors::ReadBranches*>(module.base+offsets.readBranches);
        Require(reinterpret_cast<std::uintptr_t>(bindings.whole)==module.base+offsets.wholeReentry&&branches.whole==game.base+0x19C3277,"Fixture whole-load binding differs.");
        for(std::uint32_t actor=0;actor<500;++actor) {
            const auto* record=bindings.actors+actor*0x2110;
            std::uintptr_t vtable{};std::uint32_t positive{},negative{};
            std::memcpy(&vtable,record+0x8A0,8);std::memcpy(&positive,record+0x8B0,4);std::memcpy(&negative,record+0x8C0,4);
            Require(vtable==game.base+0x2F1BB88&&positive==0x7E967699&&negative==0xFE967699,"Fixture constructor defaults differ.");
        }
        for(std::uint32_t index=0;index<runtime.functionCount;++index) {
            const auto& row=runtime.functions[index];
            const auto* unwind=reinterpret_cast<const unsigned char*>(game.base+row.UnwindData);
            Require(row.BeginAddress<row.EndAddress&&row.UnwindData>=arena-game.base+0x200000&&row.UnwindData<arena-game.base+0x400000,"Fixture unwind row exceeds its region.");
            if((unwind[0]>>3)&4) {
                const auto* parent=reinterpret_cast<const RUNTIME_FUNCTION*>(unwind+4+((unwind[2]+1)&~1u)*2);
                bool found=false;for(std::uint32_t other=0;other<runtime.functionCount;++other)if(std::memcmp(parent,runtime.functions+other,12)==0){found=true;break;}
                Require(found,"Fixture chained row has no new parent.");
            }
        }
        for(std::uint32_t index=0;index<runtime.phaseCount;++index) {
            const auto& phase=runtime.phases[index];const auto& source=bo3::actors::profile::Phases[index];
            Require(reinterpret_cast<std::uintptr_t>(phase.function)==game.base+source.owner&&phase.controlPc==game.base+source.control&&
                reinterpret_cast<std::uintptr_t>(phase.handler)==game.base+source.handler&&reinterpret_cast<std::uintptr_t>(phase.handlerData)==game.base+source.data,
                "Fixture native phase mapping differs.");
        }
        Require(RtlAddFunctionTable(runtime.functions,runtime.functionCount,game.base)!=0,"Fixture runtime registration failed.");
        for(std::uint32_t index=0;index<runtime.functionCount;++index) {
            DWORD64 base{};
            Require(RtlLookupFunctionEntry(game.base+runtime.functions[index].BeginAddress,&base,nullptr)==runtime.functions+index&&base==game.base,"Fixture runtime lookup differs.");
        }
        Require(RtlDeleteFunctionTable(runtime.functions)!=0,"Fixture runtime removal failed.");
        }
        Require(rollback.rollbackCompleted&&rollback.editsWritten==plan.edits.size(),"Fixture PausedPatch rollback failed.");
        for(const auto& [rva,protection]:{std::pair<std::uintptr_t,DWORD>{0xC7000,PAGE_EXECUTE_READ},{0xC8000,PAGE_READONLY}})
            Require(VirtualQuery(reinterpret_cast<void*>(game.base+rva),&info,sizeof info)==sizeof info&&info.Protect==protection,"Fixture rollback changed source protection.");
        for(const auto& edit:plan.edits)Require(std::memcmp(reinterpret_cast<void*>(edit.address),edit.original.data(),edit.original.size())==0,"Fixture rollback bytes differ.");
        plan.arena.reset();
        Require(VirtualQuery(reinterpret_cast<void*>(arena),&info,sizeof info)==sizeof info&&info.State==MEM_FREE,"Fixture rollback retained its arena.");
        auto retained=bo3::actors::BuildRuntimePlan(process,game,module,offsets);arena=retained.arena->Base();
        vm_startup::Receipt installed{};
        {
            vm_startup::PausedPatch publication(process,retained.edits,installed);publication.Apply();publication.Commit();retained.arena->Commit();
        }
        Require(installed.editsWritten==retained.edits.size()&&!installed.rollbackCompleted,"Fixture PausedPatch commit failed.");
        retained.arena.reset();
        Require(VirtualQuery(reinterpret_cast<void*>(arena),&info,sizeof info)==sizeof info&&info.State==MEM_COMMIT,"Fixture commit released its arena.");
        auto removal=retained.edits;for(auto& edit:removal)std::swap(edit.original,edit.replacement);
        vm_startup::Receipt removed{};
        {vm_startup::PausedPatch publication(process,std::move(removal),removed);publication.Apply();publication.Commit();}
        Require(removed.editsWritten==retained.edits.size(),"Fixture PausedPatch removal failed.");
        for(const auto& edit:retained.edits)Require(std::memcmp(reinterpret_cast<void*>(edit.address),edit.original.data(),edit.original.size())==0,"Fixture removal bytes differ.");
        Require(VirtualFree(reinterpret_cast<void*>(arena),0,MEM_RELEASE)!=0,"Fixture retained arena removal failed.");
        auto* byte=static_cast<unsigned char*>(image)+0x19C00B0;*byte^=1;
        refused=false;try {auto rejected=bo3::actors::BuildRuntimePlan(process,game,module,offsets);}catch(const std::exception&){refused=true;}
        Require(refused,"Fixture changed guard passed.");*byte^=1;
        auto* pointer=reinterpret_cast<std::uintptr_t*>(static_cast<unsigned char*>(image)+0x33B1480);++*pointer;
        refused=false;try {auto rejected=bo3::actors::BuildRuntimePlan(process,game,module,offsets);}catch(const std::exception&){refused=true;}
        Require(refused,"Fixture changed image pointer passed.");--*pointer;
        *reinterpret_cast<std::uintptr_t*>(static_cast<unsigned char*>(image)+0xA1B0798)=1;
        refused=false;try {auto rejected=bo3::actors::BuildRuntimePlan(process,game,module,offsets);}catch(const std::exception&){refused=true;}
        Require(refused,"Fixture allocated actor pool passed.");
        *reinterpret_cast<std::uintptr_t*>(static_cast<unsigned char*>(image)+0xA1B0798)=0;
        *reinterpret_cast<std::uintptr_t*>(static_cast<unsigned char*>(image)+0xA1B0790)=1;
        refused=false;try {auto rejected=bo3::actors::BuildRuntimePlan(process,game,module,offsets);}catch(const std::exception&){refused=true;}
        Require(refused,"Fixture allocated sentient pool passed.");
        *reinterpret_cast<std::uintptr_t*>(static_cast<unsigned char*>(image)+0xA1B0790)=0;
        for(const auto& edit:plan.edits)Require(std::memcmp(reinterpret_cast<void*>(edit.address),edit.original.data(),edit.original.size())==0,"Fixture refusal changed publication bytes.");
        VirtualFree(helper,0,MEM_RELEASE);VirtualFree(image,0,MEM_RELEASE);
        std::ofstream(argv[2])<<"{\"passed\":true,\"sourceEdits\":"<<plan.edits.size()<<",\"gameBase\":"<<game.base<<",\"runtimeFunctions\":"<<std::size(bo3::actors::profile::Functions)+bo3::actors::profile::ExtraFunctionCount
            <<",\"phases\":"<<std::size(bo3::actors::profile::Phases)<<",\"transaction\":\"vm_startup::PausedPatch\",\"rollback\":true,\"commit\":true,\"removal\":true,\"pageBounded\":true,\"helperPageRefusal\":true,\"guardRefusal\":true,\"pointerRefusal\":true,\"poolRefusal\":true,\"gameLaunches\":0}\n";
        return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
