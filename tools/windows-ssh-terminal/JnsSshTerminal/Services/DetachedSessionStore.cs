using JnsSshTerminal.Models;

namespace JnsSshTerminal.Services;

public sealed class DetachedSessionStore
{
    private const string FileName = "detached-sessions.json";

    public List<DetachedSessionInfo> Load() =>
        JsonStore.Load(FileName, new List<DetachedSessionInfo>())
            .Where(item => !string.IsNullOrWhiteSpace(item.SessionName))
            .OrderByDescending(item => item.DetachedAtUtc)
            .ToList();

    public void Save(IEnumerable<DetachedSessionInfo> sessions) =>
        JsonStore.Save(
            FileName,
            sessions
                .Where(item => !string.IsNullOrWhiteSpace(item.SessionName))
                .OrderByDescending(item => item.DetachedAtUtc)
                .ToList());
}
