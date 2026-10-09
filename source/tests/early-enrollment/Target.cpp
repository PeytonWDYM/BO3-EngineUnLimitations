#include <Windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

struct Slot {std::uint64_t value;std::uint32_t type,pad;std::uint64_t refs;std::uint32_t next;unsigned char rest[36];};
struct State {Slot* pool;std::uint32_t deferred,pad;const char* error;std::uint32_t depth,pad28;};
struct Bindings {std::uintptr_t image;std::uint32_t total,clients,stockClients,mode;std::uintptr_t callbacks[3];};
static_assert(sizeof(Slot)==64 && sizeof(State)==32 && sizeof(Bindings)==48);
extern "C" {
__declspec(dllexport) State vmEnhancedState[2]{};
__declspec(dllexport) unsigned char vmEnhancedCode[116]{};
__declspec(dllexport) __declspec(align(4096)) unsigned char earlySites[1069][16]{};
__declspec(dllexport) __declspec(align(4096)) unsigned char earlyArena[36864]{};
}
namespace {
void Relative(unsigned char* output,std::uintptr_t destination,std::uintptr_t next) {
    const auto value=static_cast<std::int32_t>(static_cast<std::intptr_t>(destination)-static_cast<std::intptr_t>(next));
    std::memcpy(output,&value,4);
}
void Seed(State& state,std::uint32_t capacity) {
    auto* pool=static_cast<Slot*>(VirtualAlloc(nullptr,static_cast<SIZE_T>(capacity)*64,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if(!pool)ExitProcess(3);
    pool[0].next=4;pool[1].type=17;pool[2].type=23;pool[2].next=3;pool[3].type=23;
    for(std::uint32_t i=4;i<capacity;++i){pool[i].type=27;pool[i].next=i+1<capacity?i+1:0;}
    state={pool,2,0,nullptr,3,0};
}
}
int main(int argc,char** argv) {
    if(argc!=2)return 2;
    const bool stock=std::strcmp(argv[1],"stock")==0;
    const auto image=reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    auto* helper=LoadLibraryW(L"Bo3EnhancedHelper.dll");if(!helper)return 4;
    auto* bindings=reinterpret_cast<Bindings*>(GetProcAddress(helper,"Bo3VmStateBindings"));
    const auto callback=reinterpret_cast<std::uintptr_t>(GetProcAddress(helper,"OwnedCallback"));
    if(!bindings || !callback)return 5;
    *bindings={image,stock?130000u:500001u,18,8,1,{callback,callback,callback}};
    for(unsigned int i=0;i<19;++i){const unsigned char code[]{0x41,0xb8,0xd0,0xfb,1,0};
        std::memcpy(vmEnhancedCode+i*6,code,6);const std::uint32_t total=stock?130000:500001;std::memcpy(vmEnhancedCode+i*6+2,&total,4);}
    vmEnhancedCode[114]=0x90;vmEnhancedCode[115]=0xcc;
    std::memset(earlyArena,0xcc,sizeof(earlyArena));
    for(unsigned int i=0;i<1069;++i) {
        auto* source=earlySites[i];auto* relay=earlyArena+i*32;
        const auto s=reinterpret_cast<std::uintptr_t>(source),r=reinterpret_cast<std::uintptr_t>(relay);
        const unsigned char prefix[]{0x48,0x8b,0x55,0x40,0x8b,0x02,0x89,0x45,0x44,0x48,0x8d,0x15};
        std::memcpy(relay,prefix,sizeof(prefix));Relative(relay+12,s+8,r+16);
        relay[16]=0xe9;Relative(relay+17,s+7,r+21);
        if(stock){source[0]=0x48;source[1]=0x8d;source[2]=0x15;Relative(source+3,s+8,s+7);}
        else{source[0]=0xe9;Relative(source+1,r,s+5);source[5]=source[6]=0x90;}
    }
    Seed(vmEnhancedState[0],stock?130000:500001);Seed(vmEnhancedState[1],65000);
    std::printf("{\"pid\":%lu,\"helperBase\":%llu,\"arena\":%llu}\n",GetCurrentProcessId(),
        static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(helper)),
        static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(earlyArena)));std::fflush(stdout);
    char text[64]{};
    while(std::fgets(text,sizeof(text),stdin)) {
        const std::string command=text;if(command.starts_with("stop"))break;
        if(command.starts_with("source"))earlySites[1068][0]=0x90;
        else if(command.starts_with("relay"))earlyArena[1068*32+1]^=1;
        else if(command.starts_with("padding"))earlyArena[36863]=0;
        else if(command.starts_with("partial")){const std::uint32_t total=130000;std::memcpy(vmEnhancedCode+18*6+2,&total,4);}
        else if(command.starts_with("binding"))bindings->mode=0;
        else if(command.starts_with("boot")){auto* boot=reinterpret_cast<unsigned char*>(GetProcAddress(helper,"Bo3EnhancedBoot"));boot[16]=0;}
        else if(command.starts_with("unreadable")){DWORD old{};if(!VirtualProtect(earlyArena,4096,PAGE_NOACCESS,&old))return 6;}
        std::puts("changed");std::fflush(stdout);
    }
    for(const auto& state:vmEnhancedState)VirtualFree(state.pool,0,MEM_RELEASE);FreeLibrary(helper);return 0;
}
