#include "RuntimePlan.h"
#include "RuntimeProfile.generated.h"
#include "NativeLoadBridge.h"
#include "RuntimeBinding.h"
#include "ActorRecord.h"
#include <bcrypt.h>
#include <algorithm>
#include <array>
#include <cstring>
#include <limits>
#include <sstream>
#include <stdexcept>
#pragma comment(lib,"bcrypt.lib")

namespace bo3::actors {
namespace {
using Bytes=std::vector<unsigned char>;
constexpr auto NoIndex=std::numeric_limits<std::uint32_t>::max();
Bytes Read(HANDLE process,std::uintptr_t address,std::size_t size) {
    Bytes bytes(size);SIZE_T count{};
    if(!ReadProcessMemory(process,reinterpret_cast<void*>(address),bytes.data(),size,&count)||count!=size)
        throw std::runtime_error("The actor native source read failed.");
    return bytes;
}
std::array<unsigned char,32> Sha256(const Bytes& bytes) {
    BCRYPT_ALG_HANDLE algorithm{};BCRYPT_HASH_HANDLE hash{};
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)
        throw std::runtime_error("The actor SHA-256 provider failed.");
    std::array<unsigned char,32> result{};
    const bool passed=BCryptCreateHash(algorithm,&hash,nullptr,0,nullptr,0,0)>=0 &&
        BCryptHashData(hash,const_cast<PUCHAR>(bytes.data()),static_cast<ULONG>(bytes.size()),0)>=0 &&
        BCryptFinishHash(hash,result.data(),static_cast<ULONG>(result.size()),0)>=0;
    if(hash)BCryptDestroyHash(hash);BCryptCloseAlgorithmProvider(algorithm,0);
    if(!passed)throw std::runtime_error("The actor SHA-256 calculation failed.");
    return result;
}
template<class T>Bytes Pod(const T& value) {
    Bytes bytes(sizeof value);std::memcpy(bytes.data(),&value,sizeof value);return bytes;
}
void Put32(Bytes& bytes,std::size_t offset,std::uint32_t value) {std::memcpy(bytes.data()+offset,&value,4);}
void Admit(HANDLE process,vm_startup::ImageRange game) {
    for(const auto& guard:profile::Guards) {
        if(!guard.size || guard.rva>game.size || guard.size>game.size-guard.rva)
            throw std::runtime_error("The actor source guard exceeds the image.");
        auto bytes=Read(process,game.base+guard.rva,guard.size);
        for(const auto& field:profile::Normalizations) {
            if(field.rva<guard.rva || field.rva+8>guard.rva+guard.size)continue;
            std::uintptr_t value{};std::memcpy(&value,bytes.data()+field.rva-guard.rva,8);
            if(value!=game.base+field.target)throw std::runtime_error("The actor native image pointer differs.");
            value=profile::CapturedBase+field.target;std::memcpy(bytes.data()+field.rva-guard.rva,&value,8);
        }
        const auto digest=Sha256(bytes);
        if(std::memcmp(digest.data(),profile::Data+guard.digest,digest.size())) {
            std::ostringstream message;
            message<<"The complete actor native source guard differs at RVA 0x"<<std::hex<<guard.rva
                <<" ("<<std::dec<<guard.size<<" bytes), expected SHA256 ";
            auto writeDigest=[&](const unsigned char* value) {
                constexpr char digits[]="0123456789abcdef";
                for(std::size_t index=0;index<digest.size();++index)
                    message<<digits[value[index]>>4]<<digits[value[index]&15];
            };
            writeDigest(profile::Data+guard.digest);message<<", observed SHA256 ";writeDigest(digest.data());
            throw std::runtime_error(message.str());
        }
    }
    for(const auto rva:{0xA1B0798u,0xA1B0790u}) {
        const auto bytes=Read(process,game.base+rva,8);
        if(std::any_of(bytes.begin(),bytes.end(),[](auto byte){return byte!=0;}))
            throw std::runtime_error("The native actor pool is already allocated.");
    }
}
bool AdmittedCopy(std::uint32_t rva,std::uint32_t size) {
    return std::any_of(std::begin(profile::Guards),std::end(profile::Guards),[=](const auto& g){return rva>=g.rva && rva-g.rva<=g.size && size<=g.size-(rva-g.rva);});
}
Bytes Render(HANDLE process,const profile::Template& body,std::uintptr_t game,std::uintptr_t arena) {
    Bytes bytes(body.size),coverage(body.size);
    for(std::uint32_t i=0;i<body.pieceCount;++i) {
        const auto& piece=profile::Pieces[body.pieceFirst+i];
        if(piece.offset>body.size || piece.size>body.size-piece.offset)throw std::runtime_error("The actor instruction span exceeds its body.");
        if(piece.source==NoIndex)std::memcpy(bytes.data()+piece.offset,profile::Data+piece.data,piece.size);
        else {
            if(!AdmittedCopy(piece.source,piece.size))throw std::runtime_error("The actor instruction copy has no complete guard.");
            const auto raw=Read(process,game+piece.source,piece.size);
            std::copy(raw.begin(),raw.end(),bytes.begin()+piece.offset);
        }
        std::fill_n(coverage.begin()+piece.offset,piece.size,static_cast<unsigned char>(1));
    }
    if(std::find(coverage.begin(),coverage.end(),0)!=coverage.end())throw std::runtime_error("The actor body has an incomplete instruction span.");
    const auto origin=(body.arena?arena:game)+body.offset;
    for(std::uint32_t i=0;i<body.fixupCount;++i) {
        const auto& fixup=profile::Fixups[body.fixupFirst+i];
        if(fixup.offset>bytes.size() || fixup.width>bytes.size()-fixup.offset || (fixup.width!=1&&fixup.width!=4&&fixup.width!=8))
            throw std::runtime_error("The actor operand exceeds its complete body.");
        if(fixup.imageAnchor>=profile::ImageSize || (fixup.imageAnchor&&!fixup.imageRelative))
            throw std::runtime_error("The actor context anchor exceeds its image-relative operand.");
        const auto target=(fixup.arena?arena:game)+fixup.target;
        if(fixup.next==NoIndex&&!fixup.imageRelative) {
            if(fixup.width!=8)throw std::runtime_error("The actor absolute operand has an invalid width.");
            std::memcpy(bytes.data()+fixup.offset,&target,8);
        } else {
            const auto reference=fixup.imageRelative?game+fixup.imageAnchor:origin+fixup.next;
            const auto value=static_cast<std::int64_t>(target)-static_cast<std::int64_t>(reference);
            if(fixup.width==8)throw std::runtime_error("The actor relative operand has an invalid width.");
            const auto limit=std::int64_t{1}<<(fixup.width*8-1);
            if(value< -limit || value>=limit)throw std::runtime_error("The actor relative operand exceeds its signed width.");
            std::memcpy(bytes.data()+fixup.offset,&value,fixup.width);
        }
    }
    return bytes;
}
Bytes Transfer(std::uintptr_t source,std::uintptr_t target,unsigned char opcode) {
    const auto relative=static_cast<std::int64_t>(target)-static_cast<std::int64_t>(source+5);
    if(relative<INT32_MIN || relative>INT32_MAX)throw std::runtime_error("The actor source transfer exceeds relative reach.");
    Bytes bytes(5);bytes[0]=opcode;const auto displacement=static_cast<std::int32_t>(relative);
    std::memcpy(bytes.data()+1,&displacement,4);return bytes;
}
void Thunk(ActorArena& arena,std::uint32_t offset,std::uintptr_t destination) {
    std::array<unsigned char,14> bytes{0xFF,0x25,0,0,0,0};std::memcpy(bytes.data()+6,&destination,8);arena.Write(offset,bytes.data(),bytes.size());
}
}

