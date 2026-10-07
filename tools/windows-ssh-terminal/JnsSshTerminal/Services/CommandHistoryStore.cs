using System.Collections.ObjectModel;
using JnsSshTerminal.Models;

namespace JnsSshTerminal.Services;

public sealed class CommandHistoryStore
{
    private const string FileName = "command-history.json";
    private const int MaxEntries = 500;
    private const int MaxUnpinnedCharacters = 262_144;

    public ObservableCollection<CommandHistoryEntry> Entries { get; } = new();

    public void Load()
    {
        Entries.Clear();
        foreach (var entry in JsonStore.Load(FileName, new List<CommandHistoryEntry>())
                     .OrderByDescending(e => e.When))
        {
            Entries.Add(entry);
        }

        Prune();
    }

    public void Add(string text)
    {
        text = text.TrimEnd();
        if (string.IsNullOrWhiteSpace(text))
            return;

        Entries.Insert(0, new CommandHistoryEntry
        {
            When = DateTimeOffset.Now,
            Text = text,
            Kind = text.Contains('\n') || text.Contains('\r')
                ? CommandHistoryKind.ScriptBlock
                : CommandHistoryKind.Command
        });

        Prune();
        Save();
    }

    public void Remove(CommandHistoryEntry entry)
    {
        Entries.Remove(entry);
        Save();
    }

    public void TogglePinned(CommandHistoryEntry entry)
    {
        entry.Pinned = !entry.Pinned;
        Save();
    }

    public void Save()
    {
        // Multiline/script blocks stay available for the current process only.
        // They become durable history only when the user explicitly pins them.
        var persistent = Entries
            .Where(e => e.Pinned || e.Kind == CommandHistoryKind.Command)
            .ToList();

        JsonStore.Save(FileName, persistent);
    }

    private void Prune()
    {
        while (Entries.Count > MaxEntries)
        {
            var removable = Entries.LastOrDefault(e => !e.Pinned);
            if (removable is null)
                break;

            Entries.Remove(removable);
        }

        var unpinnedChars = Entries.Where(e => !e.Pinned).Sum(e => e.Text.Length);
        while (unpinnedChars > MaxUnpinnedCharacters)
        {
            var removable = Entries.LastOrDefault(e => !e.Pinned);
            if (removable is null)
                break;

            unpinnedChars -= removable.Text.Length;
            Entries.Remove(removable);
        }
    }
}
