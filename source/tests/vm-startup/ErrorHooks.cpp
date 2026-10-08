#include "ErrorHooks.h"
#include "../../launch/preentry/Identity.h"
#include <cstring>

namespace {
void Absolute(unsigned char* code,std::uintptr_t destination) {
    code[0]=0xff; code[1]=0x25;
    std::memset(code+2,0,4);
    std::memcpy(code+6,&destination,8);
}
void Relative(unsigned char* code,unsigned char* destination) {
    code[0]=0xe9;
    const auto offset=static_cast<std::int32_t>(destination-code-5);
    std::memcpy(code+1,&offset,4);
}
}
ErrorHooks::ErrorHooks() {
    page_=static_cast<unsigned char*>(VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE));
    Require(page_!=nullptr,"Cannot allocate the owned error entry page.");
    const unsigned char original[]{0x4c,0x89,0x4c,0x24,0x20};
    std::memcpy(page_,original,5);
    // Observe the recovered R9 home slot before the owned body homes registers.
    page_[5]=0x48; page_[6]=0xb8;
    const auto home=reinterpret_cast<std::uintptr_t>(&errorTrace.observedHome);
    std::memcpy(page_+7,&home,8);
    const unsigned char observe[]{0x4c,0x8b,0x54,0x24,0x20,0x4c,0x89,0x10};
    std::memcpy(page_+15,observe,sizeof(observe));
    page_[23]=0x48; page_[24]=0xb8;
    const auto counter=reinterpret_cast<std::uintptr_t>(&errorTrace.homeStores);
    std::memcpy(page_+25,&counter,8);
    page_[33]=0xff; page_[34]=0x00;
    Absolute(page_+35,reinterpret_cast<std::uintptr_t>(OwnedOriginalError));
    std::memcpy(page_+128,original,5);
    Absolute(page_+133,reinterpret_cast<std::uintptr_t>(page_+5));
    Absolute(page_+256,reinterpret_cast<std::uintptr_t>(bo3::vm::VmErrorPrelude));
    Relative(page_+384,page_+256);
    Absolute(page_+512,reinterpret_cast<std::uintptr_t>(OwnedLaterError));
    Relative(page_,page_+256);
    DWORD previous=0;
    Require(VirtualProtect(page_,4096,PAGE_EXECUTE_READ,&previous)!=FALSE
        && FlushInstructionCache(GetCurrentProcess(),page_,4096)!=FALSE,"Cannot publish the owned error entry page.");
}
ErrorHooks::~ErrorHooks() { VirtualFree(page_,0,MEM_RELEASE); }
void ErrorHooks::InstallLater() {
    DWORD previous=0;
    Require(VirtualProtect(page_,4096,PAGE_EXECUTE_READWRITE,&previous)!=FALSE,"Cannot install the owned later detour.");
    Relative(page_,page_+512);
    DWORD discarded=0;
    Require(VirtualProtect(page_,4096,previous,&discarded)!=FALSE
        && FlushInstructionCache(GetCurrentProcess(),page_,4096)!=FALSE,"Cannot restore the owned entry protection.");
}
bo3::vm::ErrorFunction ErrorHooks::Entry() const { return reinterpret_cast<bo3::vm::ErrorFunction>(page_); }
bo3::vm::ErrorFunction ErrorHooks::Original() const { return reinterpret_cast<bo3::vm::ErrorFunction>(page_+128); }
bo3::vm::ErrorFunction ErrorHooks::LaterOriginal() const { return reinterpret_cast<bo3::vm::ErrorFunction>(page_+384); }
