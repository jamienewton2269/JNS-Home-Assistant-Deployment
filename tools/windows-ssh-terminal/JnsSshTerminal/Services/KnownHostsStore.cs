namespace JnsSshTerminal.Services;

public sealed class KnownHostEntry
{
    public string Endpoint { get; set; } = "";
    public string Algorithm { get; set; } = "";
    public string FingerprintSha256 { get; set; } = "";
    public DateTimeOffset FirstSeen { get; set; } = DateTimeOffset.Now;
}

public sealed class KnownHostsStore
{
    private const string FileName = "known-hosts.json";
    private readonly List<KnownHostEntry> _entries;

    public KnownHostsStore()
    {
        _entries = JsonStore.Load(FileName, new List<KnownHostEntry>());
    }

    public KnownHostEntry? Find(string endpoint) =>
        _entries.FirstOrDefault(e =>
            string.Equals(e.Endpoint, endpoint, StringComparison.OrdinalIgnoreCase));

    public void Trust(string endpoint, string algorithm, string fingerprintSha256)
    {
        var existing = Find(endpoint);
        if (existing is null)
        {
            _entries.Add(new KnownHostEntry
            {
                Endpoint = endpoint,
                Algorithm = algorithm,
                FingerprintSha256 = fingerprintSha256,
                FirstSeen = DateTimeOffset.Now
            });
        }
        else
        {
            existing.Algorithm = algorithm;
            existing.FingerprintSha256 = fingerprintSha256;
        }

        JsonStore.Save(
            FileName,
            _entries.OrderBy(e => e.Endpoint, StringComparer.OrdinalIgnoreCase).ToList());
    }
}
