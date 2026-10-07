#include "ProbeContract.h"
extern "C" __declspec(dllexport) void ConsumerTouch() {}
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) ProbeOutput(Stage::ImportedDll);
    return TRUE;
}
