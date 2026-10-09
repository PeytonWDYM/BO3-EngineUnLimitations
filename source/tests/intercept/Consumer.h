#pragma once
#include "Contract.h"
#include "../audio-driver/Probe.h"
void RunConsumers();
void RetainedConsumers();
void ReleaseConsumers();
void CreateWorker();
extern "C" __declspec(dllexport) DWORD JoinWorker();
extern "C" __declspec(dllexport) DWORD WINAPI SdkOwnedWorker(LPVOID);
extern "C" __declspec(dllexport) DWORD WINAPI SdkOtherWorker(LPVOID);
