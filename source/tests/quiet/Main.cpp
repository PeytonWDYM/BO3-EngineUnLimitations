#include "Fixture.h"
#ifndef QUIET_BOUNDARY_BASELINE
#include "../../launch/quiet/QuietBoundary.h"
#endif
#include <iostream>

namespace fixture {
HRESULT RenderBoundary(IAudioRenderClient* sink, IAudioRenderClient** output) {
#ifdef QUIET_BOUNDARY_BASELINE
    *output = sink;
    sink->AddRef();
    return S_OK;
#else
    return quiet::WrapRenderClient(sink, output);
#endif
}
HRESULT SoundBoundary(IDirectSoundBuffer8* sink, IDirectSoundBuffer8** output) {
#ifdef QUIET_BOUNDARY_BASELINE
    *output = sink;
    sink->AddRef();
    return S_OK;
#else
    return quiet::WrapSoundBuffer(sink, output);
#endif
}
}
int main(int argc, char** argv) {
    if (argc != 2) { std::cerr << "Usage: QuietBoundaryFixture.exe report.json\n"; return 2; }
    fixture::Report report;
    fixture::RenderScenarios(report);
    fixture::SoundScenarios(report);
#ifdef QUIET_BOUNDARY_BASELINE
    constexpr bool baseline = true;
#else
    constexpr bool baseline = false;
#endif
    const int result = report.Write(argv[1], baseline);
    std::cout << "Memory-only fixture result " << result << ". Report: " << argv[1] << '\n';
    return result;
}
