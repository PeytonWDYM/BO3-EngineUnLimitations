option casemap:none
.code
; RCX=authored code, RDX=actual DWORD, R8=expected DWORD, R9=output.
; Table indices start at zero, matching the tiny instruction fingerprints.
RunEvaluator proc
    push rbx
    push rsi
    push rdi
    mov rsi,rcx
    mov rdi,r9
    mov rbx,r8
    xor eax,eax
    xor ecx,ecx
    call rsi
    pushfq
    pop qword ptr [rdi+24]
    mov qword ptr [rdi],rax
    mov qword ptr [rdi+8],rdx
    mov qword ptr [rdi+16],rcx
    pop rdi
    pop rsi
    pop rbx
    ret
RunEvaluator endp
end
