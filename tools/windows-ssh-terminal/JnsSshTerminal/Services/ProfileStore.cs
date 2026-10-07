using JnsSshTerminal.Models;

namespace JnsSshTerminal.Services;

public sealed class ProfileStore
{
    private const string FileName = "hosts.json";

    public List<HostProfile> Load() =>
        JsonStore.Load(FileName, new List<HostProfile>())
            .OrderBy(p => p.Name, StringComparer.OrdinalIgnoreCase)
            .ToList();

    public void Save(IEnumerable<HostProfile> profiles) =>
        JsonStore.Save(FileName, profiles.OrderBy(p => p.Name, StringComparer.OrdinalIgnoreCase).ToList());
}
