// Map a private candidate as an image without executing its imports or DllMain.
#include <windows.h>
#include <array>
#include <cstdint>
#include <iostream>

int wmain(int argc, wchar_t** argv) {
    if (argc != 2) { return 2; }
    HANDLE file = CreateFileW(argv[1], GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) { return 3; }
    HANDLE mapping = CreateFileMappingW(file, nullptr, PAGE_READONLY | SEC_IMAGE_NO_EXECUTE, 0, 0, nullptr);
    CloseHandle(file);
    if (!mapping) { return 4; }
    auto* image = static_cast<std::byte*>(MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0));
    CloseHandle(mapping);
    if (!image) { return 5; }
    auto* dos = reinterpret_cast<IMAGE_DOS_HEADER*>(image);
    auto* nt = reinterpret_cast<IMAGE_NT_HEADERS64*>(image + dos->e_lfanew);
    auto& directory = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXCEPTION];
    auto* functions = reinterpret_cast<RUNTIME_FUNCTION*>(image + directory.VirtualAddress);
    size_t count = directory.Size / sizeof(RUNTIME_FUNCTION);
    auto* guard = &functions[count - 1];
    bool sorted = true;
    for (size_t index = 1; index < count; ++index) {
        sorted = sorted && functions[index - 1].EndAddress <= functions[index].BeginAddress;
    }
    std::array<uint64_t, 80> stack{};
    uint64_t entry = reinterpret_cast<uint64_t>(&stack[32]);
    constexpr uint64_t returnAddress = 0x12345678;
    stack[32] = returnAddress;
    stack[35] = 0x1111; // Original RBX spill at entry RSP + 0x18.
    stack[36] = 0x2222; // Original RBP spill at entry RSP + 0x20.
    stack[31] = 0x3333; // RSI, RDI, R14 pushes.
    stack[30] = 0x4444;
    stack[29] = 0x5555;
    unsigned passed = 0;
    for (DWORD offset : {0u, 4u, 9u, 16u, 22u, 24u}) {
        CONTEXT context{};
        context.ContextFlags = CONTEXT_FULL;
        context.Rsp = entry - 0x88;
        context.Rip = reinterpret_cast<DWORD64>(image) + guard->BeginAddress + offset;
        context.Rbp = 0x9999;
        void* handlerData = nullptr;
        DWORD64 frame = 0;
        RtlVirtualUnwind(UNW_FLAG_NHANDLER, reinterpret_cast<DWORD64>(image), context.Rip,
            guard, &context, &handlerData, &frame, nullptr);
        if (context.Rip == returnAddress && context.Rsp == entry + 8 && context.Rbx == 0x1111 &&
            context.Rbp == 0x2222 && context.Rsi == 0x3333 && context.Rdi == 0x4444 && context.R14 == 0x5555) {
            ++passed;
        }
    }
    UnmapViewOfFile(image);
    std::cout << "{\"windowsImageMapped\":true,\"entryExecuted\":false,\"functionsSorted\":"
        << (sorted ? "true" : "false") << ",\"unwindCasesPassed\":" << passed << ",\"unwindCases\":6}" << std::endl;
    return sorted && passed == 6 ? 0 : 6;
}
