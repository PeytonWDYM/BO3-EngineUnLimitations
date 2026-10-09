#include "Target.h"
#include <bcrypt.h>
#include <TlHelp32.h>
#include <algorithm>
#include <array>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>

namespace patch {
static std::string file_hash(HANDLE file) {
    BCRYPT_ALG_HANDLE algorithm = nullptr;
    BCRYPT_HASH_HANDLE hash = nullptr;
    if (BCryptOpenAlgorithmProvider(&algorithm, BCRYPT_SHA256_ALGORITHM, nullptr, 0) < 0) throw std::runtime_error("Cannot open SHA256 provider.");
    struct Cleanup {
        BCRYPT_ALG_HANDLE& algorithm;
        BCRYPT_HASH_HANDLE& hash;
        ~Cleanup() { if (hash) BCryptDestroyHash(hash); BCryptCloseAlgorithmProvider(algorithm, 0); }
    } cleanup{algorithm, hash};
    if (BCryptCreateHash(algorithm, &hash, nullptr, 0, nullptr, 0, 0) < 0) throw std::runtime_error("Cannot create SHA256 hash.");
    std::array<uint8_t, 65536> buffer{};
    DWORD read = 0;
    while (true) {
        if (!ReadFile(file, buffer.data(), static_cast<DWORD>(buffer.size()), &read, nullptr)) throw win_error("Read executable");
        if (read == 0) break;
        if (BCryptHashData(hash, buffer.data(), read, 0) < 0) throw std::runtime_error("Cannot update SHA256 hash.");
    }
    std::array<uint8_t, 32> digest{};
    if (BCryptFinishHash(hash, digest.data(), static_cast<ULONG>(digest.size()), 0) < 0) throw std::runtime_error("Cannot finish SHA256 hash.");
    std::ostringstream text;
    for (const auto value : digest) text << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(value);
    return text.str();
}

Target::Target(DWORD pid, const Profile& profile, bool writable) : pid_(pid) {
    const DWORD rights = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | SYNCHRONIZE | (writable ? PROCESS_VM_OPERATION | PROCESS_VM_WRITE : 0);
    process_ = Handle(OpenProcess(rights, FALSE, pid));
    if (!process_.get()) throw win_error("OpenProcess");
    if (exited()) throw std::runtime_error("Target process exited.");
    USHORT process_machine = 0, native_machine = 0;
    if (!IsWow64Process2(process_.get(), &process_machine, &native_machine)) throw win_error("IsWow64Process2");
    if (process_machine != IMAGE_FILE_MACHINE_UNKNOWN || native_machine != IMAGE_FILE_MACHINE_AMD64) throw std::runtime_error("Target must be native Windows x64.");
    std::wstring actual_path(32768, L'\0');
    DWORD path_size = static_cast<DWORD>(actual_path.size());
    if (!QueryFullProcessImageNameW(process_.get(), 0, actual_path.data(), &path_size)) throw win_error("Query process path");
    actual_path.resize(path_size);
    const auto expected_path = profile.target.lexically_normal().wstring();
    if (_wcsicmp(actual_path.c_str(), expected_path.c_str()) != 0) throw std::runtime_error("Target executable path differs.");
    // Deny writes and deletion while the session verifies this executable.
    executable_ = Handle(CreateFileW(actual_path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
    if (executable_.get() == INVALID_HANDLE_VALUE) throw win_error("Open executable");
    if (file_hash(executable_.get()) != profile.sha256) throw std::runtime_error("Target executable SHA256 differs.");
    Handle snapshot(CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid));
    if (snapshot.get() == INVALID_HANDLE_VALUE) throw win_error("Module snapshot");
    MODULEENTRY32W module{};
    module.dwSize = sizeof(module);
    if (!Module32FirstW(snapshot.get(), &module)) throw win_error("Read main module");
    if (_wcsicmp(module.szExePath, actual_path.c_str()) != 0) throw std::runtime_error("Main module path differs.");
    base_ = reinterpret_cast<uintptr_t>(module.modBaseAddr);
    image_size_ = module.modBaseSize;
    if (!base_ || image_size_ != profile.image_size) throw std::runtime_error("Target image size differs.");
    const auto dos_bytes = read_bytes(process_.get(), base_, sizeof(IMAGE_DOS_HEADER));
    IMAGE_DOS_HEADER dos{};
    std::memcpy(&dos, dos_bytes.data(), sizeof(dos));
    if (dos.e_magic != IMAGE_DOS_SIGNATURE || dos.e_lfanew < 0 || static_cast<uint64_t>(dos.e_lfanew) + sizeof(IMAGE_NT_HEADERS64) > image_size_) throw std::runtime_error("Invalid target PE header.");
    const auto nt_bytes = read_bytes(process_.get(), base_ + dos.e_lfanew, sizeof(IMAGE_NT_HEADERS64));
    IMAGE_NT_HEADERS64 nt{};
    std::memcpy(&nt, nt_bytes.data(), sizeof(nt));
    if (nt.Signature != IMAGE_NT_SIGNATURE || nt.FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64 || nt.OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC) throw std::runtime_error("Target PE machine differs.");
    if (nt.FileHeader.TimeDateStamp != profile.timestamp) throw std::runtime_error("Target PE timestamp differs.");
    if (nt.OptionalHeader.SizeOfImage != image_size_) throw std::runtime_error("Target PE image size differs.");
    for (const auto& record : profile.records) verify_range(record);
    std::cout << "identity verified pid=" << pid_ << " base=0x" << std::hex << base_ << std::dec << " image_size=" << image_size_ << " sha256=" << profile.sha256 << '\n';
}

bool Target::exited() const {
    const DWORD status = WaitForSingleObject(process_.get(), 0);
    if (status == WAIT_FAILED) throw win_error("Wait for target");
    return status == WAIT_OBJECT_0;
}

void Target::verify_range(const Record& record) const {
    if (record.rva >= image_size_ || record.original.size() > image_size_ - record.rva) throw std::runtime_error("Patch exceeds image bounds.");
    uintptr_t cursor = base_ + static_cast<uintptr_t>(record.rva);
    const auto end = cursor + record.original.size();
    while (cursor < end) {
        MEMORY_BASIC_INFORMATION region{};
        if (!VirtualQueryEx(process_.get(), reinterpret_cast<void*>(cursor), &region, sizeof(region))) throw win_error("VirtualQueryEx");
        if (region.State != MEM_COMMIT || region.Type != MEM_IMAGE || reinterpret_cast<uintptr_t>(region.AllocationBase) != base_ || (region.Protect & (PAGE_NOACCESS | PAGE_GUARD))) throw std::runtime_error("Patch range is not readable selected-image memory.");
        cursor = (std::min)(end, reinterpret_cast<uintptr_t>(region.BaseAddress) + region.RegionSize);
    }
}

void Target::verify_bytes(const std::vector<Record>& records, bool replacement) const {
    for (const auto& record : records) {
        verify_range(record);
        if (read_bytes(process_.get(), base_ + static_cast<uintptr_t>(record.rva), record.original.size()) != (replacement ? record.replacement : record.original)) {
            throw std::runtime_error(replacement ? "Patch removal conflict. Current bytes differ from this session's replacement." : "Patch original bytes differ.");
        }
    }
}
}
