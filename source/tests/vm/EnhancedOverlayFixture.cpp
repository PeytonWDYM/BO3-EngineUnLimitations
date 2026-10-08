#include <Windows.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

struct Slot { std::uint64_t value; std::uint32_t type,pad; std::uint64_t refs; std::uint32_t next; unsigned char rest[36]; };
struct State { Slot* pool; std::uint32_t deferred,pad; const char* error; std::uint32_t depth,pad28; };
struct RuntimeCode { unsigned char instructions[19][6]; unsigned char guard[2]; };
struct Bindings { std::uintptr_t image; std::uint32_t total,clients,stockClients,mode; std::uintptr_t callbacks[3]; };
static_assert(sizeof(Slot)==64 && sizeof(State)==32 && sizeof(Bindings)==48);
extern "C" {
__declspec(dllexport) State vmEnhancedState[2]{};
__declspec(dllexport) __declspec(align(4096)) RuntimeCode vmEnhancedCode{};
}
namespace {
void Seed(State& state,std::uint32_t capacity) {
    auto* pool=static_cast<Slot*>(VirtualAlloc(nullptr,static_cast<SIZE_T>(capacity)*64,MEM_COMMIT|MEM_RESERVE,PAGE_READWRITE));
    if(!pool) ExitProcess(3);
    pool[0].next=4; pool[1].type=17; pool[2].type=23; pool[2].next=3; pool[3].type=23;
    for(std::uint32_t index=4;index<capacity;++index) { pool[index].type=27; pool[index].next=index+1<capacity ? index+1 : 0; }
    state={pool,2,0,nullptr,3,0};
}
}
int main(int argc,char** argv) {
    if(argc!=2) return 2;
    const bool stock=std::strcmp(argv[1],"stock")==0;
    auto* helper=LoadLibraryW(L"Bo3EnhancedHelper.dll");
    if(!helper) return 4;
    auto* bindings=reinterpret_cast<Bindings*>(GetProcAddress(helper,"Bo3VmStateBindings"));
    const auto callback=reinterpret_cast<std::uintptr_t>(GetProcAddress(helper,"OwnedCallback"));
    if(!bindings || !callback) return 5;
    *bindings={reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr)),stock ? 130000u : 500001u,18,8,1,{callback,callback,callback}};
    for(auto& instruction:vmEnhancedCode.instructions) {
        const unsigned char bytes[]{0x41,0xb8,0xd0,0xfb,1,0}; std::memcpy(instruction,bytes,6);
        const std::uint32_t capacity=stock ? 130000 : 500001; std::memcpy(instruction+2,&capacity,4);
    }
    vmEnhancedCode.guard[0]=0x90; vmEnhancedCode.guard[1]=0xcc;
    Seed(vmEnhancedState[0],stock ? 130000 : 500001); Seed(vmEnhancedState[1],65000);
    std::printf("{\"pid\":%lu,\"helperBase\":%llu}\n",GetCurrentProcessId(),static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(helper))); std::fflush(stdout);
    char text[64]{};
    while(std::fgets(text,sizeof(text),stdin)) {
        const std::string command=text;
        if(command.starts_with("stop")) break;
        if(command.starts_with("partial")) { const std::uint32_t capacity=130000; std::memcpy(vmEnhancedCode.instructions[18]+2,&capacity,4); }
        else if(command.starts_with("opcode")) vmEnhancedCode.instructions[18][0]=0x40;
        else if(command.starts_with("adjacent")) vmEnhancedCode.guard[0]=0x91;
        else if(command.starts_with("binding")) bindings->mode=0;
        else if(command.starts_with("unreadable")) {
            DWORD previous{};
            if(!VirtualProtect(&vmEnhancedCode,4096,PAGE_NOACCESS,&previous)) return 6;
        }
        std::puts("changed"); std::fflush(stdout);
    }
    DWORD previous{};
    if(!VirtualProtect(&vmEnhancedCode,4096,PAGE_READWRITE,&previous)) return 7;
    for(const auto& state:vmEnhancedState) VirtualFree(state.pool,0,MEM_RELEASE);
    FreeLibrary(helper); return 0;
}
