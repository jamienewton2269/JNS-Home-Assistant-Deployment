using JnsSshTerminal.Models;

namespace JnsSshTerminal.Services;

public sealed class DetachedSessionStore
{
    private const string FileName = "detached-sessions.json";

    public List<DetachedSessionInfo> Load()
    {
        var sessions = JsonStore.Load(FileName, new List<DetachedSessionInfo>())
            .Where(item => !string.IsNullOrWhiteSpace(item.SessionName))
            .ToList();

        foreach (var item in sessions.Where(item => item.State != DetachedSessionState.Ended))
            item.State = DetachedSessionState.Unknown;

        return sessions
            .OrderBy(item => item.State == DetachedSessionState.Ended ? 1 : 0)
            .ThenByDescending(item => item.LastSeenUtc ?? item.FirstRecordedUtc)
            .ToList();
    }

    public void Save(IEnumerable<DetachedSessionInfo> sessions) =>
        JsonStore.Save(
            FileName,
            sessions
                .Where(item => !string.IsNullOrWhiteSpace(item.SessionName))
                .OrderBy(item => item.State == DetachedSessionState.Ended ? 1 : 0)
                .ThenByDescending(item => item.LastSeenUtc ?? item.FirstRecordedUtc)
                .ToList());
}
