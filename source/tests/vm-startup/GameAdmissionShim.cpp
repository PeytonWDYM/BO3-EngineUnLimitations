#include "GameManifest.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include <cstring>
#include <exception>
#include <stdexcept>

struct AdmissionResult {
    std::uint32_t accepted, countEdits, codeGuards;
    char error[256];
};
static_assert(sizeof(AdmissionResult) == 268);

// The owned Python caller provides a fixed result record. No native game code executes.
extern "C" __declspec(dllexport) void CheckGameAdmission(HANDLE process, std::uintptr_t base,
    std::uint32_t total, AdmissionResult* result) noexcept {
    *result = {};
    try {
        const auto& manifest = bo3::enhanced::ExactGameManifest;
        const auto profile = bo3::enhanced::MakeGameProfile(manifest, total);
        result->countEdits = static_cast<std::uint32_t>(profile.edits.size());
        result->codeGuards = static_cast<std::uint32_t>(manifest.guards.size());
        bo3::enhanced::VerifyGameCode(process, base, manifest);
        bo3::enhanced::VerifyMigrationUnallocated(process, base);
        for (const auto& check : profile.checks)
            if (vm_startup::ReadStopped(process, base + check.rva, check.bytes.size()) != check.bytes)
                throw std::runtime_error("An enclosing native instruction check differs.");
        result->accepted = 1;
    } catch (const std::exception& error) { strcpy_s(result->error, error.what()); }
}
