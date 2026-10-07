using JnsSshTerminal.Models;

namespace JnsSshTerminal.Services;

public sealed class LocalDataWatchdog
{
    private static readonly TimeSpan TempRetention=TimeSpan.FromDays(1);
    private static readonly TimeSpan EndedSessionRetention=TimeSpan.FromDays(7);

    public void CleanupTransientFiles()
    {
        string directory=JsonStore.DataDirectory;
        if(!Directory.Exists(directory)) return;
        DateTime cutoff=DateTime.UtcNow-TempRetention;
        foreach(string file in Directory.EnumerateFiles(directory,"*.tmp",SearchOption.TopDirectoryOnly))
        {
            try{if(File.GetLastWriteTimeUtc(file)<cutoff) File.Delete(file);}catch{}
        }
    }

    public IEnumerable<DetachedSessionInfo> PruneSessionRegistry(IEnumerable<DetachedSessionInfo> sessions)
    {
        DateTime endedCutoff=DateTime.UtcNow-EndedSessionRetention;
        return sessions
            .GroupBy(item=>$"{item.Username}{item.Host}{item.Port}{item.SessionName}",StringComparer.OrdinalIgnoreCase)
            .Select(group=>group.OrderByDescending(item=>item.LastSeenUtc??item.FirstRecordedUtc).First())
            .Where(item=>item.State!=DetachedSessionState.Ended||item.ConfirmedEndedUtc is null||item.ConfirmedEndedUtc>endedCutoff)
            .ToList();
    }
}
