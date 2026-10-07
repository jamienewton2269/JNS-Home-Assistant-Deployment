using System.Runtime.InteropServices;
using System.Security;
using System.Text;

namespace JnsSshTerminal.Services;

internal static class SecureSecret
{
    public static byte[] ToUtf8Bytes(SecureString secret)
    {
        ArgumentNullException.ThrowIfNull(secret);
        IntPtr pointer = Marshal.SecureStringToGlobalAllocUnicode(secret);
        char[] chars = new char[secret.Length];
        try
        {
            Marshal.Copy(pointer, chars, 0, chars.Length);
            return Encoding.UTF8.GetBytes(chars);
        }
        finally
        {
            Array.Clear(chars, 0, chars.Length);
            Marshal.ZeroFreeGlobalAllocUnicode(pointer);
        }
    }

    public static string ToManagedString(SecureString secret)
    {
        ArgumentNullException.ThrowIfNull(secret);
        IntPtr pointer = Marshal.SecureStringToGlobalAllocUnicode(secret);
        char[] chars = new char[secret.Length];
        try
        {
            Marshal.Copy(pointer, chars, 0, chars.Length);
            return new string(chars);
        }
        finally
        {
            Array.Clear(chars, 0, chars.Length);
            Marshal.ZeroFreeGlobalAllocUnicode(pointer);
        }
    }
}
