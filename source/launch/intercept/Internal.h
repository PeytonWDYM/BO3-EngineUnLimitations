#pragma once
#define SDK_HELPER_BUILD
#include "../../tests/intercept/Contract.h"
#include "../activation/ActivationBoundary.h"

using ComFactory = HRESULT (WINAPI*)(REFCLSID, LPUNKNOWN, DWORD, REFIID, void**);
using SoundFactory = HRESULT (WINAPI*)(LPCGUID, LPDIRECTSOUND8*, LPUNKNOWN);
using ThreadFactory = HANDLE (WINAPI*)(LPSECURITY_ATTRIBUTES, SIZE_T, LPTHREAD_START_ROUTINE, LPVOID, DWORD, LPDWORD);
extern ComFactory OriginalCom;
extern SoundFactory OriginalSound;
extern ThreadFactory OriginalThread;
extern thread_local LONG AudioDepth;
extern thread_local Api OuterApi;
extern thread_local std::uint64_t RootCaller;
struct CallArguments { DWORD context, aggregation, outputProvided, outputNull, failed; };
extern thread_local CallArguments RootArguments;
bool MapTrace();
void CloseTrace();
[[noreturn]] void StopSdk(HRESULT, Stage);
void RequireSdk(bool, HRESULT = E_UNEXPECTED);
BOOL InitializeSdk(Phase);
HRESULT ProviderCom(REFCLSID, LPUNKNOWN, DWORD, REFIID, void**);
HRESULT ProviderSound(LPCGUID, LPDIRECTSOUND8*, LPUNKNOWN);
bool ChangeHooks(bool);
HANDLE WINAPI InterceptThread(LPSECURITY_ATTRIBUTES, SIZE_T, LPTHREAD_START_ROUTINE, LPVOID, DWORD, LPDWORD) noexcept;
bool DescribeAddress(std::uint64_t address, ModuleIdentity& info);
