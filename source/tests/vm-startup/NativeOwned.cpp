#include "NativeOwned.h"
#include "../../patches/vm_pool/NativeStateBridge.h"
#include "../../patches/vm_startup/StateErrors.h"
#include "../../launch/preentry/Identity.h"
#include <array>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <vector>

extern "C" { unsigned char OwnedReaderHome=0,OwnedWriterHome=0,OwnedInsertHome=0,OwnedErrorHome=0; }
namespace {
using namespace bo3::vm;
NativeShared* trace;
std::byte* image;
std::vector<Slot> slots;
std::array<std::uint32_t,65536> buckets;
std::array<std::byte,192> tables;
std::vector<std::byte> clients,data;
std::size_t cursor;
bool failDecode;
ErrorFunction laterOriginal;
constexpr DWORD ownedErrorExit=0xe042564d;
template<class T> T& Field(std::size_t offset) { return *reinterpret_cast<T*>(image+offset); }
template<class T> T Entry(std::uint32_t rva) { return reinterpret_cast<T>(image+rva); }
void Read(void*,std::uint32_t size,void* output) {
    Require(cursor+size<=data.size(),"Owned native stream is truncated.");
    std::memcpy(output,data.data()+cursor,size); cursor+=size;
}
void Write(void*,std::uint32_t value) {
    const auto* bytes=reinterpret_cast<std::byte*>(&value); data.insert(data.end(),bytes,bytes+4);
}
void ReadSlot(std::uint32_t instance,void* file,std::uint32_t id) {
    if(failDecode && id==2) Entry<ErrorFunction>(0x20ec0b0)("owned-decode",147,2,"owned slot decode %d",17);
    Read(file,64,&slots[id]);
    if(slots[id].type!=27) Entry<InsertFunction>(0x12d9420)(instance,id,slots[id].key,slots[id].parent);
}
void WriteSlot(std::uint32_t,void*,std::uint32_t id) {
    const auto* bytes=reinterpret_cast<std::byte*>(&slots[id]); data.insert(data.end(),bytes,bytes+64);
}
std::uint32_t associations;
void ReadAssociations(std::uint32_t,void* file) { Read(file,4,&associations); }
void WriteAssociations(std::uint32_t,void* file) { Write(file,associations); }
std::uint32_t GetMode() { return 0; }
void Commit(std::uint32_t rva) {
    Require(VirtualAlloc(image+(rva&~4095u),4096,MEM_COMMIT,PAGE_READWRITE)!=nullptr,"Owned native image commit failed.");
}
void Absolute(std::byte* code,std::uintptr_t target) {
    constexpr unsigned char jump[]{0xff,0x25,0,0,0,0};
    std::memcpy(code,jump,6); std::memcpy(code+6,&target,8);
}
template<class T> void Publish(std::uint32_t rva,T continuation,std::span<const unsigned char> prefix={}) {
    Commit(rva);
    if(!prefix.empty()) std::memcpy(image+rva,prefix.data(),prefix.size());
    Absolute(image+rva+prefix.size(),reinterpret_cast<std::uintptr_t>(continuation));
}
void Append(const void* bytes,std::size_t size) {
    const auto* start=static_cast<const std::byte*>(bytes); data.insert(data.end(),start,start+size);
}
void LegacyStream() {
    data.clear(); cursor=0;
    std::uint32_t head=2; Append(&head,4);
    for(std::uint32_t id=1;id<StockTotal;++id) {
        Slot slot{};
        if(id==1) { slot.type=21; slot.flags=1; slot.key=StockTotal+0x20000; slot.parent=7; }
        else { slot.type=27; slot.next=id+1<StockTotal ? id+1 : 0; }
        Append(&slot,sizeof(slot));
    }
    for(unsigned index=0;index<31;++index) { const std::uint32_t value=100+index; Append(&value,4); }
}
bool Import(bool shouldExit) {
    bool exited=false;
    __try { Entry<WholeFunction>(0x12d52f0)(0,trace); }
    __except(GetExceptionCode()==ownedErrorExit ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) {
        exited=true; ++trace->nonLocalExits;
    }
    return exited==shouldExit;
}
bool Export(bool shouldExit) {
    bool exited=false;
    __try { Entry<WholeFunction>(0x12d5f20)(0,trace); }
    __except(GetExceptionCode()==ownedErrorExit ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) {
        exited=true; ++trace->nonLocalExits;
    }
    return exited==shouldExit;
}
void LaterError(const char* file,int line,int code,const char* format,...) {
    ++trace->laterCalls;
    char text[1024]{}; va_list args; va_start(args,format);
    std::vsnprintf(text,sizeof(text),format,args); va_end(args);
    laterOriginal(file,line,code,"%s",text);
}
void InstallLater() {
    const auto rva=0x20ec0b0u;
    DWORD old=0,discarded=0;
    Require(VirtualProtect(image+(rva&~4095u),4096,PAGE_EXECUTE_READWRITE,&old)!=FALSE,"Cannot install owned later error detour.");
    auto* saved=image+rva+128;
    const auto prior=static_cast<std::int64_t>(trace->relay+48)-static_cast<std::int64_t>(reinterpret_cast<std::uintptr_t>(saved)+5);
    Require(prior>=INT32_MIN && prior<=INT32_MAX,"Owned saved detour exceeds relay reach.");
    saved[0]=std::byte{0xe9}; const auto relative=static_cast<std::int32_t>(prior); std::memcpy(saved+1,&relative,4);
    laterOriginal=reinterpret_cast<ErrorFunction>(saved);
    Absolute(image+rva+256,reinterpret_cast<std::uintptr_t>(LaterError));
    image[rva]=std::byte{0xe9}; const std::int32_t distance=251; std::memcpy(image+rva+1,&distance,4);
    Require(VirtualProtect(image+(rva&~4095u),4096,old,&discarded)!=FALSE
        && FlushInstructionCache(GetCurrentProcess(),image+(rva&~4095u),4096)!=FALSE,"Cannot publish owned later error chain.");
}
enum class Frame { Leaf,Insert,Prelude };
bool Unwind(HMODULE helper,const char* name,Frame kind) {
    const auto pc=reinterpret_cast<DWORD64>(GetProcAddress(helper,name))+(kind==Frame::Leaf ? 5 : 0);
    DWORD64 base=0; auto* function=RtlLookupFunctionEntry(pc,&base,nullptr);
    Require(function!=nullptr,"Static helper unwind metadata is missing.");
    alignas(16) std::array<DWORD64,32> stack{};
    constexpr DWORD64 sentinel=0x123456789abcdef0ull,savedRbx=0x777788889999aaaauLL;
    CONTEXT context{}; context.Rip=pc; context.Rsp=reinterpret_cast<DWORD64>(stack.data()); context.Rbx=0x42;
    if(kind==Frame::Insert) { stack[0]=savedRbx; stack[1]=sentinel; }
    else if(kind==Frame::Prelude) stack[9]=sentinel;
    else stack[0]=sentinel;
    const auto start=context.Rsp;
    void* handler=nullptr; DWORD64 frame=0;
    RtlVirtualUnwind(UNW_FLAG_NHANDLER,base,pc,function,&context,&handler,&frame,nullptr);
    const DWORD64 size=kind==Frame::Insert ? 16 : kind==Frame::Prelude ? 0x50 : 8;
    return context.Rip==sentinel && context.Rsp==start+size
        && context.Rbx==(kind==Frame::Insert ? savedRbx : 0x42);
}
}
extern "C" void NativeClientRead(std::uint32_t instance,void* file) {
    Require(instance==1 && file==trace && OwnedReaderHome==1,"Original reader thunk ABI differs."); ++trace->clientReads;
}
extern "C" void NativeClientWrite(std::uint32_t instance,void* file) {
    Require(instance==1 && file==trace && OwnedWriterHome==1,"Original writer thunk ABI differs."); ++trace->clientWrites;
}
extern "C" void NativeInsert(std::uint32_t instance,std::uint32_t id,std::uint64_t key,std::uint32_t parent) {
    Require(instance==0 && id==1 && slots[id].key==key && parent==7 && OwnedInsertHome==1,"Original insertion thunk ABI differs.");
    ++trace->inserts;
}
extern "C" void NativeError(const char* file,int line,int code,const char* format,...) {
    Require(OwnedErrorHome==1 && code==2 && line>0,"Original error thunk ABI differs.");
    ++trace->errorCalls; trace->stateErrorCode=code;
    va_list args; va_start(args,format);
    if(trace->scenario==NativeScenario::DecodeError)
        Require(std::strcmp(file,"owned-decode")==0 && va_arg(args,int)==17,"Decode error stack argument differs.");
    else if(trace->scenario==NativeScenario::LaterError) {
        const auto* text=va_arg(args,const char*);
        Require(std::strcmp(format,"%s")==0 && std::strstr(text,"VM state read rejected (error 4)")!=nullptr,"Later error chain lost its formatted argument.");
    } else Require(std::strcmp(file,"bo3-vm-state")==0 && va_arg(args,int)==4,"State error argument differs.");
    va_end(args);
    RaiseException(ownedErrorExit,0,0,nullptr);
}
void SetupNativeImage(NativeShared* state) {
    trace=state;
    image=static_cast<std::byte*>(VirtualAlloc(nullptr,NativeImageSize,MEM_RESERVE,PAGE_NOACCESS));
    Require(image!=nullptr,"Cannot reserve owned native image.");
    trace->imageBase=reinterpret_cast<std::uintptr_t>(image); trace->imageSize=NativeImageSize;
    for(auto rva:{0x5124500u,0x3267228u,0xa1b0730u,0x10000u}) Commit(rva);
    Field<DWORD>(0x10000)=130000; Field<DWORD>(0x10004)=130000;
    Publish(0x12d52f0,OwnedReaderContinuation,NativeEntries[0].original);
    Publish(0x12d5f20,OwnedWriterContinuation,NativeEntries[1].original);
    Publish(0x12d9420,OwnedInsertContinuation,NativeEntries[2].original);
    Publish(0x20ec0b0,OwnedErrorContinuation,NativeEntries[3].original);
    Publish(0x22778b0,Read); Publish(0xd2870,Write); Publish(0x12d5590,ReadSlot); Publish(0x12d64c0,WriteSlot);
    Publish(0x1611c0,ReadAssociations); Publish(0x161310,WriteAssociations);
    Publish(0x20eac70,GetMode);
    if(trace->scenario==NativeScenario::EntryMismatch) image[0x12d52f0]=std::byte{0x49};
    for(auto rva:{0x12d5000u,0x12d6000u,0x12d9000u,0x20ec000u,0x20ea000u,0x2277000u,0xd2000u,0x161000u}) {
        DWORD old=0; Require(VirtualProtect(image+rva,4096,PAGE_EXECUTE_READ,&old)!=FALSE,"Cannot protect owned native code.");
    }
    Require(FlushInstructionCache(GetCurrentProcess(),nullptr,0)!=FALSE,"Cannot flush owned native continuations.");
}
void RunNativeExports() {
    using namespace bo3::vm;
    Require(trace->ready==1 && trace->readyBeforeCalls==1,"Native composition did not precede execution.");
    Require(Field<DWORD>(0x10000)==trace->loader.expectedTotal && Field<DWORD>(0x10004)==trace->loader.expectedTotal,"Native count transaction is incomplete.");
    slots.assign(trace->loader.expectedTotal,{}); clients.assign(18*0x171f0,{});
    Field<Slot*>(0x5124580)=slots.data(); Field<std::uint32_t*>(0x5124500)=buckets.data();
    Field<std::byte*>(0x3267228)=tables.data(); Field<std::byte*>(0xa1b0730)=clients.data();
    Entry<WholeFunction>(0x12d52f0)(1,trace); Entry<WholeFunction>(0x12d5f20)(1,trace);
    const auto helper=reinterpret_cast<HMODULE>(trace->loader.helperBase);
    trace->insertUnwind=Unwind(helper,"NativeOriginalInsertBody",Frame::Insert);
    trace->errorUnwind=Unwind(helper,"VmErrorPreludeBody",Frame::Prelude);
    for(const auto* name:{"NativeOriginalReader","NativeOriginalWriter","NativeOriginalError"})
        trace->leafUnwinds+=Unwind(helper,name,Frame::Leaf);
    Require(trace->insertUnwind && trace->errorUnwind && trace->leafUnwinds==3,"Static helper frame unwind differs.");
    if(trace->scenario==NativeScenario::LaterError) InstallLater();
    LegacyStream();
    if(trace->scenario==NativeScenario::DecodeError) {
        failDecode=true; Require(Import(true),"Native decode did not take its owned non-local exit.");
        failDecode=false; cursor=0;
    } else if(trace->scenario==NativeScenario::StateError || trace->scenario==NativeScenario::LaterError) {
        const std::uint32_t invalid=130000; std::memcpy(data.data(),&invalid,4);
        Require(Import(true),"Returned native StateError did not drop through the error chain.");
        LegacyStream();
    }
    Require(Import(false),"Real helper import failed after the error path."); ++trace->serverReads;
    Require(slots[1].key==trace->loader.expectedTotal+0x20000 && slots.back().type==27
        && slots.back().next==0,"Real helper legacy import did not translate/extend the server pool.");
    // Probe after import: a stale active context would translate this old namespace key.
    slots[1].key=130000+0x20000;
    Entry<InsertFunction>(0x12d9420)(0,1,slots[1].key,7);
    Require(slots[1].key==130000+0x20000,"Real helper import TLS remained active.");
    data.clear(); Require(Export(false),"Real helper expanded export failed."); ++trace->serverWrites;
    trace->encodedBytes=data.size(); std::uint64_t hash=14695981039346656037ull;
    for(const auto byte:data) hash=(hash^static_cast<unsigned char>(byte))*1099511628211ull;
    trace->encodedHash=hash;
    const auto expected=data; cursor=0; slots.assign(trace->loader.expectedTotal,{}); Field<Slot*>(0x5124580)=slots.data();
    Require(Import(false),"Real helper expanded import failed."); ++trace->serverReads;
    data.clear(); Require(Export(false),"Real helper second expanded export failed."); ++trace->serverWrites;
    Require(data==expected,"Real helper expanded roundtrip bytes differ.");
    if(trace->scenario==NativeScenario::StateError) {
        slots[0].next=trace->loader.expectedTotal;
        Require(Export(true),"Returned writer StateError did not drop through the original thunk.");
    }
    trace->passed=1;
}
