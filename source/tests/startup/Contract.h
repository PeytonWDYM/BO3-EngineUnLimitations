#pragma once
#include <windows.h>
#include <objbase.h>
#include <dsound.h>
#include <cstdint>

constexpr DWORD kStartupMagic = 0x53544152;
constexpr LONG kEventCapacity = 512;
constexpr DWORD kControlledStop = 0xe0510001;
enum class Scenario : DWORD { Baseline, Entry, SharedEntry, Worker, ImportCom, ImportSound,
    TlsCom, TlsSound, Dependency, Denied, Live, NoBuffer8, ClearFailed,
    StartupMatched, StartupWrongEntry, StartupWrongContext, StartupReadinessDenied, StartupColdCom, StartupColdSound };
enum class Phase : LONG { Dependency, Helper, ImportedDll, Tls, Entry, Worker, Shutdown };
enum class Api : DWORD { None, Com, Sound };
enum class Stage : DWORD { Uncovered, Restore, HookReady, RuntimeReady, ImportedProbe, TlsProbe,
    EntryProbe, WorkerProbe, RootEnter, RawFactory, RootReturn, EarlyStop, ControlledStop, ConsumerAfter,
    RenderPublish, BufferPublish, RenderOutput, SoundOutput, Callback, RemovalDenied, ReferencesReleased,
    RuntimeDestroyed, HooksRemoved, HelperRetained, HelperDetach, NativeFailure, Error, OrdinalMatch,
    ThreadCreate, ThreadReturned, SuspendedChecked, ThreadPriority, ThreadResume, GateMatched, GateUnmatched,
    GateEnter, ReadinessDenied, NativeSetup, NativeDispatch, NativeExit, WorkerJoined };
struct Event {
    Stage stage;
    Phase phase;
    Api api;
    DWORD thread;
    DWORD generation;
    LONG value;
    LONG hooksReady;
    LONG runtimeReady;
    GUID iid;
};
struct Shared {
    DWORD magic;
    Scenario scenario;
    volatile LONG phase;
    volatile LONG hooksReady;
    volatile LONG runtimeReady;
    volatile LONG count;
    volatile LONG errors;
    volatile LONG uncovered;
    volatile LONG constructors;
    volatile LONG loaderConstructors;
    volatile LONG providerCalls;
    volatile LONG rawPublications;
    volatile LONG renderPackets;
    volatile LONG silentRenderPackets;
    volatile LONG soundPlays;
    volatile LONG silentSoundPlays;
    volatile LONG generations;
    volatile LONG callbacks;
    volatile LONG callbackThread;
    volatile LONG workerThread;
    volatile LONG unsafeBranch;
    volatile LONG aborted;
    volatile LONG abortHresult;
    volatile LONG creatorThread;
    volatile LONG returnedThread;
    volatile LONG gateMatched;
    volatile LONG gateUnmatched;
    volatile LONG nativeSetups;
    volatile LONG nativeContext;
    volatile LONG priorityResult;
    volatile LONG resumeResult;
    DWORD creationFlags;
    DWORD attributesPresent;
    std::uint64_t stackSize;
    std::uint64_t originalEntry;
    std::uint64_t originalParameter;
    std::uint64_t nativeEntry;
    std::uint64_t nativeParameter;
    std::uint64_t returnedHandle;
    Event events[kEventCapacity];
};
using ComFactory = HRESULT (WINAPI*)(REFCLSID, LPUNKNOWN, DWORD, REFIID, void**);
using SoundFactory = HRESULT (WINAPI*)(LPCGUID, LPDIRECTSOUND8*, LPUNKNOWN);
#ifdef STARTUP_SHIM_BUILD
#define SHIM_API __declspec(dllexport)
#else
#define SHIM_API __declspec(dllimport)
#endif
extern "C" {
SHIM_API Shared* StartupState();
SHIM_API void StartupEvent(Stage stage, Api api, DWORD generation, LONG value, const GUID* iid);
SHIM_API void SetMemoryFactories(ComFactory com, SoundFactory sound);
SHIM_API HRESULT WINAPI OwnedCoCreateInstance(REFCLSID, LPUNKNOWN, DWORD, REFIID, void**);
SHIM_API HRESULT WINAPI OwnedDirectSoundCreate8(LPCGUID, LPDIRECTSOUND8*, LPUNKNOWN);
SHIM_API HANDLE WINAPI OwnedCreateThread(LPSECURITY_ATTRIBUTES, SIZE_T, LPTHREAD_START_ROUTINE, LPVOID, DWORD, LPDWORD);
SHIM_API DWORD WINAPI OwnedGenericThread(LPVOID);
SHIM_API DWORD WINAPI OwnedOtherThread(LPVOID);
SHIM_API void CreateStartupWorker();
SHIM_API DWORD JoinStartupWorker();
}
inline bool StartupWorkerScenario(Scenario value) { return value >= Scenario::StartupMatched && value <= Scenario::StartupColdSound; }
