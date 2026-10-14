#define WIN32_LEAN_AND_MEAN
#include <windows.h>
// The loader experiment has no process, pool, or registration side effects.
BOOL WINAPI DllMain(HINSTANCE,DWORD,LPVOID) {return TRUE;}
