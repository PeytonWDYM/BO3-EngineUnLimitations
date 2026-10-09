#pragma once
#include "Probe.h"

namespace driver_probe {
struct CallbackCounts {
    std::atomic<unsigned> live{0};
    std::atomic<unsigned> session{0};
    std::atomic<unsigned> endpoint{0};
};
ComPtr<IAudioSessionEvents> SessionCallback(const std::shared_ptr<CallbackCounts>& counts);
ComPtr<IMMNotificationClient> EndpointCallback(const std::shared_ptr<CallbackCounts>& counts);
}
