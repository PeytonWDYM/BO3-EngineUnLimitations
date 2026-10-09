#include "Plan.h"
#include "EarlyIntegrityProfile.h"
#include "../vm_startup/PausedPatch.h"
#include <bcrypt.h>
#include <algorithm>
#include <cstring>
#include <stdexcept>
#include <string>

namespace bo3::early_integrity {
namespace {
void Require(bool value,const char* message) {if(!value)throw std::runtime_error(message);}
std::string Hex(std::span<const unsigned char> bytes) {
    constexpr char digits[]="0123456789abcdef";
    std::string result;result.reserve(bytes.size()*2);
    for(const auto byte:bytes){result+=digits[byte>>4];result+=digits[byte&15];}
    return result;
}
std::vector<unsigned char> CaptureGuards(HANDLE process,std::uintptr_t imageBase) {
    std::vector<unsigned char> result;result.reserve(1024*1024);
    const auto append=[&](const auto& value) {
        const auto* begin=reinterpret_cast<const unsigned char*>(&value);
        result.insert(result.end(),begin,begin+sizeof(value));
    };
    const char magic[8]{'B','O','3','E','G','C','0','1'};
    append(magic);append(std::uint32_t{1});append(static_cast<std::uint32_t>(kGuards.size()));append(imageBase);
    result.insert(result.end(),kProfileId,kProfileId+64);
    result.insert(result.end(),kExecutableDigest.begin(),kExecutableDigest.end());
    append(kTimestamp);append(kImageSize);
    for(const auto& guard:kGuards) {
        MEMORY_BASIC_INFORMATION memory{};
        Require(VirtualQueryEx(process,reinterpret_cast<void*>(imageBase+guard.rva),&memory,sizeof(memory))==sizeof(memory),
            "Cannot query a frozen checksum diagnostic span.");
        append(guard.rva);append(guard.size);append(memory.State);append(memory.Type);append(memory.Protect);
        const auto bytes=vm_startup::ReadStopped(process,imageBase+guard.rva,guard.size);
        result.insert(result.end(),bytes.begin(),bytes.end());
    }
    return result;
}
std::int32_t Relative(std::uintptr_t destination,std::uintptr_t next) {
    if(destination>=next) {
        Require(destination-next<=INT32_MAX,"Early integrity displacement is unreachable.");
        return static_cast<std::int32_t>(destination-next);
    }
    Require(next-destination<=static_cast<std::uintptr_t>(INT32_MAX)+1,"Early integrity displacement is unreachable.");
    return static_cast<std::int32_t>(-static_cast<std::int64_t>(next-destination));
}
bool Overlap(std::uintptr_t address,size_t size,const vm_startup::AddressEdit& edit) {
    Require(!edit.original.empty() && edit.original.size()==edit.replacement.size()
        && edit.address<=UINTPTR_MAX-edit.original.size(),"Invalid early integrity exclusion edit.");
    return address<edit.address+edit.original.size() && edit.address<address+size;
}
void Exclude(std::uintptr_t address,size_t size,std::span<const vm_startup::AddressEdit> edits) {
    for(const auto& edit:edits)Require(!Overlap(address,size,edit),"Early integrity context overlaps an existing edit.");
}
void ImageMemory(HANDLE process,std::uintptr_t imageBase,std::uintptr_t address,size_t size,bool code) {
    const auto end=address+size;
    while(address<end) {
        MEMORY_BASIC_INFORMATION memory{};
        Require(VirtualQueryEx(process,reinterpret_cast<void*>(address),&memory,sizeof(memory))==sizeof(memory),"Cannot query early integrity image memory.");
        if(memory.State!=MEM_COMMIT || memory.Type!=MEM_IMAGE || memory.Protect!=PAGE_EXECUTE_READWRITE
            || reinterpret_cast<std::uintptr_t>(memory.AllocationBase)!=imageBase)
            throw std::runtime_error("Early integrity image ownership or protection differs at RVA "
                +std::to_string(address-imageBase)+", protection "+std::to_string(memory.Protect)+".");
        const auto start=reinterpret_cast<std::uintptr_t>(memory.BaseAddress);
        Require(start<=address && memory.RegionSize && start<=UINTPTR_MAX-memory.RegionSize
            && address<start+memory.RegionSize,"Early integrity memory region is invalid.");
        if(code)Require(std::any_of(kRegions.begin(),kRegions.end(),[&](const Region& r){
            return address>=imageBase+r.rva && end<=imageBase+r.rva+r.size;
        }),"Early integrity guard leaves the fixed code regions.");
        address=std::min(end,start+memory.RegionSize);
    }
}
struct Hasher {
    BCRYPT_ALG_HANDLE algorithm{};
    Hasher(){Require(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)==0,"Cannot open early integrity SHA256.");}
    ~Hasher(){if(algorithm)BCryptCloseAlgorithmProvider(algorithm,0);}
    std::array<unsigned char,32> Hash(std::span<unsigned char> bytes) {
        struct Owner {BCRYPT_HASH_HANDLE value{};~Owner(){if(value)BCryptDestroyHash(value);}} hash;
        Require(BCryptCreateHash(algorithm,&hash.value,nullptr,0,nullptr,0,0)==0,"Cannot create early integrity hash.");
        Require(BCryptHashData(hash.value,bytes.data(),static_cast<ULONG>(bytes.size()),0)==0,"Cannot hash early integrity guard.");
        std::array<unsigned char,32> result{};
        Require(BCryptFinishHash(hash.value,result.data(),static_cast<ULONG>(result.size()),0)==0,"Cannot finish early integrity hash.");
        return result;
    }
};
std::array<unsigned char,7> OriginalLea(const Site& site) {
    std::array<unsigned char,7> result{0x48,0x8d,0x15};
    const auto displacement=Relative(site.chainDestinationRva,site.leaRva+7);
    std::memcpy(result.data()+3,&displacement,sizeof(displacement));
    return result;
}
HANDLE Duplicate(HANDLE process) {
    HANDLE result{};
    Require(DuplicateHandle(GetCurrentProcess(),process,GetCurrentProcess(),&result,0,FALSE,DUPLICATE_SAME_ACCESS)!=FALSE,
        "Cannot retain early integrity child handle.");
    return result;
}
std::shared_ptr<RelayArena> Allocate(HANDLE process,std::uintptr_t imageBase) {
    SYSTEM_INFO system{};GetSystemInfo(&system);
    const auto reach=static_cast<std::uintptr_t>(INT32_MAX)-kImageSize-kArenaSize;
    const auto low=std::max(reinterpret_cast<std::uintptr_t>(system.lpMinimumApplicationAddress),imageBase>reach?imageBase-reach:0);
    const auto high=std::min(reinterpret_cast<std::uintptr_t>(system.lpMaximumApplicationAddress),imageBase+reach);
    for(auto address=low;address<high;) {
        MEMORY_BASIC_INFORMATION memory{};
        Require(VirtualQueryEx(process,reinterpret_cast<void*>(address),&memory,sizeof(memory))==sizeof(memory),"Cannot find early integrity relay memory.");
        const auto start=reinterpret_cast<std::uintptr_t>(memory.BaseAddress);
        Require(memory.RegionSize && start<=UINTPTR_MAX-memory.RegionSize,"Relay memory search overflows.");
        const auto end=start+memory.RegionSize;
        Require(end>address,"Relay memory search did not advance.");
        if(memory.State==MEM_FREE) {
            const auto aligned=(address+system.dwAllocationGranularity-1)&~(static_cast<std::uintptr_t>(system.dwAllocationGranularity)-1);
            if(aligned<high && kArenaSize<=high-aligned && aligned<=end && kArenaSize<=end-aligned) {
                struct Handle {HANDLE value;~Handle(){if(value)CloseHandle(value);}} owned{Duplicate(process)};
                if(auto* allocation=VirtualAllocEx(process,reinterpret_cast<void*>(aligned),kArenaSize,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READ)) {
                    try {
                        auto result=std::make_shared<RelayArena>(owned.value,reinterpret_cast<std::uintptr_t>(allocation));
                        owned.value=nullptr;
                        return result;
                    } catch(...) {VirtualFreeEx(process,allocation,0,MEM_RELEASE);throw;}
                }
            }
        }
        address=end;
    }
    throw std::runtime_error("No reachable early integrity relay arena.");
}
void Pieces(std::vector<vm_startup::AddressEdit>& edits,std::uintptr_t address,
    std::span<const unsigned char> original,std::span<const unsigned char> replacement) {
    while(!original.empty()) {
        const auto count=std::min(original.size(),static_cast<size_t>(4096-address%4096));
        edits.push_back({address,{original.begin(),original.begin()+count},{replacement.begin(),replacement.begin()+count}});
        address+=count;original=original.subspan(count);replacement=replacement.subspan(count);
    }
}
}
RelayArena::RelayArena(HANDLE process,std::uintptr_t address) noexcept:process_(process),address_(address) {}
RelayArena::~RelayArena() {
    if(!committed_)VirtualFreeEx(process_,reinterpret_cast<void*>(address_),0,MEM_RELEASE);
    CloseHandle(process_);
}
std::array<unsigned char,kRelayStride> EncodeRelay(const Site& site,std::uintptr_t imageBase,std::uintptr_t address) {
    Require(site.expectedTableSlot<128 && site.computedLocalSlot<128,"Early integrity frame offsets differ.");
    std::array<unsigned char,kRelayStride> code{};code.fill(0xcc);
    const unsigned char prefix[]{0x48,0x8b,0x55,site.expectedTableSlot,0x8b,0x02,0x89,0x45,site.computedLocalSlot,0x48,0x8d,0x15};
    std::copy(std::begin(prefix),std::end(prefix),code.begin());
    const auto destination=Relative(imageBase+site.chainDestinationRva,address+16);
    std::memcpy(code.data()+12,&destination,4);
    code[16]=0xe9;
    const auto continuation=Relative(imageBase+site.leaRva+7,address+21);
    std::memcpy(code.data()+17,&continuation,4);
    return code;
}
PreparedPlan PrepareStopped(HANDLE process,std::uintptr_t imageBase,std::span<const vm_startup::AddressEdit> existingEdits) {
    Require(imageBase && imageBase<=UINTPTR_MAX-kImageSize-static_cast<std::uintptr_t>(INT32_MAX),"Early integrity image address overflows.");
    SYSTEM_INFO system{};GetSystemInfo(&system);
    Require(system.dwPageSize==4096 && imageBase%system.dwPageSize==0,"Early integrity page layout differs.");
    const auto dosBytes=vm_startup::ReadStopped(process,imageBase,sizeof(IMAGE_DOS_HEADER));
    IMAGE_DOS_HEADER dos{};std::memcpy(&dos,dosBytes.data(),sizeof(dos));
    Require(dos.e_magic==IMAGE_DOS_SIGNATURE && dos.e_lfanew>=static_cast<LONG>(sizeof(dos))
        && static_cast<std::uint32_t>(dos.e_lfanew)<=kImageSize-sizeof(IMAGE_NT_HEADERS64),"Early integrity DOS identity differs.");
    const auto peBytes=vm_startup::ReadStopped(process,imageBase+dos.e_lfanew,sizeof(IMAGE_NT_HEADERS64));
    IMAGE_NT_HEADERS64 pe{};std::memcpy(&pe,peBytes.data(),sizeof(pe));
    Require(pe.Signature==IMAGE_NT_SIGNATURE && pe.FileHeader.Machine==IMAGE_FILE_MACHINE_AMD64
        && pe.FileHeader.TimeDateStamp==kTimestamp && pe.OptionalHeader.Magic==IMAGE_NT_OPTIONAL_HDR64_MAGIC
        && pe.OptionalHeader.SizeOfImage==kImageSize,"Early integrity PE identity differs.");
    Require(kSites.size()==kSiteCount && !kGuards.empty(),"Early integrity profile is incomplete.");
    Hasher hasher;
    for(const auto& guard:kGuards) {
        Require(guard.size && guard.size<=125 && guard.rva<=kImageSize-guard.size
            && guard.firstPointer<=kImagePointers.size() && guard.pointerCount<=kImagePointers.size()-guard.firstPointer,
            "Early integrity guard metadata differs.");
        const auto address=imageBase+guard.rva;
        ImageMemory(process,imageBase,address,guard.size,true);
        Exclude(address,guard.size,existingEdits);
        auto bytes=vm_startup::ReadStopped(process,address,guard.size);
        std::uint32_t priorEnd=0;
        for(size_t index=0;index<guard.pointerCount;++index) {
            const auto& pointer=kImagePointers[guard.firstPointer+index];
            Require(guard.size>=8 && pointer.offset<=guard.size-8 && pointer.offset>=priorEnd && pointer.targetRva<kImageSize,
                "Early integrity pointer metadata differs.");
            std::uintptr_t actual{};std::memcpy(&actual,bytes.data()+pointer.offset,8);
            Require(actual==imageBase+pointer.targetRva,"Early integrity image pointer differs.");
            std::fill_n(bytes.begin()+pointer.offset,8,static_cast<unsigned char>(0));
            priorEnd=pointer.offset+8;
        }
        const auto actual=hasher.Hash(bytes);
        if(actual!=guard.digest)throw ContextMismatch("Early integrity context differs at RVA "+std::to_string(guard.rva)
            +" expected="+Hex(guard.digest)+" actual="+Hex(actual)+" bytes="+Hex(bytes),CaptureGuards(process,imageBase));
    }
    for(size_t index=0;index<kSites.size();++index) {
        const auto& site=kSites[index];
        Require(site.leaRva<=kImageSize-7 && site.storeRva<=kImageSize-67 && site.expectedRva<=kImageSize-4
            && site.chainDestinationRva<=kImageSize-4 && site.expectedTableSlot<128 && site.computedLocalSlot<128,
            "Early integrity site metadata differs.");
        if(index)Require(kSites[index-1].leaRva+7<=site.leaRva,"Early integrity source sites overlap.");
        const auto expected=imageBase+site.expectedRva,chain=imageBase+site.chainDestinationRva;
        ImageMemory(process,imageBase,expected,4,false);ImageMemory(process,imageBase,chain,4,false);
        Exclude(expected,4,existingEdits);Exclude(chain,4,existingEdits);
        const auto original=OriginalLea(site);
        Require(vm_startup::ReadStopped(process,imageBase+site.leaRva,7)==std::vector<unsigned char>(original.begin(),original.end()),
            "Early integrity original LEA differs.");
        for(const auto& other:kSites)Require(site.leaRva+7<=other.storeRva
            || other.storeRva+(other.splitInstaller?67:7)<=site.leaRva,"Early integrity hook changes AAE installer bytes.");
    }
    PreparedPlan result;
    result.arena=Allocate(process,imageBase);
    std::vector<unsigned char> arena(kArenaSize,0xcc);
    for(size_t index=0;index<kSites.size();++index) {
        const auto code=EncodeRelay(kSites[index],imageBase,result.arena->address()+index*kRelayStride);
        std::copy(code.begin(),code.end(),arena.begin()+index*kRelayStride);
    }
    const auto originalArena=vm_startup::ReadStopped(process,result.arena->address(),kArenaSize);
    Require(std::all_of(originalArena.begin(),originalArena.end(),[](unsigned char byte){return byte==0;}),"New early integrity arena is not zeroed.");
    Exclude(result.arena->address(),kArenaSize,existingEdits);
    // Publish every relay page before publishing any source jump in the same stopped transaction.
    Pieces(result.edits,result.arena->address(),originalArena,arena);
    for(size_t index=0;index<kSites.size();++index) {
        const auto& site=kSites[index];
        const auto original=OriginalLea(site);
        std::array<unsigned char,7> replacement{0xe9,0,0,0,0,0x90,0x90};
        const auto displacement=Relative(result.arena->address()+index*kRelayStride,imageBase+site.leaRva+5);
        std::memcpy(replacement.data()+1,&displacement,4);
        Pieces(result.edits,imageBase+site.leaRva,original,replacement);
    }
    Require(result.edits.size()==kPublicationCount,"Early integrity publication count differs.");
    return result;
}
}
