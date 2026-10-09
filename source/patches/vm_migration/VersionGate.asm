option casemap:none
EXTERN Bo3MigrationBindings:BYTE
EXTERN Bo3MigrationVersionBranches:QWORD
PUBLIC MigrationVersionGate
.code
; At native RVA 12e226, EAX is the header version; no stack/register changes.
MigrationVersionGate PROC
    cmp eax, 3
    je accepted
    cmp eax, DWORD PTR [Bo3MigrationBindings]
    je accepted
    jmp QWORD PTR [Bo3MigrationVersionBranches+8]
accepted:
    jmp QWORD PTR [Bo3MigrationVersionBranches]
MigrationVersionGate ENDP
END
