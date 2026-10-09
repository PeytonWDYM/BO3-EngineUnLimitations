#include "ErrorOwned.h"
#include <cstdarg>
#include <cstdio>
#include <cstring>

ErrorTrace errorTrace;
__declspec(thread) constinit bo3::vm::ImportContext ownedImportContext{};
namespace {
bo3::vm::ErrorFunction laterOriginal;
constexpr char nativeFile[]="owned-native-error";
constexpr char nativeFormat[]="%I64x|%p|%.3f|%d|%s";
constexpr char nativeText[]="owned stack text";
constexpr ULONG_PTR errorExit=0xe042564d;

bo3::vm::StateError Read(std::uint32_t instance,void* file) {
    if(instance!=0 || file!=&errorTrace) ++errorTrace.errors;
    ++errorTrace.readCalls;
    ownedImportContext.active=true;
    if(errorTrace.scenario==ErrorScenario::DecodeError) CallOwnedError();
    if(errorTrace.stateError==bo3::vm::StateError::None) ownedImportContext.active=false;
    return errorTrace.stateError;
}
bo3::vm::StateError Write(std::uint32_t instance,void* file) {
    if(instance!=0 || file!=&errorTrace) ++errorTrace.errors;
    ++errorTrace.writeCalls;
    return errorTrace.stateError;
}
}
void ErrorStage(DWORD stage) { errorTrace.stages[errorTrace.stageCount++]=stage; }
void BindErrorFixture(bo3::vm::ErrorFunction entry,bo3::vm::ErrorFunction original,
    bo3::vm::ErrorFunction later) {
    bo3::vm::Bo3VmErrorBindings={entry,original,Read,Write};
    laterOriginal=later;
}
void CallOwnedError() {
    bo3::vm::Bo3VmErrorBindings.entry(nativeFile,147,2,nativeFormat,0x1122334455667788ull,
        static_cast<void*>(&errorTrace),3.125,-17,nativeText);
}
extern "C" void ClearOwnedImport() {
    ownedImportContext={};
    ++errorTrace.clearCalls;
    ErrorStage(1);
}
extern "C" void OwnedOriginalError(const char* file,int line,int code,const char* format,...) {
    ++errorTrace.originalCalls;
    errorTrace.lastCode=code;
    ErrorStage(3);
    errorTrace.originalSawInactive &= !ownedImportContext.active;
    bool valid=code==2 && errorTrace.observedHome==reinterpret_cast<std::uintptr_t>(format);
    va_list args;
    va_start(args,format);
    const bool forwarded=errorTrace.scenario==ErrorScenario::LaterRead || errorTrace.scenario==ErrorScenario::LaterArguments;
    if(forwarded) {
        const auto* text=va_arg(args,const char*);
        valid &= std::strcmp(format,"%s")==0 && text[0]!=0;
        char expected[1024]{};
        if(errorTrace.scenario==ErrorScenario::LaterRead) {
            std::snprintf(expected,sizeof(expected),"VM state read rejected (error %d).",static_cast<int>(errorTrace.stateError));
            valid &= std::strcmp(file,"bo3-vm-state")==0 && line>0;
        } else {
            std::snprintf(expected,sizeof(expected),nativeFormat,0x1122334455667788ull,
                static_cast<void*>(&errorTrace),3.125,-17,nativeText);
            valid &= file==nativeFile && line==147;
        }
        valid &= std::strcmp(text,expected)==0;
    } else if(errorTrace.scenario==ErrorScenario::Arguments || errorTrace.scenario==ErrorScenario::DecodeError) {
        valid &= file==nativeFile && line==147 && format==nativeFormat;
        valid &= va_arg(args,std::uint64_t)==0x1122334455667788ull;
        valid &= va_arg(args,void*)==&errorTrace;
        valid &= va_arg(args,double)==3.125;
        valid &= va_arg(args,int)==-17;
        valid &= va_arg(args,const char*)==nativeText;
    } else {
        errorTrace.lastStateError=va_arg(args,int);
        valid &= std::strcmp(file,"bo3-vm-state")==0 && line>0
            && errorTrace.lastStateError==static_cast<int>(errorTrace.stateError)
            && (errorTrace.stateError==bo3::vm::StateError::UnsupportedMode
                ? std::strstr(format,"supports Zombies only")!=nullptr && std::strstr(format,"stock Steam")!=nullptr
                : std::strstr(format,"VM state")!=nullptr);
    }
    va_end(args);
    errorTrace.argumentsPreserved &= valid;
    if(!valid || ownedImportContext.active) ++errorTrace.errors;
    RaiseException(static_cast<DWORD>(errorExit),0,0,nullptr);
}
extern "C" void OwnedLaterError(const char* file,int line,int code,const char* format,...) {
    ++errorTrace.laterCalls;
    ErrorStage(2);
    char text[1024]{};
    va_list args;
    va_start(args,format);
    std::vsnprintf(text,sizeof(text),format,args);
    va_end(args);
    if(std::strstr(text,"VCRedist")) return;
    laterOriginal(file,line,code,"%s",text);
}
