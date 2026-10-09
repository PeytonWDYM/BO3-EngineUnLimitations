#include "Probe.h"

namespace driver_probe {
namespace {
struct Sound {
    Trace& trace;
    HWND window=nullptr;
    ComPtr<IDirectSound8> device;
    ComPtr<IDirectSoundBuffer> base;
    ComPtr<IDirectSoundBuffer8> buffer;
    bool started=false,closed=false;
    explicit Sound(Trace& value):trace(value) {}
    bool Close() {
        if(closed) return true;
        closed=true;
        bool complete=true;
        if(started) { const HRESULT result=buffer->Stop(); trace.Call("buffer.Stop",result); complete &= SUCCEEDED(result); }
        buffer.Reset(); base.Reset(); device.Reset();
        if(window) { const BOOL result=DestroyWindow(window); trace.Call("window.Destroy",result ? S_OK : HRESULT_FROM_WIN32(GetLastError())); complete &= result!=FALSE; }
        trace.Fact("cleanup.complete",complete ? "true" : "false"); return complete;
    }
    ~Sound() { Close(); }
};
}
bool RunDirectSound(activation::Boundary& boundary, Trace& trace, const WAVEFORMATEX& format, bool wait) {
    Sound scope(trace);
    try {
        trace.Fact("directsound.format",FormatJson(format));
        const SilenceFormat silence=ValidateFormat(format);
        scope.window=CreateWindowExW(0,L"STATIC",L"Owned silent audio probe",WS_OVERLAPPED,0,0,1,1,nullptr,nullptr,GetModuleHandleW(nullptr),nullptr);
        Check(trace,"window.Create.hidden",scope.window ? S_OK : HRESULT_FROM_WIN32(GetLastError()));
        DWORD process=0; const DWORD thread=GetWindowThreadProcessId(scope.window,&process);
        const bool owned=IsWindow(scope.window) && !IsWindowVisible(scope.window) && process==GetCurrentProcessId() && thread==GetCurrentThreadId();
        trace.Fact("window.valid.hidden.owned",owned ? "true" : "false");
        if(!owned) throw Failure(E_FAIL,"window.ownership");
        Check(trace,"factory.DirectSoundCreate8.default",boundary.CreateDirectSound(nullptr,&scope.device,nullptr));
        Check(trace,"device.SetCooperativeLevel.priority",scope.device->SetCooperativeLevel(scope.window,DSSCL_PRIORITY));
        trace.Publish(scope.device.Get(),"directsound.IUnknown");
        DSBUFFERDESC description{};
        description.dwSize=sizeof(description); description.dwFlags=0x80e8;
        description.dwBufferBytes=format.nAvgBytesPerSec/20;
        description.lpwfxFormat=const_cast<WAVEFORMATEX*>(&format);
        Check(trace,"device.CreateSoundBuffer.base.prepared",scope.device->CreateSoundBuffer(&description,&scope.base,nullptr));
        trace.Publish(scope.base.Get(),"base-buffer.IUnknown");
        Check(trace,"base.QueryInterface.Buffer8",scope.base->QueryInterface(IID_IDirectSoundBuffer8,reinterpret_cast<void**>(scope.buffer.GetAddressOf())));
        trace.Publish(scope.buffer.Get(),"buffer8.IUnknown");
        trace.Fact("identity.base-buffer8",SameIdentity(trace,scope.base.Get(),scope.buffer.Get()) ? "true" : "false");
        DSBCAPS caps{}; caps.dwSize=sizeof(caps);
        Check(trace,"buffer.GetCaps",scope.buffer->GetCaps(&caps));
        if(caps.dwBufferBytes<4u*silence.alignment || caps.dwBufferBytes%silence.alignment) throw Failure(DSERR_BADFORMAT,"buffer.layout");
        LPVOID first=nullptr,second=nullptr; DWORD firstBytes=0,secondBytes=0;
        Check(trace,"buffer.Lock.split",scope.buffer->Lock(caps.dwBufferBytes-2u*silence.alignment,4u*silence.alignment,&first,&firstBytes,&second,&secondBytes,0));
        FillSilence(first,firstBytes,silence); FillSilence(second,secondBytes,silence);
        trace.Fact("split.first.bytes",std::to_string(firstBytes)); trace.Fact("split.second.bytes",std::to_string(secondBytes));
        trace.Fact("split.payload.silenceByte",std::to_string(silence.byte));
        Check(trace,"buffer.Unlock.silent",scope.buffer->Unlock(first,firstBytes,second,secondBytes));
        Check(trace,"buffer.Play.looping",scope.buffer->Play(0,0,DSBPLAY_LOOPING)); scope.started=true;
        if(wait) Sleep(25);
        return scope.Close();
    } catch(const Failure& error) { trace.Call(error.what(),error.code); }
      catch(const std::exception& error) { trace.Fact("owned.exception",Quote(error.what())); }
    scope.Close(); return false;
}
}
