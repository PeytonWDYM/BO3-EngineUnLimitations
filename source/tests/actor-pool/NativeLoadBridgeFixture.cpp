// Authored native callbacks exercise complete owned allocations and real Windows thread IDs.
#include "../../patches/actor_pool/NativeLoadBridge.h"
#include <algorithm>
#include <array>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <vector>
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

namespace {
using namespace bo3::actors;
constexpr std::uint32_t LegacyHistory=33360,History=260080;
constexpr std::uintptr_t Image=0x140000000;
void Require(bool value,const char* reason) {if(!value)throw std::runtime_error(reason);}
struct Refusal {};
struct NativeFailure {};
unsigned int Calls[4]{},Errors{},WholeCalls{},PreparedFiles{},NullWholeCalls{};
std::uintptr_t WholeFlags{};
bool Overflow{},ThrowNative{},ThrowWhole{},WholeReturnsFalse{};
ReadCounts Counts=LegacyCounts;
std::vector<std::byte> Source;
std::uint32_t Cursor{};
struct Guarded {
    std::vector<std::byte> bytes;
    explicit Guarded(std::size_t size):bytes(size+128,std::byte{0xA5}){}
    std::byte* data(){return bytes.data()+64;}
    std::size_t size() const{return bytes.size()-128;}
    void fill(std::byte value){std::fill(bytes.begin()+64,bytes.end()-64,value);}
    void check() const {
        Require(std::all_of(bytes.begin(),bytes.begin()+64,[](auto b){return b==std::byte{0xA5};}) &&
            std::all_of(bytes.end()-64,bytes.end(),[](auto b){return b==std::byte{0xA5};}),"An allocation canary changed.");
    }
};
Guarded Actors(500*0x2110),Sentients(540*0x3088),Knowledge(540*540*0x48),Words(540*540*2),HistoryBuffer(History),Scratch(History),Secondary(500*0xB00);
void AuthoredActor(void* file) {
    Require(ReaderAllowed(file,GetCurrentThreadId()),"An actor callback escaped its scope.");++Calls[0];
    if(ThrowNative)throw NativeFailure{};
    std::memset(Actors.data(),0x31,static_cast<std::size_t>(Counts.actorBytes));
}
void AuthoredSentient(void* file) {
    Require(ReaderAllowed(file,GetCurrentThreadId()),"A sentient callback escaped its scope.");++Calls[1];
    std::memset(Sentients.data(),0x42,static_cast<std::size_t>(Counts.sentientBytes));
    // Native load resets tables after it reads the records. Dirty these tables to test the final clear.
    Knowledge.fill(std::byte{0xB7});Words.fill(std::byte{0xC8});
}
void AuthoredSecondary(void* file) {
    Require(ReaderAllowed(file,GetCurrentThreadId()),"A secondary callback escaped its scope.");++Calls[2];
    Require(Counts.secondaryRecords==64 || Counts.secondaryRecords==500,"A secondary callback got an invalid count.");
    std::memset(Secondary.data(),0x53,Counts.secondaryRecords*0xB00);
}
void AuthoredRead(void* file,std::uint32_t bytes,void* destination) {
    Require(ReaderAllowed(file,GetCurrentThreadId()),"A stream callback escaped its scope.");++Calls[3];
    Require(destination==Scratch.data(),"A stream callback bypassed the complete scratch allocation.");
    auto& state=*static_cast<bo3::migration::WrittenState*>(file);
    if(Overflow || Cursor+bytes>Source.size()) {state.overflow=1;return;}
    std::memcpy(destination,Source.data()+Cursor,bytes);Cursor+=bytes;
}
void AuthoredError(const char* source,int line,int code,const char* message,...) {
    Require(std::strcmp(source,"actor_pool")==0 && line==0 && code==2 && *message,"The error ABI differs.");++Errors;throw Refusal{};
}
template<class Action> void Refuse(Action action) {
    const auto before=std::array{Calls[0],Calls[1],Calls[2],Calls[3]};
    bool refused=false;try {action();}catch(const Refusal&){refused=true;}
    Require(refused && before==std::array{Calls[0],Calls[1],Calls[2],Calls[3]},"An invalid call reached native code.");
}
void Start(bo3::migration::WrittenState& file,std::uint32_t version) {
    const RootHeader header{1024,version,0,0x4864,0,100};
    Require(BeginLoad(header,&file,GetCurrentThreadId(),32*1024*1024),"The fixture root scope failed.");
}
void CheckBuffers() {Actors.check();Sentients.check();Knowledge.check();Words.check();HistoryBuffer.check();Scratch.check();Secondary.check();}
void CheckZero(const std::byte* data,std::size_t bytes) {
    Require(std::all_of(data,data+bytes,[](auto b){return b==std::byte{};}),"Unused storage contains stale bytes.");
}
void CheckActor(std::uint32_t index) {
    std::array<std::byte,0x2110> expected{};
    const auto pointer=Image+0x2F1BB88;std::memcpy(expected.data()+0x8A0,&pointer,8);
    for(auto offset:{0x8B0,0x8B4,0x8B8,0x8C0,0x8C4,0x8C8}) {
        const std::uint32_t value=offset<0x8C0?0x7E967699u:0xFE967699u;
        std::memcpy(expected.data()+offset,&value,4);
    }
    Require(std::memcmp(Actors.data()+index*0x2110,expected.data(),expected.size())==0,"An unused actor differs from its constructor defaults.");
}
void AuthoredEarlyPreparation(bo3::migration::WrittenState& file,std::uint32_t version) {
    Start(file,version);++PreparedFiles;
    // The native preparation returns the file before the later whole-load entry uses it.
}
bool AuthoredWhole(void* file) {
    ++WholeCalls;
    if(file==nullptr) {
        Require((WholeFlags&0x841)==0x40,"The null whole reentry lost TEST RCX,RCX branch flags.");
        ++NullWholeCalls;return false;
    }
    Require(ReaderAllowed(file,GetCurrentThreadId()),"The later whole callback lost its prepared scope.");
    Require((WholeFlags&0x841)==0,"The whole reentry lost TEST RCX,RCX branch flags.");
    if(Counts.secondaryRecords==64)CheckZero(Secondary.data()+64*0xB00,(500-64)*0xB00);
    if(ThrowWhole)throw NativeFailure{};
    ReadActorState(file);ReadSentientState(file);
    // The tagged native loop writes its records directly. It never calls ReadSecondaryState.
    std::memset(Secondary.data(),0x64,Counts.secondaryRecords*0xB00);
    if(Counts.secondaryRecords==64)CheckZero(Secondary.data()+64*0xB00,(500-64)*0xB00);
    return !WholeReturnsFalse;
}
struct WholeContinuation {
    void* address;
    WholeContinuation():address(VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE)) {
        Require(address!=nullptr,"Cannot allocate the authored whole continuation.");
        // Capture TEST flags, undo the native frame, then tail-call the authored C++ callback.
        std::array<std::byte,33> code{std::byte{0x9C},std::byte{0x58},std::byte{0x49},std::byte{0xBB}};
        const auto flags=reinterpret_cast<std::uintptr_t>(&WholeFlags),callback=reinterpret_cast<std::uintptr_t>(AuthoredWhole);
        std::memcpy(code.data()+4,&flags,8);
        constexpr unsigned char body[]{0x49,0x89,0x03,0x48,0x8D,0x64,0x24,0x28,0x49,0xBB};
        std::memcpy(code.data()+12,body,sizeof(body));std::memcpy(code.data()+22,&callback,8);
        code[30]=std::byte{0x41};code[31]=std::byte{0xFF};code[32]=std::byte{0xE3};
        std::memcpy(address,code.data(),code.size());DWORD previous{};
        Require(VirtualProtect(address,4096,PAGE_EXECUTE_READ,&previous)!=0,"Cannot protect the authored whole continuation.");
        Require(FlushInstructionCache(GetCurrentProcess(),address,code.size())!=0,"Cannot flush the authored whole continuation.");
    }
    ~WholeContinuation(){VirtualFree(address,0,MEM_RELEASE);}
};
void CheckWholeUnwind() {
    DWORD64 image{};
    const auto start=reinterpret_cast<DWORD64>(ActorLoadReentry);
    const auto* entry=RtlLookupFunctionEntry(start,&image,nullptr);
    Require(entry!=nullptr,"The whole reentry has no registered native frame.");
    constexpr std::array<unsigned char,8> expected{1,4,1,0,4,0x42,0,0};
    Require(std::memcmp(reinterpret_cast<const void*>(image+entry->UnwindData),expected.data(),expected.size())==0,
        "The whole reentry unwind record differs from its native allocation.");
    alignas(16) std::array<DWORD64,8> stack{};
    const auto caller=reinterpret_cast<DWORD64>(AuthoredWhole);stack[5]=caller;
    for(const DWORD64 phase:{4ull,7ull,14ull}) {
        CONTEXT context{};context.Rip=start+phase;context.Rsp=reinterpret_cast<DWORD64>(stack.data());
        void* handler{};DWORD64 establisher{};
        RtlVirtualUnwind(UNW_FLAG_NHANDLER,image,context.Rip,const_cast<PRUNTIME_FUNCTION>(entry),&context,&handler,&establisher,nullptr);
        Require(context.Rip==caller && context.Rsp==reinterpret_cast<DWORD64>(stack.data()+6),
            "Windows lost the active whole reentry frame.");
    }
}
}
int main(int argc,char** argv) {
    try {
        Require(argc==2,"Supply a private receipt path.");
        CheckWholeUnwind();
        WholeContinuation wholeContinuation;
        Bo3ActorLoadBindings={&Counts};
        Bo3ActorReadBranches={reinterpret_cast<std::uintptr_t>(AuthoredActor),reinterpret_cast<std::uintptr_t>(AuthoredSentient),
            reinterpret_cast<std::uintptr_t>(AuthoredSecondary),reinterpret_cast<std::uintptr_t>(wholeContinuation.address)};
        Bo3ActorNativeBindings={ActorReadReentry,SentientReadReentry,SecondaryReadReentry,AuthoredRead,AuthoredError,Image,
            Actors.data(),Sentients.data(),Knowledge.data(),Words.data(),HistoryBuffer.data(),Scratch.data(),Secondary.data(),ActorLoadReentry};
        bo3::migration::WrittenState file{},other{};
        auto* nativeHistory=reinterpret_cast<void*>(Image+0xA1C3484);
        unsigned int Roots{};
        for(const auto version:std::array{3u,VmOnlyVersion,Actor500Version}) {
            const bool expanded=version==Actor500Version;
            Actors.fill(std::byte{0xE1});Sentients.fill(std::byte{0xE2});HistoryBuffer.fill(std::byte{0xE3});Scratch.fill(std::byte{0xE4});
            Secondary.fill(std::byte{0xE5});
            Start(file,version);++Roots;
            ReadActorState(&file);ReadSentientState(&file);ReadSecondaryState(&file);
            const auto actorCount=expanded?500u:64u,sentientCount=expanded?540u:104u;
            Require(std::all_of(Actors.data(),Actors.data()+actorCount*0x2110,[](auto b){return b==std::byte{0x31};}),"The imported actor prefix differs.");
            for(auto index=actorCount;index<500;++index)CheckActor(index);
            Require(std::all_of(Sentients.data(),Sentients.data()+sentientCount*0x3088,[](auto b){return b==std::byte{0x42};}),"The imported sentient prefix differs.");
            CheckZero(Sentients.data()+sentientCount*0x3088,(540-sentientCount)*0x3088);
            Require(std::all_of(Secondary.data(),Secondary.data()+actorCount*0xB00,[](auto b){return b==std::byte{0x53};}),"The imported secondary prefix differs.");
            CheckZero(Secondary.data()+actorCount*0xB00,(500-actorCount)*0xB00);
            CheckZero(Knowledge.data(),Knowledge.size());CheckZero(Words.data(),Words.size());
            const auto length=expanded?History:LegacyHistory;
            Source.resize(length+4);for(std::size_t index=0;index<length;++index)Source[index]=std::byte((index*37+11)%251);
            const std::uint32_t marker=0xA16B32F9;std::memcpy(Source.data()+length,&marker,4);Cursor=0;
            ReadActorHistory(&file,LegacyHistory,nativeHistory);
            Require(Cursor==length,"The history reader consumed the following section.");
            std::uint32_t actualMarker{};std::memcpy(&actualMarker,Source.data()+Cursor,4);Require(actualMarker==marker,"The following marker changed.");
            std::vector<std::byte> expected(History);
            if(expanded)std::copy_n(Source.begin(),History,expected.begin());
            else {
                struct Member {std::size_t oldOffset,newOffset,size;};
                constexpr std::array<Member,5> members{{{0,0,0x300},{0x300,6000,0x300},{0x600,12000,64},{0x640,12500,64},{0x680,13000,4}}};
                for(std::size_t row=0;row<20;++row)for(auto member:members)
                    std::memcpy(expected.data()+row*13004+member.newOffset,Source.data()+row*0x684+member.oldOffset,member.size);
            }
            Require(std::memcmp(expected.data(),HistoryBuffer.data(),History)==0,"The complete history import differs.");
            CheckBuffers();Require(EndLoad(&file,GetCurrentThreadId()),"The fixture scope failed to close.");
        }
        for(auto reader:{ReadActorState,ReadSentientState,ReadSecondaryState}) {
            Refuse([&]{reader(&file);});Start(file,Actor500Version);
            Refuse([&]{reader(&other);});Require(!ReaderAllowed(&file,GetCurrentThreadId()),"Wrong-file error retained its context.");
            Start(file,Actor500Version);bool foreignRefused=false;
            std::thread foreign([&]{try {reader(&file);}catch(const Refusal&){foreignRefused=true;}});foreign.join();
            Require(foreignRefused && ReaderAllowed(&file,GetCurrentThreadId()),"A foreign-thread error cleared its owner.");
            Require(EndLoad(&file,GetCurrentThreadId()),"The foreign-thread test scope failed to close.");
        }
        Refuse([&]{ReadActorHistory(&file,LegacyHistory,nativeHistory);});
        Start(file,Actor500Version);Refuse([&]{ReadActorHistory(&other,LegacyHistory,nativeHistory);});
        Start(file,Actor500Version);bool foreignHistoryRefused=false;
        std::thread foreignHistory([&]{try {ReadActorHistory(&file,LegacyHistory,nativeHistory);}catch(const Refusal&){foreignHistoryRefused=true;}});
        foreignHistory.join();
        Require(foreignHistoryRefused && ReaderAllowed(&file,GetCurrentThreadId()),"A foreign history error cleared its owner.");
        Require(EndLoad(&file,GetCurrentThreadId()),"The foreign history test scope failed to close.");
        Start(file,Actor500Version);Refuse([&]{ReadActorHistory(&file,LegacyHistory-1,nativeHistory);});
        Start(file,Actor500Version);Refuse([&]{ReadActorHistory(&file,LegacyHistory,reinterpret_cast<void*>(Image+0xA1C3485));});
        Start(file,Actor500Version);HistoryBuffer.fill(std::byte{0xD5});Overflow=true;Cursor=0;
        bool overflowRefused=false;try {ReadActorHistory(&file,LegacyHistory,nativeHistory);}catch(const Refusal&){overflowRefused=true;}
        Require(overflowRefused && Cursor==0 && !ReaderAllowed(&file,GetCurrentThreadId()),"Overflow did not clear the owning context.");
        Require(std::all_of(HistoryBuffer.data(),HistoryBuffer.data()+History,[](auto b){return b==std::byte{0xD5};}),"Overflow published incomplete history.");
        Overflow=false;file.overflow=0;Start(file,Actor500Version);ThrowNative=true;
        bool nativeFailed=false;try {ReadActorState(&file);}catch(const NativeFailure&){nativeFailed=true;}
        Require(nativeFailed && !ReaderAllowed(&file,GetCurrentThreadId()) && Counts.secondaryRecords==64,"A native exception retained its context.");
        ThrowNative=false;
        Require(!LoadActorState(nullptr),"The null no-save path changed its native false return.");
        Require(!ReaderAllowed(&file,GetCurrentThreadId()),"The null no-save path created a load scope.");
        AuthoredEarlyPreparation(file,Actor500Version);Require(!LoadActorState(nullptr),"The prepared null path changed its native false return.");
        Require(ReaderAllowed(&file,GetCurrentThreadId()) && Counts.secondaryRecords==500,"The null no-save path changed its prepared context.");
        Require(EndLoad(&file,GetCurrentThreadId()),"The null no-save fixture scope failed to close.");
        for(const auto version:std::array{3u,VmOnlyVersion,Actor500Version}) {
            Secondary.fill(std::byte{0xF6});
            AuthoredEarlyPreparation(file,version);
            Require(ReaderAllowed(&file,GetCurrentThreadId()),"Early preparation ended the later whole-load scope.");
            const auto secondaryCalls=Calls[2];
            Require(LoadActorState(&file),"The actual whole load changed its native true return.");
            Require(Calls[2]==secondaryCalls,"The tagged fixture called the ordinary secondary reader.");
            Require(!ReaderAllowed(&file,GetCurrentThreadId()) && Counts.actorBytes==LegacyCounts.actorBytes &&
                Counts.sentientBytes==LegacyCounts.sentientBytes && Counts.secondaryRecords==64,"Whole completion retained its scope or counts.");
            const auto count=version==Actor500Version?500u:64u;
            Require(std::all_of(Secondary.data(),Secondary.data()+count*0xB00,[](auto b){return b==std::byte{0x64};}),"The tagged secondary prefix differs.");
            CheckZero(Secondary.data()+count*0xB00,(500-count)*0xB00);
        }
        auto refuseWhole=[&](auto action) {
            const auto before=WholeCalls;Refuse(action);Require(WholeCalls==before,"An invalid whole call reached native code.");
        };
        refuseWhole([&]{LoadActorState(&file);});
        AuthoredEarlyPreparation(file,Actor500Version);refuseWhole([&]{LoadActorState(&other);});
        AuthoredEarlyPreparation(file,Actor500Version);bool foreignWholeRefused=false;
        std::thread foreignWhole([&]{try {LoadActorState(&file);}catch(const Refusal&){foreignWholeRefused=true;}});foreignWhole.join();
        Require(foreignWholeRefused && ReaderAllowed(&file,GetCurrentThreadId()),"A foreign whole error cleared its owner.");
        Require(EndLoad(&file,GetCurrentThreadId()),"The foreign whole test scope failed to close.");
        AuthoredEarlyPreparation(file,Actor500Version);WholeReturnsFalse=true;
        Require(!LoadActorState(&file) && !ReaderAllowed(&file,GetCurrentThreadId()) && Counts.secondaryRecords==64,
            "The authored whole false return did not survive scope cleanup.");
        WholeReturnsFalse=false;
        AuthoredEarlyPreparation(file,VmOnlyVersion);ThrowWhole=true;
        bool wholeFailed=false;try {LoadActorState(&file);}catch(const NativeFailure&){wholeFailed=true;}
        Require(wholeFailed && !ReaderAllowed(&file,GetCurrentThreadId()) && Counts.secondaryRecords==64,"A whole exception retained its context.");
        CheckBuffers();
        std::ofstream receipt(argv[1]);Require(static_cast<bool>(receipt),"Cannot write the fixture receipt.");
        receipt<<"{\"passed\":true,\"roots\":"<<Roots<<",\"authoredCallbacks\":["<<Calls[0]<<','<<Calls[1]<<','<<Calls[2]<<','<<Calls[3]
            <<"],\"errors\":"<<Errors<<",\"wholeCallbacks\":"<<WholeCalls<<",\"preparedFiles\":"<<PreparedFiles
            <<",\"nullWholeCallbacks\":"<<NullWholeCalls<<",\"wholeUnwindPhases\":3,\"wholeBooleanResultsPreserved\":true,\"deferredWholeScope\":true,\"taggedSecondaryBypassCovered\":true,\"assembledReentriesExecuted\":true,\"completeAllocationCanaries\":true,\"legacyUnusedActorsChecked\":872,\"followingHistorySectionsPreserved\":true,\"gameWrites\":0}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
