#include "../../patches/early_integrity/ImageMemory.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include <cstdio>
#include <functional>
#include <stdexcept>
#pragma section(".fixture",read,execute)
#pragma comment(linker,"/SECTION:.fixture,ERW")
__declspec(allocate(".fixture")) __declspec(align(4096)) unsigned char pages[8192]{1};
namespace {
void Check(bool value,const char* message) {if(!value)throw std::runtime_error(message);}
bool Refuses(const std::function<void()>& call) {try{call();}catch(const std::runtime_error&){return true;}return false;}
void Protect(void* address,std::size_t size,DWORD value) {
    DWORD old{};Check(VirtualProtect(address,size,value,&old)!=FALSE,"Cannot set fixture protection.");
}
}
int wmain(int argc,wchar_t** argv) {
    if(argc==2) {FILE* output{};if(_wfreopen_s(&output,argv[1],L"w",stdout))return 1;}
    try {
        const auto process=GetCurrentProcess();const auto image=reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
        const auto address=reinterpret_cast<std::uintptr_t>(pages);
        const bool wine=GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"wine_get_version")!=nullptr;
        const auto admit=[&](std::uintptr_t base,std::uintptr_t at,std::size_t size) {
            bo3::early_integrity::RequireImageMemory(process,base,at,size);
        };
        Protect(pages,sizeof(pages),PAGE_EXECUTE_WRITECOPY);
        Check(wine ? !Refuses([&]{admit(image,address,sizeof(pages));}) : Refuses([&]{admit(image,address,sizeof(pages));}),
            "Copy-on-write image selected the wrong platform policy.");
        std::puts("image-copy-on-write-platform-policy passed");
        // Windows uses the existing writable executable policy for the remaining cases.
        if(!wine)Protect(pages,sizeof(pages),PAGE_EXECUTE_READWRITE);
        const DWORD expected=wine?PAGE_EXECUTE_WRITECOPY:PAGE_EXECUTE_READWRITE;
        Check(Refuses([&]{admit(image+4096,address,1);}),"Foreign image admitted.");
        auto* privatePage=VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);
        Check(privatePage && Refuses([&]{admit(reinterpret_cast<std::uintptr_t>(privatePage),reinterpret_cast<std::uintptr_t>(privatePage),1);}),"Private memory admitted.");
        VirtualFree(privatePage,0,MEM_RELEASE);
        const auto mapping=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_EXECUTE_READWRITE,0,4096,nullptr);
        auto* view=mapping?MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS|FILE_MAP_EXECUTE,0,0,4096):nullptr;
        Check(view && Refuses([&]{admit(reinterpret_cast<std::uintptr_t>(view),reinterpret_cast<std::uintptr_t>(view),1);}),"Mapped memory admitted.");
        UnmapViewOfFile(view);CloseHandle(mapping);
        std::puts("foreign-private-and-mapped-memory-refused passed");
        for(const auto value:{PAGE_READWRITE,PAGE_EXECUTE_READ,PAGE_NOACCESS,PAGE_EXECUTE_READWRITE|PAGE_GUARD}) {
            Protect(pages+4096,4096,value);
            Check(Refuses([&]{admit(image,address,sizeof(pages));}),"The second unsuitable page was admitted.");
        }
        Protect(pages+4096,4096,expected);
        Check(Refuses([&]{admit(image,address,0);}) && Refuses([&]{admit(image,UINTPTR_MAX-1,4);}),"Invalid span admitted.");
        std::puts("complete-span-and-invalid-protection-refused passed");
        const std::vector<unsigned char> original{pages[0]},replacement{static_cast<unsigned char>(pages[0]^0xff)};
        vm_startup::Receipt receipt;
        {
            vm_startup::PausedPatch patch(process,{{address,original,replacement}},receipt);
            patch.Apply();
            MEMORY_BASIC_INFORMATION memory{};
            const auto queried=VirtualQuery(pages,&memory,sizeof(memory));
            const auto actual=vm_startup::ReadStopped(process,address,1);
            std::printf("publication protection=%lu expected=%lu byte=%u expected=%u\n",memory.Protect,expected,actual[0],replacement[0]);
            Check(queried==sizeof(memory) && memory.Protect==expected
                && actual==replacement,"Publication did not restore image protection.");
        }
        MEMORY_BASIC_INFORMATION memory{};
        Check(receipt.rollbackCompleted && vm_startup::ReadStopped(process,address,1)==original && VirtualQuery(pages,&memory,sizeof(memory))==sizeof(memory)
            && memory.Protect==expected,"Rollback did not restore bytes and protection.");
        std::puts("copy-on-write-publication-and-rollback passed");
        return 0;
    }catch(const std::exception& error){std::printf("refusal=%s\n",error.what());return 1;}
}