RuntimePlan BuildRuntimePlan(HANDLE process,vm_startup::ImageRange game,vm_startup::ImageRange helper,const HelperOffsets& exports) {
    if(game.size!=494186496 || !game.base || game.base>UINTPTR_MAX-game.size || !helper.base || helper.base>UINTPTR_MAX-helper.size ||
            game.base%0x1000 || helper.base%0x1000)
        throw std::runtime_error("The actor runtime image identity is invalid.");
    SYSTEM_INFO system{};GetSystemInfo(&system);
    if(system.dwPageSize!=0x1000)throw std::runtime_error("The actor publication page size is unsupported.");
    auto address=[&](std::uint32_t rva,std::size_t size=1) {
        if(!rva || rva>helper.size || size>helper.size-rva)throw std::runtime_error("An actor helper export exceeds its image.");
        return helper.base+rva;
    };
    for(const auto rva:{exports.activate,exports.phaseHandler,exports.actorReader,exports.sentientReader,exports.secondaryReader,
            exports.historyReader,exports.actorReentry,exports.sentientReentry,exports.secondaryReentry,exports.wholeReader,exports.wholeReentry})address(rva);
    for(const auto& [rva,size]:std::array<std::pair<std::uint32_t,std::size_t>,4>{{
            {exports.countBindings,sizeof(LoadBindings)},{exports.nativeBindings,sizeof(NativeBindings)},
            {exports.readBranches,sizeof(ReadBranches)},{exports.runtimeBindings,sizeof(RuntimeBindings)}}}) {
        const auto destination=address(rva,size);
        if(destination%0x1000+size>0x1000)throw std::runtime_error("An actor helper binding crosses a publication page.");
    }
    Admit(process,game);
    RuntimePlan plan{{},std::make_shared<ActorArena>(process,game.base,game.size)};
    auto& arena=*plan.arena;const auto base=arena.Base();
    auto edit=[&](std::uintptr_t destination,Bytes replacement) {
        const auto original=Read(process,destination,replacement.size());
        for(std::size_t offset=0;offset<replacement.size();) {
            const auto size=std::min(replacement.size()-offset,0x1000-(destination+offset)%0x1000);
            plan.edits.push_back({destination+offset,Bytes(original.begin()+offset,original.begin()+offset+size),
                Bytes(replacement.begin()+offset,replacement.begin()+offset+size)});
            offset+=size;
        }
    };
    auto bind=[&](std::uint32_t rva,Bytes replacement) {
        const auto destination=address(rva,replacement.size());
        const auto original=Read(process,destination,replacement.size());
        if(std::any_of(original.begin(),original.end(),[](auto byte){return byte!=0;}))
            throw std::runtime_error("The actor helper binding is already initialized.");
        edit(destination,std::move(replacement));
    };
    for(const auto& body:profile::Templates) {
        auto bytes=Render(process,body,game.base,base);
        if(body.arena)arena.Write(body.offset,bytes.data(),bytes.size());else edit(game.base+body.offset,std::move(bytes));
    }
    Bytes actors(static_cast<std::size_t>(ExpandedCounts.actorBytes));
    InitializeActorRecords(reinterpret_cast<std::byte*>(actors.data()),500,game.base);
    arena.Write(0x1F10000,actors.data(),actors.size());arena.Write(0x2C40000,&LegacyCounts,sizeof LegacyCounts);
    constexpr std::array<std::uint32_t,6> thunkOffsets{0x1F1000,0x1F1100,0x1F1120,0x1F1140,0x1F1160,0x1F1180};
    const std::array destinations{address(exports.phaseHandler),address(exports.actorReader),address(exports.sentientReader),address(exports.secondaryReader),address(exports.historyReader),address(exports.wholeReader)};
    for(std::size_t i=0;i<thunkOffsets.size();++i)Thunk(arena,thunkOffsets[i],destinations[i]);
    constexpr std::array<std::uint32_t,3> entries{0xB60E0,0xC44C0,0xFA0E0};
    for(std::size_t i=0;i<entries.size();++i) {
        const auto original=Read(process,game.base+entries[i],5);
        if(original!=Bytes{0x48,0x89,0x5C,0x24,0x08})throw std::runtime_error("The actor reader reentry prefix differs.");
        edit(game.base+entries[i],Transfer(game.base+entries[i],base+thunkOffsets[i+1],0xE9));
    }
    edit(game.base+0xFF77B,Transfer(game.base+0xFF77B,base+thunkOffsets[4],0xE8));
    if(Read(process,game.base+0x19C3270,7)!=Bytes{0x48,0x83,0xEC,0x28,0x48,0x85,0xC9})
        throw std::runtime_error("The actor whole-load reentry prefix differs.");
    auto wholeHook=Transfer(game.base+0x19C3270,base+thunkOffsets[5],0xE9);wholeHook.resize(7,0x90);
    edit(game.base+0x19C3270,std::move(wholeHook));
    // Windows expects each runtime row and unwind RVA relative to the actual game image base.
    const auto delta=static_cast<std::uint32_t>(base-game.base);
    static_assert(profile::ExtraFunctionCount==thunkOffsets.size());
    constexpr auto functionCount=std::size(profile::Functions)+profile::ExtraFunctionCount;
    std::vector<RUNTIME_FUNCTION> rows(functionCount);
    std::vector<Bytes> metadata;metadata.reserve(functionCount);
    std::uint32_t cursor=0x210000;
    for(std::size_t i=0;i<std::size(profile::Functions);++i) {
        const auto& source=profile::Functions[i];
        metadata.emplace_back(profile::Data+source.data,profile::Data+source.data+source.size);
        rows[i]={delta+source.begin,delta+source.end,delta+cursor};cursor+=(source.size+3)&~3u;
    }
    for(std::size_t i=0;i<thunkOffsets.size();++i) {
        metadata.push_back({1,0,0,0});rows[std::size(profile::Functions)+i]={delta+thunkOffsets[i],delta+thunkOffsets[i]+6,delta+cursor};cursor+=4;
    }
    if(cursor>0x3E0000)throw std::runtime_error("The actor unwind metadata exceeds its region.");
    for(std::size_t i=0;i<std::size(profile::Functions);++i) {
        auto& bytes=metadata[i];const auto& source=profile::Functions[i];
        if(source.parent!=NoIndex) {
            if(source.parent>=std::size(profile::Functions)||bytes.size()<12)throw std::runtime_error("The actor unwind parent is invalid.");
            std::memcpy(bytes.data()+bytes.size()-12,&rows[source.parent],12);
        } else if((bytes[0]>>3)&3) {
            if(bytes.size()<8)throw std::runtime_error("The actor handler metadata is incomplete.");
            std::uint32_t handler{};std::memcpy(&handler,bytes.data()+bytes.size()-8,4);
            if(handler==0x201F1000)Put32(bytes,bytes.size()-8,delta+thunkOffsets[0]);
        }
    }
    // Extra thunks follow the existing bodies. Keep Windows lookup rows in address order.
    for(std::size_t i=1;i<rows.size();++i)if(rows[i-1].EndAddress>rows[i].BeginAddress)
        throw std::runtime_error("The actor runtime function rows overlap.");
    for(std::size_t i=0;i<rows.size();++i)arena.Write(rows[i].UnwindData-delta,metadata[i].data(),metadata[i].size());
    constexpr std::uint32_t tableOffset=0x200000,phaseOffset=0x3E0000;
    if(rows.size()*sizeof(RUNTIME_FUNCTION)>0x10000)throw std::runtime_error("The actor runtime table exceeds its region.");
    arena.Write(tableOffset,rows.data(),rows.size()*sizeof(RUNTIME_FUNCTION));
    std::vector<actor_pool::NativeHandlerFrame> phases;
    for(const auto& source:profile::Phases)phases.push_back({game.base+source.control,game.base,
        reinterpret_cast<PRUNTIME_FUNCTION>(game.base+source.owner),source.stack,static_cast<UCHAR>(source.prolog),
        reinterpret_cast<PEXCEPTION_ROUTINE>(game.base+source.handler),reinterpret_cast<void*>(game.base+source.data)});
    if(phases.size()*sizeof(actor_pool::NativeHandlerFrame)>0x20000)throw std::runtime_error("The actor handler phases exceed their region.");
    arena.Write(phaseOffset,phases.data(),phases.size()*sizeof(actor_pool::NativeHandlerFrame));
    bind(exports.countBindings,Pod(LoadBindings{reinterpret_cast<ReadCounts*>(base+0x2C40000)}));
    bind(exports.nativeBindings,Pod(NativeBindings{
        reinterpret_cast<Reader>(address(exports.actorReentry)),reinterpret_cast<Reader>(address(exports.sentientReentry)),
        reinterpret_cast<Reader>(address(exports.secondaryReentry)),reinterpret_cast<NativeRead>(game.base+0x22778B0),
        reinterpret_cast<migration::ErrorEntry>(game.base+0x20EC0B0),game.base,
        reinterpret_cast<std::byte*>(base+0x1F10000),reinterpret_cast<std::byte*>(base+0x400000),
        reinterpret_cast<std::byte*>(base+0xB00000),reinterpret_cast<std::byte*>(base+0x2610000),
        reinterpret_cast<std::byte*>(base+0x2C00000),reinterpret_cast<std::byte*>(base+0x2C50000),reinterpret_cast<std::byte*>(base+0x2400000),
        reinterpret_cast<decltype(NativeBindings::whole)>(address(exports.wholeReentry))}));
    bind(exports.readBranches,Pod(ReadBranches{game.base+entries[0]+5,game.base+entries[1]+5,game.base+entries[2]+5,game.base+0x19C3277}));
    bind(exports.runtimeBindings,Pod(RuntimeBindings{game.base,base,
        reinterpret_cast<PRUNTIME_FUNCTION>(base+tableOffset),static_cast<std::uint32_t>(rows.size()),static_cast<std::uint32_t>(phases.size()),
        reinterpret_cast<const actor_pool::NativeHandlerFrame*>(base+phaseOffset)}));
    std::sort(plan.edits.begin(),plan.edits.end(),[](const auto& left,const auto& right){return left.address<right.address;});
    for(std::size_t i=1;i<plan.edits.size();++i)if(plan.edits[i-1].address+plan.edits[i-1].replacement.size()>plan.edits[i].address)
        throw std::runtime_error("The actor runtime publication edits overlap.");
    if(plan.edits.size()!=profile::EditCount)throw std::runtime_error("The actor runtime publication count differs.");
    arena.Protect();return plan;
}
}
