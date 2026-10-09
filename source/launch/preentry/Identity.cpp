#include "Identity.h"
#include "BuildIdentity.h"
#include <bcrypt.h>
#include <array>
#include <cstdint>
#include <stdexcept>

void Require(bool condition, const char* operation) {
    if (!condition) throw std::runtime_error(operation);
}
namespace {
HANDLE OpenLocked(const std::filesystem::path& path, std::vector<HANDLE>& locks) {
    const HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
    Require(file != INVALID_HANDLE_VALUE, "The fixed fixture file is missing or locked.");
    // Capacity is reserved before any file opens. Keep file locks through process exit.
    locks.push_back(file);
    return file;
}
void ReadAt(HANDLE file, std::uint64_t offset, void* buffer, DWORD size, const char* failure) {
    LARGE_INTEGER position{};
    position.QuadPart = static_cast<LONGLONG>(offset);
    DWORD read = 0;
    Require(SetFilePointerEx(file, position, nullptr, FILE_BEGIN) != FALSE
        && ReadFile(file, buffer, size, &read, nullptr) != FALSE && read == size, failure);
}
std::string Sha256(HANDLE file) {
    LARGE_INTEGER start{};
    Require(SetFilePointerEx(file, start, nullptr, FILE_BEGIN) != FALSE, "Cannot read the fixture file.");
    struct Algorithm { BCRYPT_ALG_HANDLE value = nullptr; ~Algorithm() { if (value) BCryptCloseAlgorithmProvider(value, 0); } } algorithm;
    struct Hash { BCRYPT_HASH_HANDLE value = nullptr; ~Hash() { if (value) BCryptDestroyHash(value); } } hash;
    Require(BCryptOpenAlgorithmProvider(&algorithm.value, BCRYPT_SHA256_ALGORITHM, nullptr, 0) == 0, "Cannot open SHA256.");
    Require(BCryptCreateHash(algorithm.value, &hash.value, nullptr, 0, nullptr, 0, 0) == 0, "Cannot create SHA256.");
    std::array<unsigned char, 65536> buffer{};
    for (;;) {
        DWORD read = 0;
        Require(ReadFile(file, buffer.data(), static_cast<DWORD>(buffer.size()), &read, nullptr) != FALSE, "Cannot read the fixture file.");
        if (!read) break;
        Require(BCryptHashData(hash.value, buffer.data(), read, 0) == 0, "Cannot hash the fixture file.");
    }
    std::array<unsigned char, 32> bytes{};
    Require(BCryptFinishHash(hash.value, bytes.data(), static_cast<ULONG>(bytes.size()), 0) == 0, "Cannot finish SHA256.");
    std::string actual;
    actual.reserve(64);
    constexpr char digits[] = "0123456789abcdef";
    for (const auto byte : bytes) { actual += digits[byte >> 4]; actual += digits[byte & 15]; }
    return actual;
}
}
void VerifyFile(const std::filesystem::path& path, const char* expected, std::vector<HANDLE>& locks) {
    Require(Sha256(OpenLocked(path, locks)) == expected, "The fixed fixture SHA256 differs from this launcher build.");
}
std::string VerifyGameBuild(const std::filesystem::path& path, std::uint32_t timestamp, std::uint32_t imageSize,
    std::vector<HANDLE>& locks) {
    const auto file = OpenLocked(path, locks);
    constexpr auto unsupported = "Unsupported game version. Its PE timestamp or image size differs from this launcher's profile.";
    IMAGE_DOS_HEADER dos{};
    ReadAt(file, 0, &dos, sizeof(dos), unsupported);
    Require(dos.e_magic == IMAGE_DOS_SIGNATURE && dos.e_lfanew >= static_cast<LONG>(sizeof(dos)), unsupported);
    IMAGE_NT_HEADERS64 pe{};
    ReadAt(file, static_cast<std::uint32_t>(dos.e_lfanew), &pe, sizeof(pe), unsupported);
    Require(pe.Signature == IMAGE_NT_SIGNATURE && pe.FileHeader.Machine == IMAGE_FILE_MACHINE_AMD64
        && pe.OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR64_MAGIC
        && pe.FileHeader.TimeDateStamp == timestamp && pe.OptionalHeader.SizeOfImage == imageSize, unsupported);
    // Copies of one build can differ outside the code. The hash is recorded, and the in-memory code guards decide.
    return Sha256(file);
}

std::filesystem::path PrivateOutput(const wchar_t* text) {
    const auto path = std::filesystem::weakly_canonical(std::filesystem::absolute(text));
    const auto repo = std::filesystem::weakly_canonical(kRepositoryRoot);
    auto left = path.begin();
    auto right = repo.begin();
    for (; left != path.end() && right != repo.end(); ++left, ++right) {
        if (CompareStringOrdinal(left->c_str(), -1, right->c_str(), -1, TRUE) != CSTR_EQUAL) break;
    }
    Require(right != repo.end(), "Write fixture traces outside the repository.");
    Require(!std::filesystem::exists(path), "Use a new trace output file.");
    return path;
}
