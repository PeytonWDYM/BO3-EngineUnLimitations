#include "Callbacks.h"

namespace driver_probe {
namespace {
struct Wasapi {
    Trace& trace;
    std::shared_ptr<CallbackCounts> counts=std::make_shared<CallbackCounts>();
    ComPtr<IMMDeviceEnumerator> enumerator;
    ComPtr<IMMDevice> device;
    ComPtr<IAudioClient> client;
    ComPtr<IAudioRenderClient> render;
    ComPtr<IAudioSessionControl> session;
    ComPtr<IAudioSessionEvents> sessionCallback;
    ComPtr<IMMNotificationClient> endpointCallback;
    HANDLE event=nullptr;
    WAVEFORMATEX* mix=nullptr;
    LPWSTR deviceId=nullptr;
    bool endpointRegistered=false,sessionRegistered=false,started=false,closed=false;
    explicit Wasapi(Trace& value):trace(value) {}
    bool Close() {
        if(closed) return true;
        closed=true;
        bool complete=true;
        if(started) { const HRESULT result=client->Stop(); trace.Call("client.Stop",result); complete &= SUCCEEDED(result); }
        if(sessionRegistered) { const HRESULT result=session->UnregisterAudioSessionNotification(sessionCallback.Get()); trace.Call("session.Unregister",result); complete &= SUCCEEDED(result); }
        if(endpointRegistered) { const HRESULT result=enumerator->UnregisterEndpointNotificationCallback(endpointCallback.Get()); trace.Call("endpoint.Unregister",result); complete &= SUCCEEDED(result); }
        render.Reset(); session.Reset(); client.Reset(); device.Reset(); enumerator.Reset();
        sessionCallback.Reset(); endpointCallback.Reset();
        if(event) { const BOOL result=CloseHandle(event); trace.Call("event.Close",result ? S_OK : HRESULT_FROM_WIN32(GetLastError())); complete &= result!=FALSE; }
        CoTaskMemFree(mix); CoTaskMemFree(deviceId);
        trace.Fact("callbacks.live",std::to_string(counts->live.load()));
        complete &= counts->live.load()==0;
        trace.Fact("cleanup.complete",complete ? "true" : "false");
        return complete;
    }
    ~Wasapi() { Close(); }
};
}
bool RunWasapi(activation::Boundary& boundary, Trace& trace, const WAVEFORMATEX* ownedFormat, bool wait) {
    Wasapi scope(trace);
    try {
        Check(trace,"factory.MMDeviceEnumerator",boundary.CreateCom(__uuidof(MMDeviceEnumerator),nullptr,CLSCTX_ALL,__uuidof(IMMDeviceEnumerator),reinterpret_cast<void**>(scope.enumerator.GetAddressOf())));
        trace.Publish(scope.enumerator.Get(),"enumerator.IUnknown");
        scope.endpointCallback=EndpointCallback(scope.counts);
        Check(trace,"endpoint.Register",scope.enumerator->RegisterEndpointNotificationCallback(scope.endpointCallback.Get()));
        scope.endpointRegistered=true;
        Check(trace,"enumerator.default.eConsole",scope.enumerator->GetDefaultAudioEndpoint(eRender,eConsole,&scope.device));
        trace.Publish(scope.device.Get(),"device.IUnknown");
        Check(trace,"device.GetId",scope.device->GetId(&scope.deviceId));
        trace.Fact("endpoint.id",Quote(Utf8(scope.deviceId)));
        Check(trace,"device.Activate.IAudioClient",scope.device->Activate(__uuidof(IAudioClient),CLSCTX_ALL,nullptr,reinterpret_cast<void**>(scope.client.GetAddressOf())));
        trace.Publish(scope.client.Get(),"client.IUnknown");
        Check(trace,"client.GetMixFormat",scope.client->GetMixFormat(&scope.mix));
        const WAVEFORMATEX& format=ownedFormat ? *ownedFormat : *scope.mix;
        trace.Fact("format",FormatJson(format));
        const SilenceFormat silence=ValidateFormat(format);
        scope.event=CreateEventW(nullptr,FALSE,FALSE,nullptr);
        Check(trace,"event.Create",scope.event ? S_OK : HRESULT_FROM_WIN32(GetLastError()));
        Check(trace,"client.Initialize.shared.event.nopersist",scope.client->Initialize(AUDCLNT_SHAREMODE_SHARED,AUDCLNT_STREAMFLAGS_EVENTCALLBACK|AUDCLNT_STREAMFLAGS_NOPERSIST,250000,0,&format,nullptr));
        Check(trace,"client.SetEventHandle",scope.client->SetEventHandle(scope.event));
        UINT32 frames=0;
        Check(trace,"client.GetBufferSize",scope.client->GetBufferSize(&frames));
        if(!frames || static_cast<ULONGLONG>(frames)*silence.alignment>SIZE_MAX) throw Failure(E_INVALIDARG,"buffer.frame-count");
        Check(trace,"client.GetService.render",scope.client->GetService(__uuidof(IAudioRenderClient),reinterpret_cast<void**>(scope.render.GetAddressOf())));
        trace.Publish(scope.render.Get(),"render.IUnknown");
        Check(trace,"client.GetService.session",scope.client->GetService(__uuidof(IAudioSessionControl),reinterpret_cast<void**>(scope.session.GetAddressOf())));
        trace.Publish(scope.session.Get(),"session.IUnknown");
        trace.Fact("identity.client-render",SameIdentity(trace,scope.client.Get(),scope.render.Get()) ? "true" : "false");
        trace.Fact("identity.client-session",SameIdentity(trace,scope.client.Get(),scope.session.Get()) ? "true" : "false");
        scope.sessionCallback=SessionCallback(scope.counts);
        Check(trace,"session.Register",scope.session->RegisterAudioSessionNotification(scope.sessionCallback.Get()));
        scope.sessionRegistered=true;
        BYTE* data=nullptr;
        Check(trace,"render.GetBuffer.first",scope.render->GetBuffer(frames,&data));
        FillSilence(data,static_cast<size_t>(frames)*silence.alignment,silence);
        trace.Fact("first.payload.silenceByte",std::to_string(silence.byte));
        trace.Fact("first.payload.bytes",std::to_string(static_cast<size_t>(frames)*silence.alignment));
        Check(trace,"render.ReleaseBuffer.first.SILENT",scope.render->ReleaseBuffer(frames,AUDCLNT_BUFFERFLAGS_SILENT));
        Check(trace,"client.Start",scope.client->Start());
        scope.started=true;
        if(wait) { const DWORD result=WaitForSingleObject(scope.event,50); trace.Fact("event.wait",std::to_string(result)); if(result==WAIT_FAILED) throw Failure(HRESULT_FROM_WIN32(GetLastError()),"event.Wait"); }
        return scope.Close();
    } catch(const Failure& error) { trace.Call(error.what(),error.code); }
      catch(const std::exception& error) { trace.Fact("owned.exception",Quote(error.what())); }
    scope.Close(); return false;
}
}
