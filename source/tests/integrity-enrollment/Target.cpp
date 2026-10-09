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
__declspec(dllexport) __declspec(align(4096)) unsigned char vmEnhancedCode[116]{};
__declspec(dllexport) __declspec(align(4096)) unsigned char integrityCode[1365][64]{};
__declspec(dllexport) __declspec(align(4096)) unsigned char integrityContexts[18][64]{};
}
namespace {
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
    const bool originalEndpoints=stock || std::strcmp(argv[1],"legacy")==0;
    const auto image=reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    auto* helper=LoadLibraryW(L"Bo3EnhancedHelper.dll");if(!helper)return 4;
    auto* bindings=reinterpret_cast<Bindings*>(GetProcAddress(helper,"Bo3VmStateBindings"));
    const auto callback=reinterpret_cast<std::uintptr_t>(GetProcAddress(helper,"OwnedCallback"));
    if(!bindings || !callback)return 5;
    *bindings={image,stock?130000u:500001u,18,8,1,{callback,callback,callback}};
    for(unsigned int i=0;i<19;++i){const unsigned char code[]{0x41,0xb8,0xd0,0xfb,1,0};
        std::memcpy(vmEnhancedCode+i*6,code,6);const std::uint32_t total=stock?130000:500001;std::memcpy(vmEnhancedCode+i*6+2,&total,4);}
    vmEnhancedCode[114]=0x90;vmEnhancedCode[115]=0xcc;
    const unsigned char x[]{0x8b,0x0c,0x8b,0x33,0x0c,0x82},n[]{0x8b,0x0c,0x8b,0xf7,0xd9,0x03,0x0c,0x82},c[]{0x8b,0x04,0x82,0x8b,0x14,0x8b,0x3b,0xc2};
    for(unsigned int i=0;i<1365;++i){auto* row=integrityCode[i];std::memset(row,0x90,64);
        const auto original=i<247 || i>=1353?x:i<506?n:c;const size_t width=i<247 || i>=1353?6:8;
        std::memcpy(row,original,width);
        if(!originalEndpoints && i<1353){if(i<506){row[3]=0x31;row[4]=0xc9;std::memset(row+5,0x90,width-5);}else row[7]=0xc0;}
        const auto pointer=image+static_cast<std::uintptr_t>(reinterpret_cast<unsigned char*>(vmEnhancedCode)-reinterpret_cast<unsigned char*>(image));
        std::memcpy(row+16,&pointer,8);row[32]=static_cast<unsigned char>(i&255);
    }
    for(unsigned int i=0;i<18;++i){auto* row=integrityContexts[i];std::memset(row,0x90,64);row[0]=0xb8;
        const std::uint32_t typed=4;std::memcpy(row+1,&typed,4);row[5]=0x85;row[6]=0xc0;row[7]=0x74;row[8]=0;
        const auto pointer=reinterpret_cast<std::uintptr_t>(integrityCode);std::memcpy(row+16,&pointer,8);row[32]=static_cast<unsigned char>(i);}
    Seed(vmEnhancedState[0],stock?130000:500001);Seed(vmEnhancedState[1],65000);
    std::printf("{\"pid\":%lu,\"helperBase\":%llu}\n",GetCurrentProcessId(),static_cast<unsigned long long>(reinterpret_cast<std::uintptr_t>(helper)));std::fflush(stdout);
    char text[64]{};
    while(std::fgets(text,sizeof(text),stdin)){const std::string command=text;if(command.starts_with("stop"))break;
        if(command.starts_with("restore"))integrityCode[0][3]=0x33;
        else if(command.starts_with("prefix"))integrityCode[0][0]=0x90;
        else if(command.starts_with("transform"))integrityCode[1353][3]=0x31;
        else if(command.starts_with("source"))integrityContexts[0][1]=5;
        else if(command.starts_with("path"))integrityContexts[17][7]=0x75;
        else if(command.starts_with("aslr"))integrityCode[0][16]^=1;
        else if(command.starts_with("partial")){const std::uint32_t total=130000;std::memcpy(vmEnhancedCode+18*6+2,&total,4);}
        else if(command.starts_with("binding"))bindings->mode=0;
        else if(command.starts_with("boot")){auto* boot=reinterpret_cast<unsigned char*>(GetProcAddress(helper,"Bo3EnhancedBoot"));boot[16]=0;}
        else if(command.starts_with("unreadable")){DWORD old{};if(!VirtualProtect(integrityCode,4096,PAGE_NOACCESS,&old))return 6;}
        std::puts("changed");std::fflush(stdout);
    }
    DWORD previous{};if(!VirtualProtect(integrityCode,4096,PAGE_READWRITE,&previous))return 7;
    for(const auto& state:vmEnhancedState)VirtualFree(state.pool,0,MEM_RELEASE);FreeLibrary(helper);return 0;
}
