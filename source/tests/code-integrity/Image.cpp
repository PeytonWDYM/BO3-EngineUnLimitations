#include "Fixture.h"
#pragma section(".owned",read,write)
extern "C" __declspec(dllexport) __declspec(allocate(".owned")) unsigned char OwnedCode[kFixtureBytes]{};
BOOL WINAPI DllMain(HINSTANCE,DWORD,LPVOID) { return TRUE; }
