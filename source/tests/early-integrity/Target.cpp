#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include "Fixture.h"

int wmain(int argc,wchar_t** argv) {
    if(argc!=5)return 2;
    const HANDLE mapping=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,argv[1]);
    const HANDLE ready=OpenEventW(EVENT_MODIFY_STATE,FALSE,argv[2]);
    const HANDLE done=OpenEventW(SYNCHRONIZE,FALSE,argv[3]);
    if(!mapping || !ready || !done)return 3;
    auto* state=static_cast<FixtureState*>(MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(FixtureState)));
    if(!state)return 4;
    const auto image=LoadLibraryW(argv[4]);
    if(!image)return 5;
    if(!GetProcAddress(image,MAKEINTRESOURCEA(1)))return 6;
    state->imageBase=reinterpret_cast<std::uintptr_t>(image);
    try {SeedFixtureProtection(GetCurrentProcess(),state->imageBase);}catch(...){return 9;}
    if(!SetEvent(ready))return 7;
    return WaitForSingleObject(done,60000)==WAIT_OBJECT_0?0:8;
}
