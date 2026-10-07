using Renci.SshNet;
using System.Buffers.Binary;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace JnsSshTerminal.Services;

public sealed record GeneratedSshKey(string PrivateKeyPath, string PublicKeyPath, string PublicKey);

public sealed class SecureKeyStore
{
    private const uint CryptProtectUiForbidden = 0x1;
    private static readonly byte[] Entropy =
        SHA256.HashData(Encoding.UTF8.GetBytes("JNS.SshTerminal.SecureKey.v1"));

    public string KeyDirectory { get; } = Path.Combine(JsonStore.DataDirectory, "keys");

    public bool IsManagedKey(string path) =>
        !string.IsNullOrWhiteSpace(path) &&
        path.EndsWith(".jnskey", StringComparison.OrdinalIgnoreCase);

    public GeneratedSshKey GenerateKey()
    {
        Directory.CreateDirectory(KeyDirectory);
        string stem = $"jns-ecdsa-p256-{DateTime.UtcNow:yyyyMMdd-HHmmss}-{Guid.NewGuid():N}"[..48];
        string privatePath = Path.Combine(KeyDirectory, stem + ".jnskey");
        string publicPath = Path.Combine(KeyDirectory, stem + ".pub");
        byte[]? pkcs8 = null;
        byte[]? pemBytes = null;
        byte[]? protectedBytes = null;
        try
        {
            using var ecdsa = ECDsa.Create(ECCurve.NamedCurves.nistP256);
            pkcs8 = ecdsa.ExportPkcs8PrivateKey();
            string pem = ToPem("PRIVATE KEY", pkcs8);
            pemBytes = Encoding.ASCII.GetBytes(pem);
            pem = string.Empty;
            protectedBytes = Protect(pemBytes);
            File.WriteAllBytes(privatePath, protectedBytes);

            string publicKey = BuildOpenSshPublicKey(ecdsa.ExportParameters(false));
            File.WriteAllText(publicPath, publicKey + Environment.NewLine, new UTF8Encoding(false));
            return new GeneratedSshKey(privatePath, publicPath, publicKey);
        }
        catch
        {
            TryDelete(privatePath);
            TryDelete(publicPath);
            throw;
        }
        finally
        {
            if (pkcs8 is not null) CryptographicOperations.ZeroMemory(pkcs8);
            if (pemBytes is not null) CryptographicOperations.ZeroMemory(pemBytes);
            if (protectedBytes is not null) CryptographicOperations.ZeroMemory(protectedBytes);
        }
    }

    public PrivateKeyFile OpenPrivateKey(string path)
    {
        if (!IsManagedKey(path))
            throw new InvalidOperationException("The selected key is not a JNS protected key.");
        byte[] protectedBytes = File.ReadAllBytes(path);
        byte[]? plainBytes = null;
        try
        {
            plainBytes = Unprotect(protectedBytes);
            using var stream = new MemoryStream(plainBytes, writable:false);
            return new PrivateKeyFile(stream);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(protectedBytes);
            if (plainBytes is not null) CryptographicOperations.ZeroMemory(plainBytes);
        }
    }

    public bool TryReadPublicKey(string privateKeyPath, out string publicKey)
    {
        publicKey = "";
        if (string.IsNullOrWhiteSpace(privateKeyPath)) return false;
        string publicPath = IsManagedKey(privateKeyPath)
            ? Path.ChangeExtension(privateKeyPath, ".pub")
            : privateKeyPath + ".pub";
        if (!File.Exists(publicPath)) return false;
        publicKey = File.ReadAllText(publicPath).Trim();
        return !string.IsNullOrWhiteSpace(publicKey);
    }

    private static string ToPem(string label, byte[] der)
    {
        string base64 = Convert.ToBase64String(der);
        var builder = new StringBuilder();
        builder.Append("-----BEGIN ").Append(label).AppendLine("-----");
        for (int i=0; i<base64.Length; i+=64)
            builder.AppendLine(base64.Substring(i, Math.Min(64, base64.Length-i)));
        builder.Append("-----END ").Append(label).AppendLine("-----");
        return builder.ToString();
    }

