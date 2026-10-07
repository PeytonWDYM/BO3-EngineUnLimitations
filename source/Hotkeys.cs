using System.Runtime.InteropServices;

// Read only the recorder's Ctrl+Shift+function-key combinations.
public static class RecorderHotkeys
{
    [DllImport("user32.dll")]
    private static extern short GetAsyncKeyState(int virtualKey);

    public static bool IsDown(int virtualKey)
    {
        return (GetAsyncKeyState(0x11) & 0x8000) != 0
            && (GetAsyncKeyState(0x10) & 0x8000) != 0
            && (GetAsyncKeyState(virtualKey) & 0x8000) != 0;
    }
}
