#include "Fixture.h"
#include "../../patches/early_integrity/Plan.h"
#include "EarlyIntegrityProfile.h"
#include <cstring>
#include <stdexcept>

namespace integrity=bo3::early_integrity;
extern "C" std::uintptr_t Probe(void*,void*,void*,std::uint64_t);
namespace {
void Check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
void Disp(unsigned char* field,std::uintptr_t to,std::uintptr_t next) {
    const auto delta=static_cast<std::int32_t>(static_cast<std::int64_t>(to)-static_cast<std::int64_t>(next));
    std::memcpy(field,&delta,4);
}
}
void ProveRelays() {
    struct Allocation {unsigned char* bytes;~Allocation(){VirtualFree(bytes,0,MEM_RELEASE);}}
        allocation{static_cast<unsigned char*>(VirtualAlloc(nullptr,4096,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE))};
    Check(allocation.bytes!=nullptr,"Cannot allocate authored relay fixture.");
    const auto base=reinterpret_cast<std::uintptr_t>(allocation.bytes);
    for(const auto& original:integrity::kSites) {
        auto site=original;site.leaRva=0;site.chainDestinationRva=2048;
        DWORD prior{};Check(VirtualProtect(allocation.bytes,4096,PAGE_READWRITE,&prior)!=FALSE,"Cannot seed authored relay fixture.");
        std::memset(allocation.bytes,0xcc,4096);
        const auto relay=integrity::EncodeRelay(site,base,base+512);
        std::memcpy(allocation.bytes+512,relay.data(),relay.size());
        allocation.bytes[0]=0xe9;Disp(allocation.bytes+1,base+512,base+5);
        allocation.bytes[5]=allocation.bytes[6]=0x90;
        if(original.leaRva+7!=original.storeRva) {
            // Authored flag-preserving register and stack transport.
            const unsigned char transport[]{0x53,0x48,0x8d,0x1d,0,0,0,0,0x48,0x87,0x1c,0x24,0xc3};
            std::memcpy(allocation.bytes+7,transport,sizeof(transport));
            Disp(allocation.bytes+11,base+128,base+15);
        } else {
            allocation.bytes[7]=0xe9;Disp(allocation.bytes+8,base+128,base+12);
        }
        const unsigned char store[]{0x89,0x04,0x8a,0xc3};
        std::memcpy(allocation.bytes+128,store,sizeof(store));
        Check(VirtualProtect(allocation.bytes,1024,PAGE_EXECUTE_READWRITE,&prior)!=FALSE,"Cannot admit authored relay execution.");
        Check(FlushInstructionCache(GetCurrentProcess(),allocation.bytes,1024)!=FALSE,"Cannot flush authored relay execution.");
        for(const auto expected:{0u,0x12345678u,0xffffffffu})for(const auto flags:{0x202ull,0xad7ull}) {
            alignas(16) std::array<unsigned char,256> frame{};frame.fill(0x5a);
            std::uint32_t local=0xa5a55a5a;
            std::memcpy(frame.data()+site.computedLocalSlot,&local,4);
            const auto pointer=reinterpret_cast<std::uintptr_t>(&expected);
            std::memcpy(frame.data()+site.expectedTableSlot,&pointer,8);
            const auto computed=reinterpret_cast<std::uintptr_t>(frame.data()+site.computedLocalSlot);
            std::memcpy(frame.data()+240,&computed,8);
            const std::uint32_t zero=0;std::memcpy(frame.data()+site.indexSlot,&zero,4);
            auto healthyFrame=frame;std::memcpy(healthyFrame.data()+site.computedLocalSlot,&expected,4);
            std::array<std::uintptr_t,17> actual{};
            const auto rsp=Probe(allocation.bytes,frame.data(),actual.data(),flags);
            Check(actual[0]==expected && actual[1]==0x1111 && actual[2]==0 && actual[3]==base+2048
                && actual[4]==reinterpret_cast<std::uintptr_t>(frame.data()) && actual[5]==rsp
                && actual[6]==0x2222 && actual[7]==0x3333 && actual[8]==0x4444 && actual[9]==0x5555
                && actual[10]==0x6666 && actual[11]==0x7777 && actual[12]==0x8888 && actual[13]==0x9999
                && actual[14]==0xaaaa && actual[15]==0xbbbb,"Authored relay changed a live register or RSP.");
            Check((actual[16]&0x8d5)==(flags&0x8d5),"Authored relay changed arithmetic flags.");
            Check(frame==healthyFrame,"Authored relay changed unrelated frame bytes.");
            std::uint32_t chain{};std::memcpy(&chain,allocation.bytes+2048,4);
            Check(chain==expected,"Authored relay did not correct the chained DWORD.");
        }
    }
}
