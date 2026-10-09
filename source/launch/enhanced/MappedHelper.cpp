#include "MappedHelper.h"
#include "../../patches/vm_startup/PausedPatch.h"
#include "../preentry/Identity.h"
#include <Psapi.h>
#include <algorithm>
#include <cstring>

namespace bo3::enhanced {
namespace {
const IMAGE_NT_HEADERS64& Header(HMODULE module) {
    const auto* base = reinterpret_cast<const unsigned char*>(module);
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    Require(dos->e_magic == IMAGE_DOS_SIGNATURE && dos->e_lfanew > 0, "The helper DOS header differs.");
    const auto& nt = *reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
    Require(nt.Signature == IMAGE_NT_SIGNATURE && nt.FileHeader.Machine == IMAGE_FILE_MACHINE_AMD64
        && nt.OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR64_MAGIC, "Use the x64 helper.");
    return nt;
}
std::uint32_t Export(HMODULE module, const char* name, std::uint32_t size) {
    const auto base = reinterpret_cast<std::uintptr_t>(module);
    const auto address = reinterpret_cast<std::uintptr_t>(GetProcAddress(module, name));
    Require(address > base && address - base < size, "An exact helper export is missing.");
    return static_cast<std::uint32_t>(address - base);
}
void RelocateSection(HMODULE local, const IMAGE_NT_HEADERS64& nt, std::uintptr_t remote,
    std::uint32_t rva, std::vector<unsigned char>& bytes) {
    const auto& directory = nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
    const auto* base = reinterpret_cast<const unsigned char*>(local);
    const auto delta = remote - reinterpret_cast<std::uintptr_t>(local);
    std::size_t position = 0;
    while (position < directory.Size) {
        Require(directory.VirtualAddress <= nt.OptionalHeader.SizeOfImage
            && position <= nt.OptionalHeader.SizeOfImage - directory.VirtualAddress
            && sizeof(IMAGE_BASE_RELOCATION) <= directory.Size - position, "Invalid helper relocation block.");
        const auto& block = *reinterpret_cast<const IMAGE_BASE_RELOCATION*>(base + directory.VirtualAddress + position);
        Require(block.SizeOfBlock >= sizeof(block) && block.SizeOfBlock <= directory.Size - position
            && (block.SizeOfBlock - sizeof(block)) % sizeof(WORD) == 0, "Invalid helper relocation size.");
        const auto* entries = reinterpret_cast<const WORD*>(&block + 1);
        const auto count = (block.SizeOfBlock - sizeof(block)) / sizeof(WORD);
        for (std::size_t i = 0; i < count; ++i) {
            const auto type = entries[i] >> 12;
            const auto offset = static_cast<std::uint64_t>(block.VirtualAddress) + (entries[i] & 0xfff);
            if (type == IMAGE_REL_BASED_ABSOLUTE || offset < rva || offset >= static_cast<std::uint64_t>(rva) + bytes.size()) continue;
            Require(type == IMAGE_REL_BASED_DIR64 && offset - rva <= bytes.size() - sizeof(std::uintptr_t),
                "Unsupported helper code relocation.");
            std::uintptr_t address;
            std::memcpy(&address, bytes.data() + offset - rva, sizeof(address));
            address += delta;
            std::memcpy(bytes.data() + offset - rva, &address, sizeof(address));
        }
        position += block.SizeOfBlock;
    }
}
}
MappedHelper::MappedHelper(const std::filesystem::path& path)
    : mapped_(LoadLibraryExW(path.c_str(), nullptr, DONT_RESOLVE_DLL_REFERENCES)), bootOffset_(0), image{}, state{}, migration{} {
    Require(mapped_ != nullptr, "Cannot inspect the fixed helper.");
    try {
        image.size = Header(mapped_).OptionalHeader.SizeOfImage;
        const auto entry = [&](const char* name) { return Export(mapped_, name, image.size); };
        bootOffset_ = entry("Bo3EnhancedBoot");
        introAudioBindings=entry("Bo3IntroAudioBindings");
        introAudioHandler=entry("IsCustomIntroPlaying");
        introStartHandler=entry("StartCustomIntro");
        introUpdateHandler=entry("UpdateCustomIntroPlayers");
        originalIntro=entry("NativeOriginalIntro");
        originalIntroUpdate=entry("NativeOriginalIntroUpdate");
        state = {entry("Bo3VmStateBindings"),entry("Bo3VmErrorBindings"),entry("ReadNativeState"),entry("WriteNativeState"),
            entry("InsertNativeStateKey"),entry("ReadStateOrDrop"),entry("WriteStateOrDrop"),entry("VmErrorPrelude"),
            entry("NativeOriginalReader"),entry("NativeOriginalWriter"),entry("NativeOriginalInsert"),entry("NativeOriginalError")};
        migration = {entry("Bo3MigrationBindings"),entry("Bo3MigrationVersionBranches"),entry("Bo3MigrationLoadBindings"),
            entry("Bo3MigrationReentries"),entry("Bo3MigrationFlushBindings"),
            {entry("ReceiveMigrationHeader"),entry("ReceiveMigrationData"),entry("ReceiveMigrationHeaderAck"),
             entry("SendMigrationHeader"),entry("LoadMigrationState"),entry("FlushMigrationState")},
            {entry("MigrationHeaderReentry"),entry("MigrationDataReentry"),entry("MigrationHeaderAckReentry"),
             entry("MigrationSendHeaderReentry"),entry("MigrationLoadReentry"),entry("MigrationFlushReentry")},
            entry("SendHeaderAck"),entry("MigrationVersionGate")};
    } catch (...) { FreeLibrary(mapped_); throw; }
}
MappedHelper::~MappedHelper() { FreeLibrary(mapped_); }
void MappedHelper::Admit(HANDLE process, const std::filesystem::path& file) {
    std::array<HMODULE, 2048> modules{};
    DWORD needed = 0;
    Require(K32EnumProcessModulesEx(process, modules.data(), static_cast<DWORD>(sizeof(modules)), &needed, LIST_MODULES_64BIT)
        && needed <= sizeof(modules) && needed % sizeof(HMODULE) == 0, "Cannot list the stopped child's modules.");
    image.base = 0;
    for (std::size_t i = 0; i < needed / sizeof(HMODULE); ++i) {
        std::array<wchar_t, 32768> path{};
        const auto length = K32GetModuleFileNameExW(process, modules[i], path.data(), static_cast<DWORD>(path.size()));
        Require(length && length < path.size(), "Cannot read a stopped module path.");
        if (std::filesystem::equivalent(file, path.data())) {
            Require(image.base == 0, "The helper has multiple mapped identities.");
            image.base = reinterpret_cast<std::uintptr_t>(modules[i]);
        }
    }
    Require(image.base != 0, "The fixed helper was not loaded before allocation.");
    const auto bootBytes = vm_startup::ReadStopped(process, image.base + bootOffset_, sizeof(BootRecord));
    BootRecord boot{};
    std::memcpy(&boot, bootBytes.data(), sizeof(boot));
    Require(boot.abi == BootAbi && boot.bytes == sizeof(boot) && boot.module == image.base && boot.ready == 1 && boot.reserved == 0,
        "The helper did not publish the exact loader-ready record.");
    const auto& nt = Header(mapped_);
    const auto* section = IMAGE_FIRST_SECTION(&nt);
    unsigned int checked = 0;
    for (unsigned int i = 0; i < nt.FileHeader.NumberOfSections; ++i) {
        if (!(section[i].Characteristics & IMAGE_SCN_MEM_EXECUTE)
            && std::memcmp(section[i].Name, ".pdata", 6) != 0
            && std::memcmp(section[i].Name, ".rdata", 6) != 0) continue;
        const auto rva = section[i].VirtualAddress, size = section[i].Misc.VirtualSize;
        Require(size && size <= image.size && rva <= image.size - size, "A helper code section exceeds its image.");
        const auto* begin = reinterpret_cast<const unsigned char*>(mapped_) + rva;
        std::vector<unsigned char> expected(begin, begin + size);
        RelocateSection(mapped_, nt, image.base, rva, expected);
        auto observed = vm_startup::ReadStopped(process, image.base + rva, size);
        // The Windows loader resolves only the declared IAT. All other read-only bytes must match.
        const auto& iat = nt.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IAT];
        const auto first = std::max<std::uint64_t>(rva, iat.VirtualAddress);
        const auto last = std::min<std::uint64_t>(static_cast<std::uint64_t>(rva) + size,
            static_cast<std::uint64_t>(iat.VirtualAddress) + iat.Size);
        if (first < last) std::copy(expected.begin() + first - rva, expected.begin() + last - rva, observed.begin() + first - rva);
        Require(observed == expected, "The mapped helper code or unwind metadata differs.");
        ++checked;
    }
    Require(checked >= 3, "The helper requires code, unwind tables and read-only metadata.");
}
}
