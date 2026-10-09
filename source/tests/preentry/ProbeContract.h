#pragma once
#include <windows.h>
#include <cstdint>

// This contract belongs only to the native fixtures compiled by this harness.
constexpr DWORD kTraceMagic = 0x50454e54;
constexpr DWORD kMaximumEvents = 64;
enum class Scenario : DWORD { Baseline, Protected, EarlyDependency, Denied, LiveReference, Remove };
enum class Stage : DWORD { ProviderInit, Restore, HelperReady, ImportedDll, Tls, Entry,
                          LiveAcquire, RemoveDenied, LiveRelease, Removed, HelperDetach, AfterRemove, Error,
                          UnloadAttempt, HelperRetained };
struct Event { DWORD stage; LONG ready; LONG output; LONG references; };
struct SharedTrace {
    DWORD magic;
    Scenario scenario;
    volatile LONG count;
    volatile LONG ready;
    volatile LONG references;
    volatile LONG unsafeCalls;
    volatile LONG internalErrors;
    Event events[kMaximumEvents];
};
#ifdef PREENTRY_PROVIDER_BUILD
#define PROBE_API __declspec(dllexport)
#else
#define PROBE_API __declspec(dllimport)
#endif
extern "C" {
PROBE_API SharedTrace* ProbeState();
PROBE_API void ProbeRecord(Stage stage, LONG output);
PROBE_API LONG OwnedFactory();
PROBE_API void ProbeOutput(Stage stage);
}
