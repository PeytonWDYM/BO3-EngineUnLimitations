#pragma once
#include "Coordinator.h"

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
    void Write(const Receipt&);
    const std::filesystem::path& Path() const {return path_;}
    PrivateReceipt(const PrivateReceipt&)=delete;
    PrivateReceipt& operator=(const PrivateReceipt&)=delete;
};
}
