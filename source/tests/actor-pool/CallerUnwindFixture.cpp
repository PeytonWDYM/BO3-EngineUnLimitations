// Compare complete caller frames through Windows APIs. No game instruction or handler executes.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <array>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

namespace {
void Require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
template<class T> T Read(std::ifstream& input) {
    T value{}; input.read(reinterpret_cast<char*>(&value), sizeof(value));
    Require(static_cast<bool>(input), "Incomplete caller unwind input."); return value;
}
std::vector<unsigned char> Bytes(std::ifstream& input, std::uint32_t size) {
    Require(size <= 131072, "The caller fixture interval exceeds owned storage.");
    std::vector<unsigned char> bytes(size); input.read(reinterpret_cast<char*>(bytes.data()), size);
    Require(static_cast<bool>(input), "Incomplete caller fixture bytes."); return bytes;
}
struct Allocation {
    void* memory = VirtualAlloc(nullptr, 131072, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    ~Allocation() { if (memory) VirtualFree(memory, 0, MEM_RELEASE); }
    unsigned char* data() { Require(memory != nullptr, "Cannot allocate caller fixture storage."); return static_cast<unsigned char*>(memory); }
    DWORD64 base() { return reinterpret_cast<DWORD64>(data()); }
};
struct Registration {
    RUNTIME_FUNCTION function;
    bool active = false;
    ~Registration() { if (active) RtlDeleteFunctionTable(&function); }
    void add(DWORD64 base) {
        active = RtlAddFunctionTable(&function, 1, base) != FALSE;
        Require(active, "Windows refused the caller fixture table.");
    }
    void remove(DWORD64 base) {
        Require(RtlDeleteFunctionTable(&function) != FALSE, "Cannot delete the caller fixture table."); active = false;
        DWORD64 found{};
        Require(RtlLookupFunctionEntry(base, &found, nullptr) == nullptr, "A caller fixture registration survived deletion.");
    }
};
struct Header { std::uint32_t codeBytes, metadataBytes, oldMetadataBytes, contexts, expanded; };
constexpr DWORD64 FakeStack = 0x50000000, ReturnPc = 0x1234567812345678;
constexpr std::array<unsigned int, 8> Nonvolatile{3, 5, 6, 7, 12, 13, 14, 15};
DWORD64& Register(CONTEXT& context, unsigned int index) {
    switch (index) {
    case 0: return context.Rax; case 1: return context.Rcx; case 2: return context.Rdx; case 3: return context.Rbx;
    case 4: return context.Rsp; case 5: return context.Rbp; case 6: return context.Rsi; case 7: return context.Rdi;
    case 8: return context.R8; case 9: return context.R9; case 10: return context.R10; case 11: return context.R11;
    case 12: return context.R12; case 13: return context.R13; case 14: return context.R14; case 15: return context.R15;
    default: throw std::runtime_error("Invalid caller fixture register.");
    }
}
bool Matches(CONTEXT& context, DWORD64 stack) {
    if (context.Rip != ReturnPc || context.Rsp != stack + 0x1F010) return false;
    for (auto index : Nonvolatile) if (Register(context, index) != 0x100000000ull + index) return false;
    for (int index = 6; index < 16; ++index) {
        const M128A expected{0x2233445566778899ull, (static_cast<LONGLONG>(index) << 56) | 0x11};
        if (std::memcmp(&(&context.Xmm0)[index], &expected, sizeof(expected))) return false;
    }
    return true;
}
void Unwind(Allocation& image, RUNTIME_FUNCTION& function, CONTEXT& context) {
    PVOID handlerData{}; DWORD64 frame{};
    RtlVirtualUnwind(UNW_FLAG_NHANDLER, image.base(), context.Rip, &function, &context, &handlerData, &frame, nullptr);
}
std::vector<unsigned char> Mutate(std::vector<unsigned char> prepared, const std::vector<unsigned char>& original, bool allocation) {
    for (unsigned int slot = 0; slot < prepared[2];) {
        const auto position = 4 + slot * 2;
        const auto opcode = prepared[position + 1] & 15;
        const auto extra = (opcode == 1 || opcode == 4 || opcode == 8) ? 1u : 0u;
        if ((allocation && opcode == 1) || (!allocation && (opcode == 4 || opcode == 8)))
            std::memcpy(prepared.data() + position + 2, original.data() + position + 2, 2);
        slot += extra + 1;
    }
    return prepared;
}
}

int wmain(int argc, wchar_t** argv) {
    try {
        Require(argc == 2, "Supply the owned caller-unwind fixture file.");
        std::ifstream input(argv[1], std::ios::binary);
        Require(Read<std::array<char, 8>>(input) == std::array<char, 8>{'B','O','3','C','F','U','W','1'}, "Unknown caller fixture format.");
        Require(Read<std::uint32_t>(input) == 2, "The caller fixture needs stock and expanded frames.");
        unsigned int probes{}, mutations{};
        for (unsigned int variant = 0; variant < 2; ++variant) {
            const auto header = Read<Header>(input);
            Require(header.codeBytes == 1599 && header.metadataBytes == 80 && header.oldMetadataBytes == 80 &&
                    header.contexts == 374 && header.expanded == variant, "Invalid guarded caller fixture extent.");
            const auto code = Bytes(input, header.codeBytes), metadata = Bytes(input, header.metadataBytes), original = Bytes(input, header.oldMetadataBytes);
            Allocation stack, image;
            const auto stackBytes = Bytes(input, 131072); std::memcpy(stack.data(), stackBytes.data(), stackBytes.size());
            std::memcpy(image.data(), code.data(), code.size());
            constexpr unsigned int UnwindOffset = 1600;
            std::memcpy(image.data() + UnwindOffset, metadata.data(), metadata.size());
            image.data()[UnwindOffset] = 1; // Handler omission applies only to this owned comparison.
            Registration table{{0, header.codeBytes, UnwindOffset}}; table.add(image.base());
            for (unsigned int index = 0; index < header.contexts; ++index) {
                const auto control = Read<std::uint32_t>(input);
                Require(control < header.codeBytes, "Caller context lies outside its function.");
                auto gprs = Read<std::array<DWORD64, 16>>(input);
                const auto xmm = Read<std::array<M128A, 16>>(input);
                CONTEXT context{}; context.ContextFlags = CONTEXT_ALL; context.Rip = image.base() + control;
                for (unsigned int reg = 0; reg < 16; ++reg) {
                    auto value = gprs[reg];
                    if (value >= FakeStack && value < FakeStack + 131072) value = stack.base() + value - FakeStack;
                    Register(context, reg) = value;
                }
                std::memcpy(&context.Xmm0, xmm.data(), sizeof(xmm));
                DWORD64 foundBase{};
                Require(RtlLookupFunctionEntry(context.Rip, &foundBase, nullptr) == &table.function && foundBase == image.base(), "Caller runtime lookup differs.");
                auto actual = context; Unwind(image, table.function, actual);
                if (!Matches(actual, stack.base())) {
                    std::cerr << "variant=" << variant << " control=" << std::hex << control << " rsp=" << actual.Rsp - stack.base() << " rip=" << actual.Rip << '\n';
                    throw std::runtime_error("Windows caller unwinding differs from the original return contract.");
                }
                ++probes;
                if (variant && control == 0x9B) {
                    for (bool allocation : {true, false}) {
                        Allocation mutant;
                        std::memcpy(mutant.data(), code.data(), code.size());
                        auto invalidMetadata = Mutate(metadata, original, allocation); invalidMetadata[0] = 1;
                        std::memcpy(mutant.data() + UnwindOffset, invalidMetadata.data(), invalidMetadata.size());
                        auto invalid = context; invalid.Rip = mutant.base() + control;
                        Unwind(mutant, table.function, invalid);
                        Require(!Matches(invalid, stack.base()), "Unchanged caller metadata escaped detection."); ++mutations;
                    }
                }
            }
            table.remove(image.base());
        }
        Require(input.peek() == std::char_traits<char>::eof() && mutations == 2, "Caller fixture coverage or framing differs.");
        std::cout << "{\"passed\":true,\"instructionBoundaryContexts\":" << probes << ",\"metadataMutationsRefused\":" << mutations
                  << ",\"registrationsDeleted\":true,\"handlersExecuted\":false,\"gameWrites\":0}\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