    private static string BuildOpenSshPublicKey(ECParameters parameters)
    {
        const string algorithm="ecdsa-sha2-nistp256";
        const string curve="nistp256";
        byte[] x=PadCoordinate(parameters.Q.X,32);
        byte[] y=PadCoordinate(parameters.Q.Y,32);
        byte[] point=new byte[65];
        point[0]=0x04;
        Buffer.BlockCopy(x,0,point,1,32);
        Buffer.BlockCopy(y,0,point,33,32);
        try
        {
            using var blob=new MemoryStream();
            WriteSshString(blob,Encoding.ASCII.GetBytes(algorithm));
            WriteSshString(blob,Encoding.ASCII.GetBytes(curve));
            WriteSshString(blob,point);
            string comment=$"JNS-SshTerminal@{Environment.MachineName}";
            return $"{algorithm} {Convert.ToBase64String(blob.ToArray())} {comment}";
        }
        finally
        {
            CryptographicOperations.ZeroMemory(x);
            CryptographicOperations.ZeroMemory(y);
            CryptographicOperations.ZeroMemory(point);
        }
    }

    private static byte[] PadCoordinate(byte[]? coordinate,int length)
    {
        if(coordinate is null) throw new CryptographicException("ECDSA public coordinate missing.");
        if(coordinate.Length==length) return coordinate.ToArray();
        if(coordinate.Length>length) return coordinate[^length..];
        byte[] padded=new byte[length];
        Buffer.BlockCopy(coordinate,0,padded,length-coordinate.Length,coordinate.Length);
        return padded;
    }

    private static void WriteSshString(Stream stream,byte[] value)
    {
        Span<byte> length=stackalloc byte[4];
        BinaryPrimitives.WriteUInt32BigEndian(length,(uint)value.Length);
        stream.Write(length);
        stream.Write(value);
    }

    private static byte[] Protect(byte[] plain)=>CryptData(plain,true);
    private static byte[] Unprotect(byte[] encrypted)=>CryptData(encrypted,false);

    private static byte[] CryptData(byte[] input,bool protect)
    {
        IntPtr inputPointer=IntPtr.Zero;
        IntPtr entropyPointer=IntPtr.Zero;
        DataBlob output=default;
        try
        {
            inputPointer=Marshal.AllocHGlobal(input.Length);
            Marshal.Copy(input,0,inputPointer,input.Length);
            entropyPointer=Marshal.AllocHGlobal(Entropy.Length);
            Marshal.Copy(Entropy,0,entropyPointer,Entropy.Length);
            var inputBlob=new DataBlob{Size=input.Length,Data=inputPointer};
            var entropyBlob=new DataBlob{Size=Entropy.Length,Data=entropyPointer};
            bool success=protect
                ? CryptProtectData(ref inputBlob,null,ref entropyBlob,IntPtr.Zero,IntPtr.Zero,CryptProtectUiForbidden,out output)
                : CryptUnprotectData(ref inputBlob,IntPtr.Zero,ref entropyBlob,IntPtr.Zero,IntPtr.Zero,CryptProtectUiForbidden,out output);
            if(!success) throw new Win32Exception(Marshal.GetLastWin32Error());
            byte[] result=new byte[output.Size];
            Marshal.Copy(output.Data,result,0,output.Size);
            return result;
        }
        finally
        {
            ZeroAndFree(inputPointer,input.Length);
            ZeroAndFree(entropyPointer,Entropy.Length);
            if(output.Data!=IntPtr.Zero)
            {
                ZeroUnmanaged(output.Data,output.Size);
                LocalFree(output.Data);
            }
        }
    }

    private static void ZeroAndFree(IntPtr pointer,int length)
    {
        if(pointer==IntPtr.Zero) return;
        ZeroUnmanaged(pointer,length);
        Marshal.FreeHGlobal(pointer);
    }

    private static void ZeroUnmanaged(IntPtr pointer,int length)
    {
        if(pointer==IntPtr.Zero||length<=0) return;
        byte[] zeros=new byte[length];
        try{Marshal.Copy(zeros,0,pointer,length);}
        finally{CryptographicOperations.ZeroMemory(zeros);}
    }

    private static void TryDelete(string path)
    {
        try{if(File.Exists(path)) File.Delete(path);}catch{}
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct DataBlob{public int Size;public IntPtr Data;}

    [DllImport("Crypt32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    [return:MarshalAs(UnmanagedType.Bool)]
    private static extern bool CryptProtectData(ref DataBlob dataIn,string? description,ref DataBlob optionalEntropy,IntPtr reserved,IntPtr promptStruct,uint flags,out DataBlob dataOut);

    [DllImport("Crypt32.dll",CharSet=CharSet.Unicode,SetLastError=true)]
    [return:MarshalAs(UnmanagedType.Bool)]
    private static extern bool CryptUnprotectData(ref DataBlob dataIn,IntPtr description,ref DataBlob optionalEntropy,IntPtr reserved,IntPtr promptStruct,uint flags,out DataBlob dataOut);

    [DllImport("Kernel32.dll",SetLastError=true)]
    private static extern IntPtr LocalFree(IntPtr memory);
}
