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

    public string DisplayText
    {
        get
        {
            var oneLine = Text.Replace("\r", "").Replace("\n", " ↵ ").Trim();
            if (oneLine.Length > 90)
            {
                oneLine = oneLine[..90] + "…";
            }

            return Kind == CommandHistoryKind.ScriptBlock ? $"[BLOCK] {oneLine}" : oneLine;
        }
    }
}
