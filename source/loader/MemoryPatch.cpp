#include "MemoryPatch.h"
#include <algorithm>
#include <iostream>

namespace patch {
struct Protection {
    uintptr_t address;
    SIZE_T length;
    DWORD original;
};

// The caller must hold the target's cooperative safe point for every write.
static void write_record(const Target& target, const Record& record, const std::vector<uint8_t>& bytes) {
    const uintptr_t address = target.base() + static_cast<uintptr_t>(record.rva);
    const auto end = address + bytes.size();
    std::vector<Protection> protections;
    SYSTEM_INFO system_info{};
    GetSystemInfo(&system_info);
    // Allocate rollback state before a page protection can change.
    protections.reserve((bytes.size() + system_info.dwPageSize - 1) / system_info.dwPageSize + 1);
    std::string failure;
    bool protection_failure = false;
    try {
        for (auto cursor = address; cursor < end;) {
            MEMORY_BASIC_INFORMATION region{};
            if (!VirtualQueryEx(target.process(), reinterpret_cast<void*>(cursor), &region, sizeof(region))) throw win_error("VirtualQueryEx");
            const auto length = (std::min)(end, reinterpret_cast<uintptr_t>(region.BaseAddress) + region.RegionSize) - cursor;
            const bool executable = (region.Protect & (PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY)) != 0;
            DWORD old = 0;
            if (!VirtualProtectEx(target.process(), reinterpret_cast<void*>(cursor), length, executable ? PAGE_EXECUTE_READWRITE : PAGE_READWRITE, &old)) throw win_error("VirtualProtectEx");
            protections.push_back({cursor, length, old});
            cursor += length;
        }
        SIZE_T written = 0;
        if (!WriteProcessMemory(target.process(), reinterpret_cast<void*>(address), bytes.data(), bytes.size(), &written)) throw win_error("WriteProcessMemory");
        if (written != bytes.size()) throw std::runtime_error("WriteProcessMemory returned a short write.");
        if (!FlushInstructionCache(target.process(), reinterpret_cast<void*>(address), bytes.size())) throw win_error("FlushInstructionCache");
        if (read_bytes(target.process(), address, bytes.size()) != bytes) throw std::runtime_error("Patch readback differs.");
    } catch (const std::exception& error) {
        failure = error.what();
    }
    for (auto it = protections.rbegin(); it != protections.rend(); ++it) {
        DWORD discarded = 0;
        if (!VirtualProtectEx(target.process(), reinterpret_cast<void*>(it->address), it->length, it->original, &discarded)) {
            protection_failure = true;
            if (!failure.empty()) failure += " ";
            failure += win_error("Restore memory protection").what();
        }
    }
    if (protection_failure) throw IncompleteMutation(failure);
    if (!failure.empty()) throw std::runtime_error(failure);
}

void apply_records(const Target& target, const std::vector<Record>& records) {
    target.verify_bytes(records, false);
    size_t attempted = 0;
    try {
        for (const auto& record : records) {
            // Recheck each record immediately before changing it.
            if (read_bytes(target.process(), target.base() + static_cast<uintptr_t>(record.rva), record.original.size()) != record.original) throw std::runtime_error("Patch original bytes changed at the safe point.");
            ++attempted;
            write_record(target, record, record.replacement);
#ifdef PATCH_LOADER_E2E_DELAY_RECORD_WRITES
            if (attempted == 1) Sleep(250);
#endif
#ifdef PATCH_LOADER_E2E_FAIL_AFTER_FIRST_WRITE
            // This path exists only in the separate native E2E fault executable.
            if (attempted == 1) throw std::runtime_error("E2E fixture failure after the first real memory write.");
#endif
        }
        std::cout << "applied records=" << records.size() << '\n' << std::flush;
    } catch (const std::exception& error) {
        const std::string original_failure = error.what();
        std::string rollback_failure;
        while (attempted > 0) {
            const auto& record = records[--attempted];
            try {
                const auto current = read_bytes(target.process(), target.base() + static_cast<uintptr_t>(record.rva), record.original.size());
                if (current == record.original) continue;
                for (size_t index = 0; index < current.size(); ++index) {
                    if (current[index] != record.original[index] && current[index] != record.replacement[index]) throw std::runtime_error("Rollback conflict. Current bytes have another value.");
                }
                // A short write can leave original and replacement bytes in one record.
                write_record(target, record, record.original);
            } catch (const std::exception& rollback_error) {
                if (!rollback_failure.empty()) rollback_failure += " ";
                rollback_failure += rollback_error.what();
            }
        }
        if (rollback_failure.empty() && dynamic_cast<const IncompleteMutation*>(&error) == nullptr) throw std::runtime_error(original_failure + " rollback complete.");
        throw IncompleteMutation(original_failure + " Rollback incomplete: " + rollback_failure);
    }
}

void remove_records(const Target& target, const std::vector<Record>& records) {
    target.verify_bytes(records, true);
    // Inspect all replacement bytes before removal so a conflict changes nothing.
    std::string failure;
    for (auto it = records.rbegin(); it != records.rend(); ++it) {
        try {
            if (read_bytes(target.process(), target.base() + static_cast<uintptr_t>(it->rva), it->replacement.size()) != it->replacement) throw std::runtime_error("Patch removal conflict. Current bytes changed at the safe point.");
            write_record(target, *it, it->original);
#ifdef PATCH_LOADER_E2E_DELAY_RECORD_WRITES
            Sleep(250);
#endif
        } catch (const std::exception& error) {
            if (!failure.empty()) failure += " ";
            failure += error.what();
        }
    }
    if (!failure.empty()) throw IncompleteMutation("Removal incomplete: " + failure);
    target.verify_bytes(records, false);
    std::cout << "removed records=" << records.size() << '\n' << std::flush;
}
}
