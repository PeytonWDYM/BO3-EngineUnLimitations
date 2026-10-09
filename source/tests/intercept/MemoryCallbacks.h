#pragma once
#include "Consumer.h"
#include "../audio-driver/Callbacks.h"
using CallbackAction = void (*)() noexcept;
Microsoft::WRL::ComPtr<IMMNotificationClient> MemoryEndpoint(const std::shared_ptr<driver_probe::CallbackCounts>&, CallbackAction);
Microsoft::WRL::ComPtr<IAudioSessionEvents> MemorySession(const std::shared_ptr<driver_probe::CallbackCounts>&, CallbackAction,
    std::shared_ptr<bool>, Microsoft::WRL::ComPtr<IAudioClient>);
