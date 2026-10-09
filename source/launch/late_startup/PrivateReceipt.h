#pragma once
#ifdef BO3_EARLY_STARTUP
#include "../early_startup/Coordinator.h"
#elif defined(BO3_INTEGRITY_STARTUP)
#include "../integrity_startup/Coordinator.h"
#elif defined(BO3_BINDINGS_CONTROL)
#include "../bindings_control/Coordinator.h"
#elif defined(BO3_JOB_CONTROL)
#include "../job_control/Receipt.h"
#elif defined(BO3_JOB_STARTUP)
#include "../job_startup/Coordinator.h"
#else
#include "Coordinator.h"
#endif

namespace bo3::late_startup {
class PrivateReceipt {
    std::vector<HANDLE> directories_;
    HANDLE file_=INVALID_HANDLE_VALUE;
    std::filesystem::path path_;
    void Create(const std::filesystem::path&,const OwnedChild&);
public:
    explicit PrivateReceipt(const OwnedChild&);
#ifdef BO3_LATE_OWNED_TEST
    PrivateReceipt(const std::filesystem::path& directory,const OwnedChild&);
#endif
    ~PrivateReceipt();
#ifdef BO3_EARLY_STARTUP
    void Write(const early_startup::Receipt&);
#elif defined(BO3_INTEGRITY_STARTUP)
    void Write(const integrity_startup::Receipt&);
#elif defined(BO3_BINDINGS_CONTROL)
    void Write(const bindings_control::Receipt&);
#elif defined(BO3_JOB_CONTROL)
    void Write(const job_control::Receipt&);
#elif defined(BO3_JOB_STARTUP)
    void Write(const job_startup::Receipt&);
#else
    void Write(const Receipt&);
#endif
#ifdef BO3_LATE_STOCK_CONTROL
    void Write(const ControlReceipt&);
#endif
    const std::filesystem::path& Path() const {return path_;}
    PrivateReceipt(const PrivateReceipt&)=delete;
    PrivateReceipt& operator=(const PrivateReceipt&)=delete;
};
}
