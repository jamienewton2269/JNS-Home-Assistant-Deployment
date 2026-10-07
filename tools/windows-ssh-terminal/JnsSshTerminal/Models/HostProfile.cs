namespace JnsSshTerminal.Models;

public sealed class HostProfile
{
    public string Name { get; set; } = "";
    public string Host { get; set; } = "";
    public int Port { get; set; } = 22;
    public string Username { get; set; } = "";
    public string? KeyFile { get; set; }

    public override string ToString() =>
        string.IsNullOrWhiteSpace(Name) ? $"{Username}@{Host}:{Port}" : Name;
}
