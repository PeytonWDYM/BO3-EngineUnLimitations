#include "../../patches/vm_migration/MigrationPlan.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

using namespace bo3::migration;
namespace {
void Check(bool value) { if (!value) throw std::runtime_error("migration plan assertion"); }
struct Region {
    void* pointer;
    Region(std::size_t bytes, DWORD allocation) : pointer(VirtualAlloc(nullptr, bytes, allocation, PAGE_READWRITE)) { Check(pointer != nullptr); }
    ~Region() { VirtualFree(pointer, 0, MEM_RELEASE); }
    std::uintptr_t Base() const { return reinterpret_cast<std::uintptr_t>(pointer); }
};
void Commit(std::uintptr_t address) {
    Check(VirtualAlloc(reinterpret_cast<void*>(address & ~std::uintptr_t{4095}),4096,MEM_COMMIT,PAGE_READWRITE)!=nullptr);
}
std::uint32_t Number(std::ifstream& file) {
    std::uint32_t value; file.read(reinterpret_cast<char*>(&value),4); Check(file.good()); return value;
}
std::vector<unsigned char> Snapshot(const std::vector<vm_startup::AddressEdit>& edits) {
    std::vector<unsigned char> result;
    for (const auto& edit : edits) {
        const auto bytes=vm_startup::ReadStopped(GetCurrentProcess(),edit.address,edit.original.size());
        result.insert(result.end(),bytes.begin(),bytes.end());
    }
    return result;
}
std::vector<DWORD> Protections(const std::vector<vm_startup::AddressEdit>& edits) {
    std::vector<DWORD> result;
    for(const auto& edit:edits) {
        MEMORY_BASIC_INFORMATION memory{};
        Check(VirtualQuery(reinterpret_cast<const void*>(edit.address),&memory,sizeof(memory))==sizeof(memory));
        result.push_back(memory.Protect);
    }
    return result;
}
void Save(const std::filesystem::path& path,const std::vector<unsigned char>& bytes) {
    std::ofstream file(path,std::ios::binary); file.write(reinterpret_cast<const char*>(bytes.data()),bytes.size()); Check(file.good());
}
template<class F> void Refused(F action) {
    bool failed=false; try { action(); } catch (const std::runtime_error&) { failed=true; } Check(failed);
}
}
int main(int argc,char** argv) {
    try {
        Check(argc==3);
        constexpr std::uint32_t imageBytes=494186496;
        Region image(imageBytes+65536,MEM_RESERVE),helper(32768,MEM_RESERVE|MEM_COMMIT);
        const auto relay=image.Base()+imageBytes+4096; Commit(relay);
        std::ifstream seed(argv[1],std::ios::binary); Check(seed.good());
        const auto records=Number(seed);
        for (std::uint32_t i=0;i<records;++i) {
            const auto rva=Number(seed), count=Number(seed); Check(rva<imageBytes && count<=imageBytes-rva && count<=8);
            Commit(image.Base()+rva);
            seed.read(reinterpret_cast<char*>(image.Base()+rva),count); Check(seed.good());
            DWORD discarded=0;
            Check(VirtualProtect(reinterpret_cast<void*>((image.Base()+rva)&~std::uintptr_t{4095}),4096,PAGE_EXECUTE_READ,&discarded)!=FALSE);
        }
        MigrationPlanInput input{{image.Base(),imageBytes},{helper.Base(),32768},
            {0x2000,0x2040,0x2050,0x2060,0x2098,{0x100,0x120,0x140,0x160,0x180,0x1a0},
             {0x300,0x320,0x340,0x360,0x380,0x3a0},0x1c0,0x1e0},relay+64};
        const auto migration=BuildMigrationPlan(input); Check(migration.size()==16);
        std::size_t podBytes=0; for(std::size_t i=0;i<5;++i) podBytes+=migration[i].original.size(); Check(podBytes==168);
        Check(migration[5].original.size()==128 && migration[12].replacement[0]==0xe8 && migration[13].replacement[0]==0xe9);
        Check(migration[8].replacement.size()==8 && migration[8].replacement[5]==0x90 && migration[11].replacement.size()==6);
        Refused([&]{auto bad=input;bad.total=1000001;BuildMigrationPlan(bad);});
        Refused([&]{auto bad=input;bad.clientRoots=10;BuildMigrationPlan(bad);});
        Refused([&]{auto bad=input;bad.bufferBytes=39321600;BuildMigrationPlan(bad);});
        Refused([&]{auto bad=input;bad.exports.bindings=32767;BuildMigrationPlan(bad);});
        Refused([&]{auto bad=input;bad.exports.versionBranches=bad.exports.bindings;BuildMigrationPlan(bad);});
        Refused([&]{auto bad=input;bad.relay=input.image.base+0x100000000ull;BuildMigrationPlan(bad);});
        Refused([&]{auto bad=input;bad.image.base=UINTPTR_MAX-16;BuildMigrationPlan(bad);});
        const vm_startup::NativePlanInput core{input.image,input.helper,
            {{{0x12d52f0,{0x48,0x89,0x5c,0x24,0x10}},{0x12d5f20,{0x48,0x89,0x5c,0x24,0x08}},
              {0x12d9420,{0x40,0x53,0x49,0x8b,0xd8}},{0x20ec0b0,{0x4c,0x89,0x4c,0x24,0x20}}}},
            {0x3000,0x3030,0x700,0x720,0x740,0x760,0x780,0x7a0,0x7c0,0x7e0,0x800,0x820},
            relay,500001,18,8,bo3::vm::NativeModePolicy::ZombiesOnly,{}};
        auto composed=vm_startup::BuildNativePlan(core); composed.insert(composed.end(),migration.begin(),migration.end());
        const auto original=Snapshot(composed); Save(std::filesystem::path(argv[2])/"before.bin",original);
        const auto protections=Protections(composed);
        vm_startup::Receipt rollback;
        {
            vm_startup::PausedPatch patch(GetCurrentProcess(),composed,rollback); patch.Apply();
            Save(std::filesystem::path(argv[2])/"applied.bin",Snapshot(composed));
            Check(Snapshot(composed)!=original && rollback.editsWritten==composed.size());
            Check(Protections(composed)==protections);
        }
        Check(rollback.rollbackCompleted && Snapshot(composed)==original && Protections(composed)==protections);
        auto damaged=composed; damaged.back().original[0]^=1;
        vm_startup::Receipt rejected;
        Refused([&]{vm_startup::PausedPatch patch(GetCurrentProcess(),damaged,rejected);patch.Apply();});
        Check(rejected.editsWritten==0 && Snapshot(composed)==original);
        vm_startup::Receipt installed;
        {vm_startup::PausedPatch patch(GetCurrentProcess(),composed,installed);patch.Apply();patch.Commit();}
        std::vector<vm_startup::AddressEdit> removal;
        for(const auto& edit:composed) removal.push_back({edit.address,edit.replacement,edit.original});
        vm_startup::Receipt removed;
        {vm_startup::PausedPatch patch(GetCurrentProcess(),removal,removed);patch.Apply();patch.Commit();}
        Check(Snapshot(composed)==original); Save(std::filesystem::path(argv[2])/"restored.bin",Snapshot(composed));
        Check(Protections(composed)==protections);
        std::ofstream receipt(std::filesystem::path(argv[2])/"plan-addresses.txt");
        receipt<<"imageBase "<<std::hex<<image.Base()<<"\nhelperBase "<<helper.Base()<<"\ncoreRelay "<<relay
               <<"\nmigrationRelay "<<input.relay<<"\n";
        const auto restoredProtections=Protections(composed);
        for(std::size_t i=0;i<composed.size();++i)
            receipt<<"edit "<<composed[i].address<<" bytes "<<std::dec<<composed[i].original.size()<<std::hex
                   <<" protectionBefore "<<protections[i]<<" protectionRestored "<<restoredProtections[i]<<"\n";
        Check(receipt.good());
        std::cout<<"checked-policy-helper-bounds-relative-reach passed\n"
                 <<"all-168-POD-bytes-eight-relays-and-native-original-guards passed\n"
                 <<"composed-core-migration-apply-rollback-and-removal passed\n";
        return 0;
    } catch(const std::exception& error) {std::cerr<<error.what()<<'\n';return 1;}
}
