#include "Plan.h"
#include "Profile.h"
#include "../vm_startup/PausedPatch.h"
#include <bcrypt.h>
#include <algorithm>
#include <cstring>
#include <stdexcept>
namespace bo3::code_integrity {
namespace {
constexpr std::array<unsigned char,6> xorOriginal{0x8b,0x0c,0x8b,0x33,0x0c,0x82};
constexpr std::array<unsigned char,8> negOriginal{0x8b,0x0c,0x8b,0xf7,0xd9,0x03,0x0c,0x82};
constexpr std::array<unsigned char,8> cmpOriginal{0x8b,0x04,0x82,0x8b,0x14,0x8b,0x3b,0xc2};
constexpr std::array<unsigned char,6> xorReplacement{0x8b,0x0c,0x8b,0x31,0xc9,0x90};
constexpr std::array<unsigned char,8> negReplacement{0x8b,0x0c,0x8b,0x31,0xc9,0x90,0x90,0x90};
constexpr std::array<unsigned char,8> cmpReplacement{0x8b,0x04,0x82,0x8b,0x14,0x8b,0x3b,0xc0};
void Require(bool value,const char* message) {if(!value)throw std::runtime_error(message);}
std::array<unsigned char,32> Digest(std::span<const unsigned char> bytes) {
    struct Algorithm {BCRYPT_ALG_HANDLE value{};~Algorithm(){if(value)BCryptCloseAlgorithmProvider(value,0);}} algorithm;
    struct Hash {BCRYPT_HASH_HANDLE value{};~Hash(){if(value)BCryptDestroyHash(value);}} hash;
    Require(BCryptOpenAlgorithmProvider(&algorithm.value,BCRYPT_SHA256_ALGORITHM,nullptr,0)==0,"Cannot open integrity SHA256.");
    Require(BCryptCreateHash(algorithm.value,&hash.value,nullptr,0,nullptr,0,0)==0,"Cannot create integrity SHA256.");
    Require(BCryptHashData(hash.value,const_cast<PUCHAR>(bytes.data()),static_cast<ULONG>(bytes.size()),0)==0,"Cannot hash integrity guard.");
    std::array<unsigned char,32> result{};
    Require(BCryptFinishHash(hash.value,result.data(),static_cast<ULONG>(result.size()),0)==0,"Cannot finish integrity SHA256.");
    return result;
}
bool InsideRegion(std::uint32_t rva,std::uint32_t size) {
    return std::any_of(kRegions.begin(),kRegions.end(),[&](const Region& region){
        return rva>=region.rva && size<=region.size && rva-region.rva<=region.size-size;
    });
}
bool Overlaps(std::uintptr_t start,size_t size,const vm_startup::AddressEdit& edit) {
    Require(!edit.original.empty() && edit.original.size()==edit.replacement.size()
        && edit.address<=UINTPTR_MAX-edit.original.size(),"Invalid existing integrity exclusion edit.");
    return start<edit.address+edit.original.size() && edit.address<start+size;
}
void VerifyMemory(HANDLE process,std::uintptr_t imageBase,std::uintptr_t address,size_t size) {
    const auto end=address+size;
    while(address<end) {
        MEMORY_BASIC_INFORMATION memory{};
        Require(VirtualQueryEx(process,reinterpret_cast<void*>(address),&memory,sizeof(memory))==sizeof(memory),"Cannot query integrity memory.");
        Require(memory.State==MEM_COMMIT && memory.Type==MEM_IMAGE && memory.Protect==PAGE_EXECUTE_READWRITE
            && reinterpret_cast<std::uintptr_t>(memory.AllocationBase)==imageBase,"Integrity image memory or protection differs.");
        const auto start=reinterpret_cast<std::uintptr_t>(memory.BaseAddress);
        Require(memory.RegionSize>0 && start<=address && start<=UINTPTR_MAX-memory.RegionSize
            && address<start+memory.RegionSize,"Integrity memory region is invalid.");
        address=std::min(end,start+memory.RegionSize);
    }
}
void ValidateProfile() {
    Require(kRecords.size()==kPatternCount && kRegions.size()==2,"Integrity profile inventory differs.");
    std::array<std::uint32_t,4> counts{};
    for(size_t index=0;index<kRecords.size();++index) {
        const auto& record=kRecords[index];
        const auto original=Original(record.family);
        Require(record.guardSize>=original.size() && record.guardSize<=100
            && record.rva<=kImageSize-record.guardSize && InsideRegion(record.rva,record.guardSize),"Integrity guard exceeds fixed code regions.");
        Require(record.liveFlags==(record.family==Family::Compare ? Flags::ZeroCarry : Flags::Zero),"Integrity endpoint flags are unsupported.");
        Require(record.imageAddressCount<=record.imageAddresses.size(),"Integrity normalization inventory differs.");
        for(size_t field=0;field<record.imageAddressCount;++field) {
            const auto& pointer=record.imageAddresses[field];
            Require(pointer.offset>=original.size() && pointer.offset<=record.guardSize-8
                && pointer.targetRva<kImageSize,"Integrity normalized address exceeds its guard.");
            if(field)Require(record.imageAddresses[field-1].offset+8<=pointer.offset,"Integrity normalized addresses overlap.");
        }
        if(index)Require(kRecords[index-1].rva+Original(kRecords[index-1].family).size()<=record.rva,"Integrity records overlap or are not ordered.");
        ++counts[static_cast<size_t>(record.family)];
    }
    Require(counts==kFamilyCounts,"Integrity evaluator families differ.");
}
std::vector<unsigned char> VerifyGuard(HANDLE process,std::uintptr_t imageBase,const Guard& guard,
    std::span<const vm_startup::AddressEdit> existingEdits) {
    Require(guard.size && guard.size<=125 && guard.rva<=kImageSize-guard.size
        && InsideRegion(guard.rva,guard.size),"Integrity context exceeds fixed code regions.");
    Require(guard.imageAddressCount<=guard.imageAddresses.size(),"Integrity context normalization differs.");
    const auto address=imageBase+guard.rva;
    VerifyMemory(process,imageBase,address,guard.size);
    for(const auto& edit:existingEdits)Require(!Overlaps(address,guard.size,edit),"Integrity guard overlaps an engine edit.");
    auto bytes=vm_startup::ReadStopped(process,address,guard.size);
    for(size_t field=0;field<guard.imageAddressCount;++field) {
        const auto& pointer=guard.imageAddresses[field];
        Require(guard.size>=8 && pointer.offset<=guard.size-8 && pointer.targetRva<kImageSize,"Integrity context address exceeds its guard.");
        if(field)Require(guard.imageAddresses[field-1].offset+8<=pointer.offset,"Integrity context addresses overlap.");
        std::uintptr_t actual{};std::memcpy(&actual,bytes.data()+pointer.offset,sizeof(actual));
        Require(actual==imageBase+pointer.targetRva,"Integrity transport address differs.");
        std::fill_n(bytes.begin()+pointer.offset,8,static_cast<unsigned char>(0));
    }
    Require(Digest(bytes)==guard.digest,"Integrity evaluator or source context differs.");
    return bytes;
}
}
std::span<const unsigned char> Original(Family family) {
    switch(family) {
    case Family::Xor:case Family::InputTransform:return xorOriginal;
    case Family::NegAdd:return negOriginal;
    case Family::Compare:return cmpOriginal;
    }
    throw std::runtime_error("Unknown integrity evaluator family.");
}
std::span<const unsigned char> Replacement(Family family) {
    switch(family) {
    case Family::Xor:return xorReplacement;
    case Family::NegAdd:return negReplacement;
    case Family::Compare:return cmpReplacement;
    case Family::InputTransform:throw std::runtime_error("Checksum input transforms must remain original.");
    }
    throw std::runtime_error("Unknown integrity evaluator family.");
}
std::vector<vm_startup::AddressEdit> PrepareStopped(HANDLE process,std::uintptr_t imageBase,
    const std::array<unsigned char,32>& verifiedExecutableDigest,
    std::span<const vm_startup::AddressEdit> existingEdits) {
#ifndef BO3_CODE_INTEGRITY_OWNED_TEST
    Require(kProductionInputAttributionVerified,"Comparison inputs are not attributed exclusively to game-code checks. Production preparation refused.");
#endif
    ValidateProfile();
    Require(verifiedExecutableDigest==kExecutableDigest,"Integrity executable identity differs.");
    Require(imageBase && imageBase<=UINTPTR_MAX-kImageSize,"Integrity image address overflows.");
    const auto dosBytes=vm_startup::ReadStopped(process,imageBase,sizeof(IMAGE_DOS_HEADER));
    IMAGE_DOS_HEADER dos{};std::memcpy(&dos,dosBytes.data(),sizeof(dos));
    Require(dos.e_magic==IMAGE_DOS_SIGNATURE && dos.e_lfanew>=static_cast<LONG>(sizeof(dos))
        && static_cast<std::uint32_t>(dos.e_lfanew)<=kImageSize-sizeof(IMAGE_NT_HEADERS64),"Integrity DOS header differs.");
    const auto peBytes=vm_startup::ReadStopped(process,imageBase+dos.e_lfanew,sizeof(IMAGE_NT_HEADERS64));
    IMAGE_NT_HEADERS64 pe{};std::memcpy(&pe,peBytes.data(),sizeof(pe));
    Require(pe.Signature==IMAGE_NT_SIGNATURE && pe.FileHeader.Machine==IMAGE_FILE_MACHINE_AMD64
        && pe.FileHeader.TimeDateStamp==kTimestamp && pe.OptionalHeader.Magic==IMAGE_NT_OPTIONAL_HDR64_MAGIC
        && pe.OptionalHeader.SizeOfImage==kImageSize,"Integrity PE identity differs.");
    std::vector<vm_startup::AddressEdit> result;
    result.reserve(kEditCount);
    Require(!kContextGuards.empty(),"Integrity source and flag-path contexts are missing.");
    for(const auto& guard:kContextGuards)VerifyGuard(process,imageBase,guard,existingEdits);
    for(const auto& record:kRecords) {
        const auto address=imageBase+record.rva;
        const auto guard=VerifyGuard(process,imageBase,{record.rva,record.guardSize,record.guardDigest,
            record.imageAddresses,record.imageAddressCount},existingEdits);
        const auto original=Original(record.family);
        Require(std::equal(original.begin(),original.end(),guard.begin()),"Integrity original instruction differs.");
        if(record.family==Family::InputTransform)continue;
        const auto replacement=Replacement(record.family);
        const size_t offset=record.family==Family::Compare ? 6 : 3;
        result.push_back({address+offset,{original.begin()+offset,original.end()},
            {replacement.begin()+offset,replacement.end()}});
    }
    Require(result.size()==kEditCount,"Integrity endpoint plan is incomplete.");
    return result;
}
}
