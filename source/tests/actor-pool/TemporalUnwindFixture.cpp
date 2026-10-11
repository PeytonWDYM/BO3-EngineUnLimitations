// Check relocated temporal frames through Windows. This fixture never calls game code.
#include <Windows.h>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
void Require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
template<class T> T Read(std::ifstream& input) {
    T result{}; input.read(reinterpret_cast<char*>(&result), sizeof(result));
    Require(static_cast<bool>(input), "Incomplete temporal frame input."); return result;
}
std::vector<unsigned char> Bytes(std::ifstream& input, std::uint32_t size) {
    Require(size <= 131072, "Temporal fixture interval exceeds owned storage.");
    std::vector<unsigned char> bytes(size); input.read(reinterpret_cast<char*>(bytes.data()), size);
    Require(static_cast<bool>(input), "Incomplete temporal fixture bytes."); return bytes;
}
struct Allocation {
    void* memory = VirtualAlloc(nullptr, 131072, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    ~Allocation() { if (memory) VirtualFree(memory, 0, MEM_RELEASE); }
    unsigned char* data() { Require(memory != nullptr, "Cannot allocate temporal fixture storage."); return static_cast<unsigned char*>(memory); }
    DWORD64 base() { return reinterpret_cast<DWORD64>(data()); }
};
struct Registration {
    std::array<RUNTIME_FUNCTION, 3> functions{};
    bool active{};
    ~Registration() { if (active) RtlDeleteFunctionTable(functions.data()); }
    void add(DWORD64 base) { Require(RtlAddFunctionTable(functions.data(), 3, base) != FALSE, "Cannot register temporal frames."); active = true; }
    void remove() { Require(RtlDeleteFunctionTable(functions.data()) != FALSE, "Cannot delete temporal frames."); active = false; }
};
struct Header { std::uint32_t imageBytes, frames, contexts, expanded; };
DWORD64& Register(CONTEXT& context, unsigned int index) {
    switch (index) {
    case 0:return context.Rax; case 1:return context.Rcx; case 2:return context.Rdx; case 3:return context.Rbx;
    case 4:return context.Rsp; case 5:return context.Rbp; case 6:return context.Rsi; case 7:return context.Rdi;
    case 8:return context.R8; case 9:return context.R9; case 10:return context.R10; case 11:return context.R11;
    case 12:return context.R12; case 13:return context.R13; case 14:return context.R14; default:return context.R15;
    }
}
bool Matches(CONTEXT& context, DWORD64 stack) {
    if (context.Rip != 0x1234567812345678ull || context.Rsp != stack + 0x1F010) return false;
    for (unsigned int index : {3u,5u,6u,7u,12u,13u,14u,15u})
        if (Register(context,index) != 0x100000000ull + index) return false;
    for (unsigned int index = 6; index < 16; ++index) {
        const M128A expected{0x2233445566778899ull, (static_cast<LONGLONG>(index) << 56) | 0x11};
        if (std::memcmp(&(&context.Xmm0)[index], &expected, sizeof(expected))) return false;
    }
    return true;
}
void Unwind(Allocation& image, RUNTIME_FUNCTION& function, CONTEXT& context) {
    PVOID data{}; DWORD64 frame{};
    RtlVirtualUnwind(UNW_FLAG_NHANDLER, image.base(), context.Rip, &function, &context, &data, &frame, nullptr);
}
}

