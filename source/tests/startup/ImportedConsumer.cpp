#include "Contract.h"
#include <mmdeviceapi.h>
extern "C" __declspec(dllexport) void ImportedConsumerTouch() {}
BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        auto* state = StartupState();
        state->phase = static_cast<LONG>(Phase::ImportedDll);
        StartupEvent(Stage::ImportedProbe, Api::None, 0, 0, nullptr);
        if (StartupWorkerScenario(state->scenario)) CreateStartupWorker();
        if (state->scenario == Scenario::ImportCom) {
            void* output = nullptr;
            OwnedCoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), &output);
            StartupEvent(Stage::ConsumerAfter, Api::Com, 0, 0, nullptr);
        } else if (state->scenario == Scenario::ImportSound) {
            IDirectSound8* output = nullptr;
            OwnedDirectSoundCreate8(nullptr, &output, nullptr);
            StartupEvent(Stage::ConsumerAfter, Api::Sound, 0, 0, nullptr);
        }
    }
    return TRUE;
}
