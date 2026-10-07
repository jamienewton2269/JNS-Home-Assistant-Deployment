namespace JnsSshTerminal.Models;

public sealed class DetachedSessionInfo
{
    public string SessionName { get; set; } = "";
    public string Label { get; set; } = "";
    public string Host { get; set; } = "";
    public int Port { get; set; } = 22;
    public string Username { get; set; } = "";
    public string? KeyFile { get; set; }
    public DateTime DetachedAtUtc { get; set; } = DateTime.UtcNow;

    public override string ToString() =>
        $"{Label} • {Username}@{Host}:{Port} • {DetachedAtUtc.ToLocalTime():yyyy-MM-dd HH:mm}";
}
