#include "GameProfile.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include <bcrypt.h>
#include <cstring>
#include <stdexcept>

namespace bo3::enhanced {
namespace {
void Require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
std::array<unsigned char, 32> Digest(std::span<const unsigned char> bytes) {
    struct Algorithm {
        BCRYPT_ALG_HANDLE value{};
        ~Algorithm() { if (value) BCryptCloseAlgorithmProvider(value, 0); }
    } algorithm;
    struct Hash {
        BCRYPT_HASH_HANDLE value{};
        ~Hash() { if (value) BCryptDestroyHash(value); }
    } hash;
    Require(BCryptOpenAlgorithmProvider(&algorithm.value, BCRYPT_SHA256_ALGORITHM, nullptr, 0) == 0, "Cannot open the code digest provider.");
    Require(BCryptCreateHash(algorithm.value, &hash.value, nullptr, 0, nullptr, 0, 0) == 0, "Cannot create the code digest.");
    Require(BCryptHashData(hash.value, const_cast<PUCHAR>(bytes.data()), static_cast<ULONG>(bytes.size()), 0) == 0,
        "Cannot hash the stopped code range.");
    std::array<unsigned char, 32> result{};
    Require(BCryptFinishHash(hash.value, result.data(), static_cast<ULONG>(result.size()), 0) == 0, "Cannot finish the code digest.");
    return result;
}
void Validate(const GameManifest& manifest) {
    Require(manifest.imageSize == 494186496 && manifest.timestamp == 1765634846
        && manifest.allocationEntry == 0x12df230 && manifest.poolPointer == 0x5124580 && manifest.hashPointer == 0x5124500,
        "Unsupported game manifest identity.");
    Require(manifest.counts.size() == 19 && !manifest.guards.empty(), "The native count or code inventory is incomplete.");
    for (const auto& count : manifest.counts) {
        Require(count.size >= 5 && count.size <= count.bytes.size() && count.rva <= manifest.imageSize - count.size
            && count.immediateOffset <= count.size - 4, "Invalid native count instruction.");
        std::uint32_t stock{};
        std::memcpy(&stock, count.bytes.data() + count.immediateOffset, sizeof(stock));
        Require(stock == 130000, "A native count instruction does not contain the stock capacity.");
    }
    for (const auto& guard : manifest.guards)
        Require(guard.size && guard.size <= manifest.imageSize && guard.rva <= manifest.imageSize - guard.size,
            "A native code guard exceeds the image.");
}
template<class T> T Read(HANDLE process, std::uintptr_t address) {
    const auto bytes = vm_startup::ReadStopped(process, address, sizeof(T));
    T value;
    std::memcpy(&value, bytes.data(), sizeof(value));
    return value;
}
}
vm_startup::Profile MakeGameProfile(const GameManifest& manifest, std::uint32_t total) {
    Validate(manifest);
    Require(total == 500001 || total == 1000001, "Use 500k or 1m usable server slots.");
    vm_startup::Profile profile{manifest.imageSize, manifest.allocationEntry, manifest.poolPointer, manifest.hashPointer, {}, {}};
    profile.checks.push_back({manifest.allocationEntry, {manifest.allocationPrefix.begin(), manifest.allocationPrefix.end()}});
    for (const auto& entry : manifest.entries)
        profile.checks.push_back({entry.rva, {entry.original.begin(), entry.original.end()}});
    for (const auto& count : manifest.counts) {
        profile.checks.push_back({count.rva, {count.bytes.begin(), count.bytes.begin() + count.size}});
        std::vector<unsigned char> replacement(sizeof(total));
        std::memcpy(replacement.data(), &total, sizeof(total));
        const auto original = count.bytes.begin() + count.immediateOffset;
        profile.edits.push_back({count.rva + count.immediateOffset, {original, original + 4}, std::move(replacement)});
    }
    return profile;
}
void VerifyGameCode(HANDLE process, std::uintptr_t imageBase, const GameManifest& manifest) {
    Validate(manifest);
    Require(imageBase <= UINTPTR_MAX - manifest.imageSize, "The game image address overflows.");
    const auto dos = Read<IMAGE_DOS_HEADER>(process, imageBase);
    Require(dos.e_magic == IMAGE_DOS_SIGNATURE && dos.e_lfanew >= static_cast<LONG>(sizeof(dos))
        && static_cast<std::uint32_t>(dos.e_lfanew) <= manifest.imageSize - sizeof(IMAGE_NT_HEADERS64), "The game DOS header differs.");
    const auto pe = Read<IMAGE_NT_HEADERS64>(process, imageBase + dos.e_lfanew);
    Require(pe.Signature == IMAGE_NT_SIGNATURE && pe.FileHeader.Machine == IMAGE_FILE_MACHINE_AMD64
        && pe.FileHeader.TimeDateStamp == manifest.timestamp && pe.OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR64_MAGIC
        && pe.OptionalHeader.SizeOfImage == manifest.imageSize, "The game PE identity differs.");
    for (const auto& guard : manifest.guards)
        Require(Digest(vm_startup::ReadStopped(process, imageBase + guard.rva, guard.size)) == guard.digest,
            "A native code range differs. No hooks were published.");
}
void VerifyMigrationUnallocated(HANDLE process, std::uintptr_t imageBase) {
    for (const auto rva : {0x3ec4ed8u, 0x3ec4ee0u, 0x3ec4ee8u, 0x3ec4ef0u})
        Require(Read<std::uintptr_t>(process, imageBase + rva) == 0, "Migration storage already exists. Early activation is required.");
    for (const auto rva : {0x3ec4ef8u, 0x3ec4efcu})
        Require(Read<std::uint32_t>(process, imageBase + rva) == 0, "Migration capacity was already published. Activation refused.");
}
}
