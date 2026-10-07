using System.IO;
using System.Text.Json;

namespace JnsSshTerminal.Services;

internal static class JsonStore
{
    private static readonly JsonSerializerOptions Options = new()
    {
        WriteIndented = true,
        PropertyNameCaseInsensitive = true
    };

    public static string DataDirectory { get; } = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "JNS",
        "SshTerminal");

    public static T Load<T>(string fileName, T fallback)
    {
        try
        {
            var path = Path.Combine(DataDirectory, fileName);
            if (!File.Exists(path))
                return fallback;

            return JsonSerializer.Deserialize<T>(File.ReadAllText(path), Options) ?? fallback;
        }
        catch
        {
            return fallback;
        }
    }

    public static void Save<T>(string fileName, T value)
    {
        Directory.CreateDirectory(DataDirectory);
        var path = Path.Combine(DataDirectory, fileName);
        var temp = path + ".tmp";

        File.WriteAllText(temp, JsonSerializer.Serialize(value, Options));
        File.Move(temp, path, true);
    }
}
