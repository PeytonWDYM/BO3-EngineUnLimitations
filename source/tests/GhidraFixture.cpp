extern "C" int puts(const char *text);
extern "C" __declspec(dllimport) void __stdcall Sleep(unsigned long milliseconds);

extern "C" __declspec(dllexport) __declspec(noinline) int AllocateEntity(int count) {
    if (count >= 32) {
        puts("fixture entity pool exhausted");
        return -1;
    }
    return count + 1;
}

int main(int argc, char **) {
    if (argc == 2) {
        Sleep(90000);
    }
    return AllocateEntity(32) == -1 ? 0 : 1;
}
