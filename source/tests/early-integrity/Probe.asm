.code
Probe PROC
    push rbx
    push rbp
    push rsi
    push rdi
    push r12
    push r13
    push r14
    push r15
    sub rsp,80h
    mov [rsp],rcx
    mov [rsp+8],r8
    mov [rsp+16],r9
    mov rbp,rdx
    mov rax,0a5a55a5ah
    xor ecx,ecx
    mov rdx,[rbp+240]
    mov rbx,1111h
    mov rsi,2222h
    mov rdi,3333h
    mov r8,4444h
    mov r9,5555h
    mov r10,6666h
    mov r11,7777h
    mov r12,8888h
    mov r13,9999h
    mov r14,0aaaah
    mov r15,0bbbbh
    push qword ptr [rsp+16]
    popfq
    call qword ptr [rsp]
    mov [rsp+24],r10
    mov r10,[rsp+8]
    mov [r10],rax
    mov [r10+8],rbx
    mov [r10+16],rcx
    mov [r10+24],rdx
    mov [r10+32],rbp
    mov [r10+48],rsi
    mov [r10+56],rdi
    mov [r10+64],r8
    mov [r10+72],r9
    mov rax,[rsp+24]
    mov [r10+80],rax
    mov [r10+88],r11
    mov [r10+96],r12
    mov [r10+104],r13
    mov [r10+112],r14
    mov [r10+120],r15
    lea rax,[rsp]
    mov [r10+40],rax
    pushfq
    pop rax
    mov [r10+128],rax
    mov rax,rsp
    add rsp,80h
    pop r15
    pop r14
    pop r13
    pop r12
    pop rdi
    pop rsi
    pop rbp
    pop rbx
    ret
Probe ENDP
END
