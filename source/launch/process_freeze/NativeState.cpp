#include "NativeState.h"
#include <stdexcept>

namespace process_freeze {
NativeApi::NativeApi() {
    const auto module = GetModuleHandleW(L"ntdll.dll");
    create = reinterpret_cast<CreateState>(GetProcAddress(module, "NtCreateProcessStateChange"));
    change = reinterpret_cast<ChangeState>(GetProcAddress(module, "NtChangeProcessState"));
    thread = reinterpret_cast<CreateThread>(GetProcAddress(module, "NtCreateThreadEx"));
    if (!create || !change || !thread) throw std::runtime_error("Required native state export is absent.");
}
Identity ReadIdentity(HANDLE process) {
    FILETIME creation{}, exit{}, kernel{}, user{};
    wchar_t image[32768]{};
    DWORD length = static_cast<DWORD>(std::size(image));
    if (!GetProcessTimes(process, &creation, &exit, &kernel, &user) ||
        !QueryFullProcessImageNameW(process, 0, image, &length))
        throw std::runtime_error("Cannot read owned process identity.");
    const auto created = (static_cast<unsigned long long>(creation.dwHighDateTime) << 32) | creation.dwLowDateTime;
    return {GetProcessId(process), created, std::wstring(image, length)};
}
void RequireIdentity(HANDLE process, const Identity& expected) {
    const auto actual = ReadIdentity(process);
    if (actual.pid != expected.pid || actual.created != expected.created || actual.image != expected.image)
        throw std::runtime_error("Owned process identity differs.");
}
State::State(const NativeApi& api, HANDLE process, Identity identity)
    : api_(api), process_(process), identity_(std::move(identity)) {
    RequireIdentity(process_, identity_);
    const auto status = api_.create(&state_, 1, nullptr, process_, 0);
    if (status < 0) throw std::runtime_error("Native state object creation failed.");
}
State::~State() { Close(); }
NTSTATUS State::Change(ULONG action) {
    RequireIdentity(process_, identity_);
    return api_.change(state_, process_, action, nullptr, 0, 0);
}
void State::Close() {
    if (state_) { CloseHandle(state_); state_ = nullptr; }
}
}
