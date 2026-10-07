namespace JnsSshTerminal.Models;

public enum DetachedSessionState
{
    Unknown,
    RunningDetached,
    RunningAttached,
    Ended
}

public sealed class DetachedSessionInfo
{
    public string SessionName { get; set; } = "";
    public string Label { get; set; } = "";
    public string Host { get; set; } = "";
    public int Port { get; set; } = 22;
    public string Username { get; set; } = "";
    public string? KeyFile { get; set; }
    public DateTime FirstRecordedUtc { get; set; } = DateTime.UtcNow;
    public DateTime? RemoteCreatedUtc { get; set; }
    public DateTime? LastSeenUtc { get; set; }
    public DateTime? LastCheckedUtc { get; set; }
    public DateTime? ConfirmedEndedUtc { get; set; }
    public DetachedSessionState State { get; set; } = DetachedSessionState.Unknown;

    public string StateText => State switch
    {
        DetachedSessionState.RunningDetached => "RUNNING / DETACHED",
        DetachedSessionState.RunningAttached => "RUNNING / ATTACHED",
        DetachedSessionState.Ended => "ENDED",
        _ => "UNKNOWN / NOT CHECKED"
    };

    public override string ToString()
    {
        DateTime when = (LastSeenUtc ?? RemoteCreatedUtc ?? FirstRecordedUtc).ToLocalTime();
        return $"[{StateText}] {Label} • {Username}@{Host}:{Port} • {when:yyyy-MM-dd HH:mm}";
    }
}
