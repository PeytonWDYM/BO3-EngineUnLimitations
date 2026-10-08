#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>
#include "../../patches/vm_startup/StateErrors.h"
#include <string>

enum class ErrorScenario { ReadSuccess, WriteSuccess, ReadErrors, WriteErrors, Arguments, DecodeError,
    LaterRead, LaterArguments, Suppress, Unwind };
struct ErrorTrace {
    ErrorScenario scenario;
    bo3::vm::StateError stateError;
    DWORD readCalls=0,writeCalls=0,clearCalls=0,originalCalls=0,laterCalls=0,exits=0,homeStores=0,errors=0;
    DWORD stages[64]{};
    DWORD stageCount=0;
    std::uintptr_t observedHome=0;
    int lastCode=0,lastStateError=0;
    bool argumentsPreserved=true,originalSawInactive=true,unwindPassed=false;
};
extern ErrorTrace errorTrace;
extern __declspec(thread) constinit bo3::vm::ImportContext ownedImportContext;
void ErrorStage(DWORD);
void BindErrorFixture(bo3::vm::ErrorFunction entry, bo3::vm::ErrorFunction original,
    bo3::vm::ErrorFunction laterOriginal);
void CallOwnedError();
extern "C" void ClearOwnedImport();
extern "C" void OwnedOriginalError(const char*,int,int,const char*,...);
extern "C" void OwnedLaterError(const char*,int,int,const char*,...);
extern "C" void VmErrorPreludeBody();
