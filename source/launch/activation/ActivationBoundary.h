#pragma once
#include "../quiet/QuietBoundary.h"
#include <mmdeviceapi.h>
#include <audiopolicy.h>
#include <memory>

namespace activation {
class Provider {
public:
    virtual ~Provider() = default;
    virtual HRESULT CreateCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output) = 0;
    virtual HRESULT CreateDirectSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer) = 0;
    // Must stop the controlled consumer. The owned fixture throws a test exception.
    [[noreturn]] virtual void Abort(HRESULT code, const char* stage) = 0;
};
class Runtime;
class Boundary {
public:
    explicit Boundary(std::shared_ptr<Provider> provider);
    HRESULT CreateCom(REFCLSID clsid, LPUNKNOWN outer, DWORD context, REFIID iid, void** output);
    HRESULT CreateDirectSound(LPCGUID device, LPDIRECTSOUND8* output, LPUNKNOWN outer);
    bool CanUnload() const;
private:
    std::shared_ptr<Runtime> runtime_;
};
}