int wmain(int argc, wchar_t** argv) {
    try {
        Require(argc == 2, "Supply the owned temporal frame fixture.");
        std::ifstream input(argv[1], std::ios::binary);
        Require(Read<std::array<char,8>>(input) == std::array<char,8>{'B','O','3','T','F','U','W','1'}, "Unknown temporal frame fixture.");
        Require(Read<std::uint32_t>(input) == 4, "Expected stock and expanded producer/rewind frames.");
        unsigned int contexts{}, mutations{}, saveMutations{}, tables{};
        for (unsigned int variant = 0; variant < 4; ++variant) {
            const auto header = Read<Header>(input);
            Require(header.imageBytes < 65536 && header.frames == 3 && header.contexts > 0 && header.contexts < 512 && header.expanded == variant % 2,
                    "Invalid temporal fixture header.");
            const auto bytes = Bytes(input, header.imageBytes);
            Allocation image, stack; std::memcpy(image.data(), bytes.data(), bytes.size());
            Registration registration;
            for (auto& function : registration.functions) function = Read<RUNTIME_FUNCTION>(input);
            const auto stackBytes = Bytes(input, 131072); std::memcpy(stack.data(), stackBytes.data(), stackBytes.size());
            registration.add(image.base());
            bool saveChecked{};
            for (unsigned int index = 0; index < header.contexts; ++index) {
                const auto control = Read<std::uint32_t>(input);
                auto gprs = Read<std::array<DWORD64,16>>(input);
                const auto xmm = Read<std::array<M128A,16>>(input);
                CONTEXT context{}; context.ContextFlags = CONTEXT_ALL; context.Rip = image.base() + control;
                for (unsigned int reg = 0; reg < 16; ++reg) {
                    auto value = gprs[reg];
                    if (value >= 0x50000000 && value < 0x50020000) value = stack.base() + value - 0x50000000;
                    Register(context,reg) = value;
                }
                std::memcpy(&context.Xmm0, xmm.data(), sizeof(xmm));
                DWORD64 foundBase{}; auto* function = RtlLookupFunctionEntry(context.Rip, &foundBase, nullptr);
                Require(function != nullptr && foundBase == image.base(), "Temporal runtime lookup differs.");
                auto actual = context; Unwind(image, *function, actual);
                if (!Matches(actual, stack.base())) {
                    std::cerr << "variant=" << variant << " control=" << std::hex << control << " rsp=" << actual.Rsp - stack.base() << '\n';
                    throw std::runtime_error("Temporal Windows unwind differs from the native return contract.");
                }
                ++contexts;
                // A complete body context must fail when its root retains the stock allocation.
                if (header.expanded && index == header.contexts / 2) {
                    Allocation invalid; std::memcpy(invalid.data(), bytes.data(), bytes.size());
                    const auto offset = registration.functions[0].UnwindData;
                    auto* metadata = invalid.data() + offset;
                    bool changed{};
                    for (unsigned int slot = 0; slot < metadata[2];) {
                        const auto position = 4 + slot * 2;
                        const auto opcode = metadata[position+1] & 15;
                        if (opcode == 1) {
                            const std::uint16_t old = variant < 2 ? 33 : 215;
                            std::memcpy(metadata + position + 2, &old, 2); changed = true; break;
                        }
                        slot += opcode == 4 || opcode == 8 ? 2u : 1u;
                    }
                    Require(changed, "Missing allocation mutation site.");
                    auto stale = context; stale.Rip = invalid.base() + control;
                    Unwind(invalid, *function, stale);
                    Require(!Matches(stale, stack.base()), "Stale temporal allocation escaped refusal."); ++mutations;
                }
                const auto& late = registration.functions[1];
                if (header.expanded && !saveChecked && function == &registration.functions[1]
                    && control >= late.BeginAddress + bytes[late.UnwindData+1]) {
                    Allocation invalid; std::memcpy(invalid.data(), bytes.data(), bytes.size());
                    const auto root = registration.functions[0].UnwindData;
                    Require((bytes[root+5] & 15) == 1, "The root allocation encoding differs.");
                    std::uint16_t allocation{}; std::memcpy(&allocation, bytes.data()+root+6, 2);
                    const unsigned int growth = allocation - (variant < 2 ? 33u : 215u);
                    auto* metadata = invalid.data()+late.UnwindData;
                    unsigned int changed{};
                    for (unsigned int slot = 0; slot < metadata[2];) {
                        const auto position = 4+slot*2;
                        const auto opcode = metadata[position+1] & 15;
                        Require(opcode == 4, "The late-save fragment has an unknown operation.");
                        std::uint16_t value{}; std::memcpy(&value, metadata+position+2, 2);
                        Require(value >= growth, "The late-save offset cannot retain its stock value.");
                        value = static_cast<std::uint16_t>(value-growth);
                        std::memcpy(metadata+position+2, &value, 2); ++changed; slot += 2;
                    }
                    Require(changed != 0, "Missing late-save mutation site.");
                    auto stale = context; stale.Rip = invalid.base()+control;
                    Unwind(invalid,*function,stale);
                    Require(!Matches(stale,stack.base()), "Stale register-save offsets escaped refusal.");
                    saveChecked = true; ++saveMutations;
                }
            }
            registration.remove(); ++tables;
        }
        Require(input.peek() == std::char_traits<char>::eof() && mutations == 2 && saveMutations == 2, "Temporal fixture coverage differs.");
        std::cout << "{\"passed\":true,\"contexts\":" << contexts << ",\"allocationMutationsRefused\":" << mutations
                  << ",\"saveMutationsRefused\":" << saveMutations << ",\"functionTablesDeleted\":" << tables
                  << ",\"handlersExecuted\":false,\"gameWrites\":0}\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
