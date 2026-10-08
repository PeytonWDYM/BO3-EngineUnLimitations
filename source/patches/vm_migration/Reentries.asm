option casemap:none
EXTERN Bo3MigrationReentries:QWORD
EXTERN Bo3MigrationFlushBindings:QWORD
PUBLIC MigrationHeaderReentry
PUBLIC MigrationDataReentry
PUBLIC MigrationHeaderAckReentry
PUBLIC MigrationSendHeaderReentry
PUBLIC MigrationLoadReentry
PUBLIC MigrationFlushReentry
.code
MigrationHeaderReentry PROC
    mov [rsp+10h], rsi
    jmp QWORD PTR [Bo3MigrationReentries]
MigrationHeaderReentry ENDP

; Captured first five bytes push RBX, RBP, R14. Continue before PUSH R15.
MigrationDataReentry PROC FRAME
    push rbx
    .pushreg rbx
    push rbp
    .pushreg rbp
    push r14
    .pushreg r14
    .endprolog
    ; A RIP-indirect JMP here looks like an epilogue although pushes remain active.
    ; R11 is volatile and carries no native argument; its register JMP stays body code.
    mov r11, QWORD PTR [Bo3MigrationReentries+8]
    jmp r11
MigrationDataReentry ENDP

; Reproduce the overwritten selected-peer CMP/JNE without register changes.
MigrationHeaderAckReentry PROC FRAME
    sub rsp, 8
    .allocstack 8
    .endprolog
    mov [rsp], rax
    mov rax, QWORD PTR [Bo3MigrationReentries+24]
    cmp ecx, DWORD PTR [rax]
    jne rejectedPeer
    mov rax, [rsp]
    add rsp, 8
    jmp QWORD PTR [Bo3MigrationReentries+16]
rejectedPeer:
    mov rax, [rsp]
    add rsp, 8
    jmp QWORD PTR [Bo3MigrationReentries+48]
MigrationHeaderAckReentry ENDP

MigrationSendHeaderReentry PROC
    mov [rsp+10h], rbx
    jmp QWORD PTR [Bo3MigrationReentries+32]
MigrationSendHeaderReentry ENDP

MigrationLoadReentry PROC
    mov [rsp+8], rbx
    jmp QWORD PTR [Bo3MigrationReentries+40]
MigrationLoadReentry ENDP
MigrationFlushReentry PROC FRAME
    push rdi
    .pushreg rdi
    sub rsp, 20h
    .allocstack 20h
    .endprolog
    mov r11, QWORD PTR [Bo3MigrationFlushBindings+8]
    jmp r11
MigrationFlushReentry ENDP
END
