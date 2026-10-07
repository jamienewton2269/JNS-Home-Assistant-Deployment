using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Cryptography;

namespace JnsSshTerminal.Services;

public sealed class WindowsCredentialStore
{
    private const uint CredTypeGeneric = 1;
    private const uint CredPersistLocalMachine = 2;
    private const int ErrorNotFound = 1168;
    private const string TargetPrefix = "JNS.SshTerminal/SSH/";

    public bool HasPassword(string host, int port, string username)
    {
        if (!CredReadW(Target(host, port, username), CredTypeGeneric, 0, out IntPtr pointer))
            return false;
        CredFree(pointer);
        return true;
    }

    public byte[]? ReadPassword(string host, int port, string username)
    {
        if (!CredReadW(Target(host, port, username), CredTypeGeneric, 0, out IntPtr pointer))
            return null;
        try
        {
            var credential = Marshal.PtrToStructure<Credential>(pointer);
            if (credential.CredentialBlob == IntPtr.Zero || credential.CredentialBlobSize == 0)
                return Array.Empty<byte>();
            byte[] secret = new byte[credential.CredentialBlobSize];
            Marshal.Copy(credential.CredentialBlob, secret, 0, secret.Length);
            return secret;
        }
        finally { CredFree(pointer); }
    }

    public void SavePassword(string host, int port, string username, byte[] passwordUtf8)
    {
        ArgumentNullException.ThrowIfNull(passwordUtf8);
        if (passwordUtf8.Length == 0)
            throw new ArgumentException("Password must not be empty.", nameof(passwordUtf8));
        IntPtr blob = Marshal.AllocHGlobal(passwordUtf8.Length);
        try
        {
            Marshal.Copy(passwordUtf8, 0, blob, passwordUtf8.Length);
            var credential = new Credential
            {
                Type = CredTypeGeneric,
                TargetName = Target(host, port, username),
                CredentialBlobSize = (uint)passwordUtf8.Length,
                CredentialBlob = blob,
                Persist = CredPersistLocalMachine,
                UserName = username
            };
            if (!CredWriteW(ref credential, 0))
                throw new Win32Exception(Marshal.GetLastWin32Error());
        }
        finally
        {
            ZeroUnmanaged(blob, passwordUtf8.Length);
            Marshal.FreeHGlobal(blob);
        }
    }

    public void DeletePassword(string host, int port, string username)
    {
        if (CredDeleteW(Target(host, port, username), CredTypeGeneric, 0))
            return;
        int error = Marshal.GetLastWin32Error();
        if (error != ErrorNotFound)
            throw new Win32Exception(error);
    }

    private static string Target(string host, int port, string username) =>
        $"{TargetPrefix}{username.Trim()}@{host.Trim().ToLowerInvariant()}:{port}";

    private static void ZeroUnmanaged(IntPtr pointer, int length)
    {
        if (pointer == IntPtr.Zero || length <= 0) return;
        byte[] zeros = new byte[length];
        try { Marshal.Copy(zeros, 0, pointer, length); }
        finally { CryptographicOperations.ZeroMemory(zeros); }
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct Credential
    {
        public uint Flags;
        public uint Type;
        [MarshalAs(UnmanagedType.LPWStr)] public string? TargetName;
        [MarshalAs(UnmanagedType.LPWStr)] public string? Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public uint CredentialBlobSize;
        public IntPtr CredentialBlob;
        public uint Persist;
        public uint AttributeCount;
        public IntPtr Attributes;
        [MarshalAs(UnmanagedType.LPWStr)] public string? TargetAlias;
        [MarshalAs(UnmanagedType.LPWStr)] public string? UserName;
    }

    [DllImport("Advapi32.dll", EntryPoint="CredWriteW", CharSet=CharSet.Unicode, SetLastError=true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CredWriteW(ref Credential userCredential, uint flags);

    [DllImport("Advapi32.dll", EntryPoint="CredReadW", CharSet=CharSet.Unicode, SetLastError=true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CredReadW(string target, uint type, uint reservedFlag, out IntPtr credentialPtr);

    [DllImport("Advapi32.dll", EntryPoint="CredDeleteW", CharSet=CharSet.Unicode, SetLastError=true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CredDeleteW(string target, uint type, uint flags);

    [DllImport("Advapi32.dll")]
    private static extern void CredFree(IntPtr buffer);
}
