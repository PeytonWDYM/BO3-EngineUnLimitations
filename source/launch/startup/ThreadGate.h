#pragma once
#include "../../tests/startup/Contract.h"
using ThreadFactory = HANDLE (WINAPI*)(LPSECURITY_ATTRIBUTES, SIZE_T, LPTHREAD_START_ROUTINE, LPVOID, DWORD, LPDWORD);
extern ThreadFactory OriginalThread;
HANDLE WINAPI InterceptOwnedThread(LPSECURITY_ATTRIBUTES, SIZE_T, LPTHREAD_START_ROUTINE, LPVOID, DWORD, LPDWORD) noexcept;
BOOL InitializeWorkerRuntime();
