#pragma once
#include <windows.h>
#include <excpt.h>

namespace bo3::actor_pool {
// Caller-owned pointers must survive dispatch. Runtime binding and native-owner admission remain disabled.
struct NativeHandlerFrame {
    DWORD64 controlPc;
    DWORD64 imageBase;
    PRUNTIME_FUNCTION function;
    DWORD64 temporaryStackBytes;
    UCHAR prologBytes;
    PEXCEPTION_ROUTINE handler;
    PVOID handlerData;
};

// Translate the fixed frame and native language location together. The Windows context stays shared.
inline EXCEPTION_DISPOSITION DispatchNativeHandler(PEXCEPTION_RECORD exception, PVOID frame, PCONTEXT context,
                                                    PDISPATCHER_CONTEXT dispatcher, const NativeHandlerFrame& native) {
    if (native.controlPc < native.imageBase + native.function->BeginAddress + native.prologBytes)
        return ExceptionContinueSearch;
    const auto originalFrame = reinterpret_cast<DWORD64>(frame) + native.temporaryStackBytes;
    auto translated = *dispatcher;
    translated.ControlPc = native.controlPc;
    translated.ImageBase = native.imageBase;
    translated.FunctionEntry = native.function;
    translated.EstablisherFrame = originalFrame;
    translated.LanguageHandler = native.handler;
    translated.HandlerData = native.handlerData;
    const auto result = native.handler(exception, reinterpret_cast<PVOID>(originalFrame), context, &translated);
    dispatcher->ScopeIndex = translated.ScopeIndex;
    return result;
}
}
