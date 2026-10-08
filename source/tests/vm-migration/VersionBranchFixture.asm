option casemap:none
EXTERN MigrationVersionGate:PROC
PUBLIC TestMigrationVersion
.code
TestMigrationVersion PROC
    mov eax, ecx
    jmp MigrationVersionGate
TestMigrationVersion ENDP
END
