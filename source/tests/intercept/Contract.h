#pragma once
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <objbase.h>
#include <mmreg.h>
#include <dsound.h>
#include <cstdint>

constexpr DWORD kSdkMagic = 0x53444b49;
constexpr DWORD kSdkStop = 0xe0520001;
constexpr LONG kSdkEvents = 1024;
enum class Mode : DWORD { Memory, PhysicalSilent };
enum class Scenario : DWORD { Baseline, Entry, Worker, WrongEntry, WrongContext, Denied,
    ImportCom, ImportSound, TlsCom, TlsSound, NoBuffer8, ClearFailed, Reentrant, MissingHandshake };
enum class Phase : LONG { Helper, Imported, Tls, Entry, Worker, Shutdown };
enum class Api : DWORD { None, Com, Sound, Thread };
enum class Stage : DWORD { Restore, HooksReady, Imported, Tls, Entry, ThreadCreate, ThreadReturned,
    Suspended, Priority, Resume, Match, Unmatched, Gate, RuntimeReady, Setup, Dispatch, Joined,
    FactoryRequested, RootEnter, ProviderEnter, RootReturn, ColdStop, UnsupportedStop, RecursiveStop,
    NonAudio, RenderPublish, BufferPublish, Format, FirstSilent, Start, FullClear, SplitClear, Play,
    Callback, RemovalDenied, ReferencesReleased, RuntimeClosed, HooksRemoved, Retained, Detach, Error };
struct ModuleIdentity {
    std::uint64_t base, rva;
    DWORD imageSize, timestamp;
    wchar_t path[1024];
};
struct Event {
    Stage stage; Api api; Phase phase;
    DWORD pid, tid, generation;
    LONG value, hooksReady, runtimeReady, depth;
    Api outer;
    std::uint64_t caller;
    GUID clsid, iid;
    ModuleIdentity callerModule;
};
struct Shared {
    DWORD magic; Mode mode; Scenario scenario;
    volatile LONG phase, hooksReady, runtimeReady, count, errors, constructors;
    volatile LONG providerCalls, physicalAudioCalls, rawPublications, generations;
    volatile LONG renderPackets, silentRenderPackets, soundObservations, silentSoundObservations;
    volatile LONG callbackCalls, callbackLive, callbackTid, creatorTid, workerTid, returnedTid;
    volatile LONG matched, unmatched, nativeSetups, nativeContext, priorityResult, resumeResult;
    volatile LONG aborted, abortHresult, fullClears, plays, silentReleases, nonAudioCalls;
    DWORD flags, attributesPresent;
    std::uint64_t stackSize, originalEntry, parameter, returnedHandle;
    std::uint64_t sdkCom, sdkSound, sdkThread;
    ModuleIdentity sdkModules[3];
    Event events[kSdkEvents];
};
#ifdef SDK_HELPER_BUILD
#define SDK_API __declspec(dllexport)
#else
#define SDK_API __declspec(dllimport)
#endif
extern "C" {
SDK_API Shared* SdkTrace();
SDK_API void SdkRecord(Stage, Api, DWORD generation, LONG value, const GUID* clsid, const GUID* iid);
SDK_API BOOL WINAPI SdkInitializeEntry();
SDK_API BOOL WINAPI SdkStopRuntime();
SDK_API void WINAPI SdkObserve(IUnknown*, Api, DWORD);
SDK_API void WINAPI SdkSnapshot();
SDK_API void WINAPI SdkFireCallbacks();
}
#ifdef SDK_CONSUMER_BUILD
#define CONSUMER_API __declspec(dllexport)
#else
#define CONSUMER_API __declspec(dllimport)
#endif
extern "C" {
[[noreturn]] CONSUMER_API void ConsumerStop(HRESULT code);
CONSUMER_API void ConsumerCheck(bool condition, HRESULT code = E_UNEXPECTED);
CONSUMER_API void ConsumerGood(HRESULT code);
}
inline bool WorkerScenario(Scenario value) { return value >= Scenario::Worker && value <= Scenario::Denied; }
