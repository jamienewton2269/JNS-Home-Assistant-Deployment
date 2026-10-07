using System.Text.Json.Serialization;

namespace JnsSshTerminal.Models;

public enum CommandHistoryKind
{
    Command,
    ScriptBlock
}

public sealed class CommandHistoryEntry
{
    public DateTimeOffset When { get; set; } = DateTimeOffset.Now;
    public string Text { get; set; } = "";
    public CommandHistoryKind Kind { get; set; }
    public bool Pinned { get; set; }

    [JsonIgnore]
    public string DisplayText
    {
        get
        {
            var oneLine = Text.Replace("\r", "").Replace("\n", " ↵ ").Trim();
            if (oneLine.Length > 90)
            {
                oneLine = oneLine[..90] + "…";
            }

            string prefix = Pinned ? "★ " : "";
            return prefix + (Kind == CommandHistoryKind.ScriptBlock ? $"[BLOCK] {oneLine}" : oneLine);
        }
    }
}
